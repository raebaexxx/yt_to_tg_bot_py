import os
import yt_dlp
import subprocess
import logging
from typing import Optional, Callable
from config import DOWNLOAD_DIR
from utils.helpers import sanitize_filename

logger = logging.getLogger(__name__)


class ProgressHook:
    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback

    def __call__(self, d):
        if d["status"] == "downloading":
            percent = d.get("_percent_str", "0%")
            speed = d.get("_speed_str", "N/A")
            if self.callback:
                self.callback(f"Downloading: {percent} at {speed}")
        elif d["status"] == "finished":
            if self.callback:
                self.callback("Download complete, processing...")


def download_video(
    url: str,
    quality: str,
    output_dir: str = None,
    progress_callback: Optional[Callable] = None,
) -> Optional[str]:
    if output_dir is None:
        output_dir = DOWNLOAD_DIR

    os.makedirs(output_dir, exist_ok=True)

    from services.youtube import QUALITY_OPTIONS

    format_str = QUALITY_OPTIONS.get(quality, QUALITY_OPTIONS["720p"])

    if quality == "audio":
        format_str = "bestaudio"
        ext = "m4a"
    else:
        ext = "mp4"

    filename = sanitize_filename("video")
    output_template = os.path.join(output_dir, f"{filename}.%(ext)s")

    ydl_opts = {
        "format": format_str,
        "outtmpl": output_template,
        "merge_output_format": "mp4" if quality != "audio" else None,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [ProgressHook(progress_callback)],
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
