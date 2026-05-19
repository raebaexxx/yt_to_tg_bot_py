import os
import re
import time
import logging
import asyncio
import requests
from typing import Optional
from config import RUTRACKER_USERNAME, RUTRACKER_PASSWORD, DOWNLOAD_DIR

logger = logging.getLogger(__name__)

RUTRACKER_URL = "https://rutracker.org"
RUTRACKER_API = "https://api.rutracker.org/api/v1"

_session_cookie: Optional[str] = None


def login() -> Optional[str]:
    global _session_cookie
    if _session_cookie:
        return _session_cookie

    if not RUTRACKER_USERNAME or not RUTRACKER_PASSWORD:
        logger.error("RUTRACKER_USERNAME or RUTRACKER_PASSWORD not set")
        return None

    try:
        session = requests.Session()
        resp = session.post(
            f"{RUTRACKER_URL}/forum/login.php",
            data={
                "login_username": RUTRACKER_USERNAME,
                "login_password": RUTRACKER_PASSWORD,
                "login": "Вход",
            },
            timeout=15,
        )

        if "logout" in resp.text.lower() or resp.cookies.get("bb_session"):
            _session_cookie = resp.cookies.get("bb_session")
            logger.info("Rutracker login successful")
            return _session_cookie
        else:
            logger.error("Rutracker login failed")
            return None
    except Exception as e:
        logger.error(f"Rutracker login error: {e}")
        return None


def search(query: str) -> list:
    cookie = login()
    if not cookie:
        return []

    try:
        session = requests.Session()
        session.cookies.set("bb_session", cookie)
        session.cookies.set("bb_dl", cookie)

        resp = session.get(
            f"{RUTRACKER_URL}/forum/tracker.php",
            params={
                "nm": query,
                "o": 10,
                "s": 2,
            },
            timeout=15,
        )
        resp.raise_for_status()

        results = _parse_search_results(resp.text)
        logger.info(f"Rutracker search for '{query}': found {len(results)} results")
        return results
    except Exception as e:
        logger.error(f"Rutracker search failed: {e}")
        return []


def _parse_search_results(html: str) -> list:
    results = []
    pattern = re.compile(
        r'<a[^>]+class="tLink"[^>]+href="\.\/forum\/viewtopic\.php\?t=(\d+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    for match in pattern.finditer(html):
        torrent_id = match.group(1)
        title = re.sub(r'<[^>]+>', '', match.group(2)).strip()

        if title:
            results.append({
                "id": int(torrent_id),
                "title": title,
                "url": f"{RUTRACKER_URL}/forum/viewtopic.php?t={torrent_id}",
            })

    return results


def get_magnet(torrent_id: int) -> Optional[str]:
    cookie = login()
    if not cookie:
        return None

    try:
        session = requests.Session()
        session.cookies.set("bb_session", cookie)
        session.cookies.set("bb_dl", cookie)

        resp = session.get(
            f"{RUTRACKER_URL}/forum/dl.php",
            params={"t": torrent_id},
            timeout=15,
            allow_redirects=False,
        )

        if resp.status_code == 302:
            location = resp.headers.get("Location", "")
            if "magnet:" in location:
                return location

        resp2 = session.get(
            f"{RUTRACKER_URL}/forum/dl.php",
            params={"t": torrent_id},
            timeout=15,
        )

        if ".torrent" in resp2.headers.get("Content-Disposition", ""):
            return _torrent_to_magnet(resp2.content)

        return None
    except Exception as e:
        logger.error(f"Failed to get magnet for {torrent_id}: {e}")
        return None


def _torrent_to_magnet(torrent_data: bytes) -> Optional[str]:
    try:
        import bencode3
        torrent = bencode3.bdecode(torrent_data)
        info = torrent[b"info"]
        info_hash = __import__("hashlib").sha1(bencode3.bencode(info)).hexdigest()
        name = info.get(b"name", b"unknown").decode("utf-8", errors="replace")
        return f"magnet:?xt=urn:btih:{info_hash}&dn={name}"
    except Exception as e:
        logger.error(f"Failed to convert torrent to magnet: {e}")
        return None


async def download_torrent(
    magnet: str,
    output_dir: str,
    progress_callback=None,
    cancel_ctx=None,
) -> Optional[str]:
    try:
        import libtorrent as lt
    except ImportError:
        logger.error("libtorrent not installed. Run: pip install libtorrent")
        return None

    return await _download_with_libtorrent(magnet, output_dir, progress_callback, cancel_ctx)


async def _download_with_libtorrent(
    magnet: str,
    output_dir: str,
    progress_callback=None,
    cancel_ctx=None,
) -> Optional[str]:
    import libtorrent as lt

    ses = lt.session()
    ses.listen_on(6881, 6891)

    params = {
        "save_path": output_dir,
        "storage_mode": lt.storage_mode_t.storage_mode_sparse,
    }

    try:
        handle = lt.add_magnet_uri(ses, magnet, params)
    except Exception as e:
        logger.error(f"Failed to add magnet: {e}")
        return None

    logger.info(f"Downloading torrent: {handle.name() or 'unknown'}")

    last_update = 0
    total_size = 0

    while not handle.has_metadata():
        if cancel_ctx and cancel_ctx.is_cancelled:
            ses.remove_torrent(handle)
            return None
        await asyncio.sleep(1)

    total_size = handle.total_wanted()

    while not handle.is_seed():
        if cancel_ctx and cancel_ctx.is_cancelled:
            ses.remove_torrent(handle)
            return None

        status = handle.status()
        now = time.time()

        if now - last_update >= 2:
            last_update = now
            progress = status.progress * 100
            speed = status.download_rate
            downloaded = status.total_done
            remaining = total_size - downloaded
            eta = (remaining / speed) if speed > 0 else 0

            if progress_callback:
                progress_callback(progress, speed, downloaded, remaining, eta, total_size)

        await asyncio.sleep(1)

    files = handle.get_torrent_info().files()
    largest_file = max(
        [(f.path, f.size) for f in files if f.size > 50 * 1024 * 1024],
        key=lambda x: x[1],
        default=(None, 0),
    )

    ses.remove_torrent(handle)

    if largest_file[0]:
        return os.path.join(output_dir, largest_file[0])

    files_in_dir = [
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if os.path.getsize(os.path.join(output_dir, f)) > 50 * 1024 * 1024
    ]

    if files_in_dir:
        return max(files_in_dir, key=os.path.getsize)

    return None
