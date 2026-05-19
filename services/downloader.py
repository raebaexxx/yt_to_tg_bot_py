import os
import asyncio
import yt_dlp
import subprocess
import logging
import time
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
                self.bot.edit_message_text(text="Download complete!", chat_id=self.chat_id, message_id=self.message_id),
                self.loop,
            )


def _build_format_string(quality: str) -> tuple:
    if quality == "audio":
        return "bestaudio[acodec^=mp4a]/bestaudio", True

    height_map = {
        "4k": 2160,
        "1080p": 1080,
        "720p": 720,
        "480p": 480,
        "360p": 360,
    }
    h = height_map.get(quality, 720)

    native_mp4 = (
        f"bestvideo[vcodec^=avc1][height<={h}]+bestaudio[acodec^=mp4a]/"
        f"bestvideo[vcodec^=avc1][height<={h}]+bestaudio/"
        f"best[height<={h}][ext=mp4]/"
        f"best[height<={h}]"
    )
    return native_mp4, False


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

    format_str, is_audio = _build_format_string(quality)

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

    if not is_audio:
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

            if is_audio:
                if not downloaded.endswith(".m4a"):
                    m4a_path = os.path.join(output_dir, f"{filename}.m4a")
                    _convert_audio_to_m4a(downloaded, m4a_path)
                    if os.path.exists(m4a_path):
                        os.remove(downloaded)
                        return m4a_path
                return downloaded

            if downloaded.endswith(".mp4"):
                if _is_h264_mp4(downloaded):
                    logger.info(f"Video already in H.264 MP4 format, no conversion needed: {downloaded}")
                    return downloaded

            mp4_path = os.path.join(output_dir, f"{filename}.mp4")
            if not _convert_to_phone_mp4(downloaded, mp4_path):
                logger.error("Failed to convert video to phone-compatible format")
                return None
            if os.path.exists(mp4_path):
                os.remove(downloaded)
            return mp4_path

    except Exception as e:
        logger.error(f"Failed to download video: {e}")
        return None


def _is_h264_mp4(filepath: str) -> bool:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name",
        "-of", "csv=p=0",
        filepath,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        codec = result.stdout.strip()
        return codec in ("h264", "avc1")
    except Exception:
        return False


def _convert_to_phone_mp4(input_path: str, output_path: str) -> bool:
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "22",
        "-profile:v", "high",
        "-level", "4.0",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-y", output_path,
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _, stderr = process.communicate(timeout=7200)

        if process.returncode != 0:
            logger.error(f"FFmpeg conversion failed: {stderr[-500:]}")
            return False

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error("FFmpeg produced empty output")
            return False

        return True

    except subprocess.TimeoutExpired:
        process.kill()
        logger.error("FFmpeg conversion timed out")
        return False
    except Exception as e:
        logger.error(f"FFmpeg conversion failed: {e}")
        return False


def _convert_audio_to_m4a(input_path: str, output_path: str) -> bool:
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:a", "aac",
        "-b:a", "128k",
        "-y", output_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Audio conversion failed: {e}")
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

                if thumb_url.endswith(".webp"):
                    webp_path = os.path.join(output_dir, "thumb.webp")
                    import urllib.request
                    urllib.request.urlretrieve(thumb_url, webp_path)
                    _convert_webp_to_jpg(webp_path, thumb_path)
                    if os.path.exists(webp_path):
                        os.remove(webp_path)
                else:
                    import urllib.request
                    urllib.request.urlretrieve(thumb_url, thumb_path)

                if os.path.exists(thumb_path):
                    return thumb_path
    except Exception as e:
        logger.error(f"Failed to download thumbnail: {e}")
    return None


def _convert_webp_to_jpg(webp_path: str, jpg_path: str) -> bool:
    cmd = [
        "ffmpeg",
        "-i", webp_path,
        "-q:v", "2",
        jpg_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False
