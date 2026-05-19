import os
import asyncio
import yt_dlp
import subprocess
import logging
from typing import Optional
from config import DOWNLOAD_DIR
from utils.helpers import sanitize_filename

logger = logging.getLogger(__name__)


class ProgressHook:
    def __init__(self, bot, chat_id, message_id, loop):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.loop = loop
        self.last_update = 0

    def __call__(self, d):
        if d["status"] == "downloading":
            import time
            now = time.time()
            if now - self.last_update < 2:
                return
            self.last_update = now
            percent = d.get("_percent_str", "0%")
            speed = d.get("_speed_str", "N/A")
            text = f"Downloading: {percent} at {speed}"
            asyncio.run_coroutine_threadsafe(
                self.bot.edit_message_text(text=text, chat_id=self.chat_id, message_id=self.message_id),
                self.loop,
            )
        elif d["status"] == "finished":
            asyncio.run_coroutine_threadsafe(
                self.bot.edit_message_text(text="Download complete, processing...", chat_id=self.chat_id, message_id=self.message_id),
                self.loop,
            )


async def download_video(
    url: str,
    quality: str,
    bot,
    chat_id: int,
    message_id: int,
    output_dir: str = None,
) -> Optional[str]:
    if output_dir is None:
        output_dir = DOWNLOAD_DIR

    os.makedirs(output_dir, exist_ok=True)

    from services.youtube import QUALITY_OPTIONS

    format_str = QUALITY_OPTIONS.get(quality, QUALITY_OPTIONS["720p"])

    if quality == "audio":
        format_str = "bestaudio"
    else:
        format_str = QUALITY_OPTIONS[quality]

    filename = sanitize_filename("video")
    output_template = os.path.join(output_dir, f"{filename}.%(ext)s")

    loop = asyncio.get_event_loop()
    progress_hook = ProgressHook(bot, chat_id, message_id, loop)

    ydl_opts = {
        "format": format_str,
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
        "socket_timeout": 30,
        "retries": 3,
    }

    if quality != "audio":
        ydl_opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None

            downloaded = ydl.prepare_filename(info)
            if not os.path.exists(downloaded):
                for ext_check in ["mp4", "mkv", "webm", "m4a"]:
                    potential = os.path.join(
                        output_dir, f"{filename}.{ext_check}"
                    )
                    if os.path.exists(potential):
                        downloaded = potential
                        break

            if not os.path.exists(downloaded):
                logger.error(f"Downloaded file not found: {downloaded}")
                return None

            if quality != "audio" and not downloaded.endswith(".mp4"):
                mp4_path = os.path.join(output_dir, f"{filename}.mp4")
                _convert_to_mp4(downloaded, mp4_path)
                if os.path.exists(mp4_path):
                    os.remove(downloaded)
                    downloaded = mp4_path

            return downloaded

    except Exception as e:
        logger.error(f"Failed to download video: {e}")
        return None


def _convert_to_mp4(input_path: str, output_path: str) -> bool:
    cmd = [
        "ffmpeg",
        "-i",
        input_path,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-y",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=3600
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"FFmpeg conversion failed: {e}")
        return False


def download_thumbnail(url: str, output_dir: str) -> Optional[str]:
    ydl_opts = {
        "writesthumbnail": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get("thumbnail"):
                thumb_url = info["thumbnail"]
                thumb_path = os.path.join(output_dir, "thumb.jpg")
                import urllib.request

                urllib.request.urlretrieve(thumb_url, thumb_path)
                return thumb_path
    except Exception as e:
        logger.error(f"Failed to download thumbnail: {e}")
    return None
