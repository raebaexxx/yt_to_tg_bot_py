import os
import logging
from typing import Optional
import requests
from config import OPENSUBTITLES_API_KEY, OPENSUBTITLES_USERNAME, OPENSUBTITLES_PASSWORD

logger = logging.getLogger(__name__)

BASE_URL = "https://api.opensubtitles.com/api/v1"
HEADERS = {
    "Api-Key": OPENSUBTITLES_API_KEY,
    "Content-Type": "application/json",
    "User-Agent": "MovieBot v1.0",
}

_token: Optional[str] = None


def _login() -> Optional[str]:
    global _token
    if _token:
        return _token

    if not OPENSUBTITLES_API_KEY:
        logger.error("OPENSUBTITLES_API_KEY not set")
        return None

    try:
        resp = requests.post(
            f"{BASE_URL}/login",
            json={
                "username": OPENSUBTITLES_USERNAME,
                "password": OPENSUBTITLES_PASSWORD,
            },
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _token = data.get("token")
        return _token
    except Exception as e:
        logger.error(f"OpenSubtitles login failed: {e}")
        return None


def search_subtitles(imdb_id: str = None, query: str = None, languages: list = None) -> list:
    token = _login()
    if not token:
        return []

    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    params = {"page": 1, "limit": 10}

    if imdb_id:
        params["imdb_id"] = imdb_id.replace("tt", "")
    if query:
        params["query"] = query
    if languages:
        params["languages"] = ",".join(languages)

    try:
        resp = requests.get(
            f"{BASE_URL}/subtitles",
            headers=headers,
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            files = attrs.get("files", [])
            if not files:
                continue

            results.append({
                "id": item.get("id"),
                "language": attrs.get("language", "unknown"),
                "language_name": attrs.get("language", "unknown"),
                "title": attrs.get("feature_details", {}).get("title", ""),
                "year": attrs.get("feature_details", {}).get("year", 0),
                "file_id": files[0].get("file_id"),
                "file_name": files[0].get("file_name", ""),
            })

        return results
    except Exception as e:
        logger.error(f"OpenSubtitles search failed: {e}")
        return []


def download_subtitle(file_id: str, output_path: str) -> bool:
    token = _login()
    if not token:
        return False

    headers = {**HEADERS, "Authorization": f"Bearer {token}"}

    try:
        resp = requests.post(
            f"{BASE_URL}/download",
            headers=headers,
            json={"file_id": int(file_id)},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        download_url = data.get("link")
        if not download_url:
            logger.error("No download URL from OpenSubtitles")
            return False

        resp2 = requests.get(download_url, timeout=30)
        resp2.raise_for_status()

        content = resp2.content
        if download_url.endswith(".zip") or download_url.endswith(".gz"):
            import zipfile
            import io
            import gzip

            if download_url.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for name in zf.namelist():
                        if name.endswith(".srt"):
                            with open(output_path, "wb") as f:
                                f.write(zf.read(name))
                            return True
            elif download_url.endswith(".gz"):
                decompressed = gzip.decompress(content)
                srt_content = decompressed.decode("utf-8", errors="replace")
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(srt_content)
                return True
        else:
            with open(output_path, "wb") as f:
                f.write(content)
            return True

        return False
    except Exception as e:
        logger.error(f"OpenSubtitles download failed: {e}")
        return False
