import os
import asyncio
import yt_dlp
import subprocess
import logging
import time
import re
from typing import Optional
from config import DOWNLOAD_DIR
from utils.helpers import sanitize_filename, format_file_size

logger = logging.getLogger(__name__)


class ProgressHook:
    def __init__(self, bot, chat_id, message_id, loop):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.loop = loop
        self.last_update = 0
        self._edit_task = None

    def _safe_edit(self, text):
        async def _do_edit():
            try:
                await self.bot.edit_message_text(
                    text=text,
                    chat_id=self.chat_id,
                    message_id=self.message_id,
                )
            except Exception as e:
                logger.debug(f"Progress edit failed (ignored): {e}")

        if self._edit_task and not self._edit_task.done():
            self._edit_task.cancel()
        self._edit_task = asyncio.run_coroutine_threadsafe(_do_edit(), self.loop)

    def __call__(self, d):
        if d["status"] == "downloading":
            now = time.time()
            if now - self.last_update < 2:
                return
            self.last_update = now
            percent = d.get("_percent_str", "0%")
            speed = d.get("_speed_str", "N/A")
            text = f"Downloading: {percent} at {speed}"
            self._safe_edit(text)
        elif d["status"] == "finished":
            self._safe_edit("Download complete!")


def _build_format_string(quality: str) -> tuple:
    if quality == "audio":
        return "bestaudio[acodec^=mp4a]/bestaudio", True

    if quality == "4k":
        fmt = (
            "bestvideo[height=2160]+bestaudio[acodec^=mp4a]/"
            "bestvideo[height=2160]+bestaudio/"
            "bestvideo[height>=2160]+bestaudio[acodec^=mp4a]/"
            "bestvideo[height>=2160]+bestaudio/"
            "bestvideo[vcodec^=avc1][height<=2160]+bestaudio[acodec^=mp4a]/"
            "bestvideo[vcodec^=avc1][height<=2160]+bestaudio/"
            "bestvideo[height<=2160]+bestaudio[acodec^=mp4a]/"
            "bestvideo[height<=2160]+bestaudio/"
            "best[height<=2160][ext=mp4]/"
            "best[height<=2160]"
        )
    elif quality == "1080p":
        fmt = (
            "bestvideo[vcodec^=avc1][height=1080]+bestaudio[acodec^=mp4a]/"
            "bestvideo[vcodec^=avc1][height=1080]+bestaudio/"
            "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[acodec^=mp4a]/"
            "bestvideo[vcodec^=avc1][height<=1080]+bestaudio/"
            "bestvideo[height<=1080]+bestaudio[acodec^=mp4a]/"
            "bestvideo[height<=1080]+bestaudio/"
            "best[height<=1080][ext=mp4]/"
            "best[height<=1080]"
        )
    else:
        height_map = {
            "720p": 720,
            "480p": 480,
            "360p": 360,
        }
        h = height_map.get(quality, 720)
        fmt = (
            f"bestvideo[vcodec^=avc1][height<={h}]+bestaudio[acodec^=mp4a]/"
            f"bestvideo[vcodec^=avc1][height<={h}]+bestaudio/"
            f"best[height<={h}][ext=mp4]/"
            f"best[height<={h}]"
        )
    return fmt, False


async def download_video(
    url: str,
    quality: str,
    bot,
    chat_id: int,
    message_id: int,
    output_dir: str = None,
) -> Optional[tuple]:
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
        "socket_timeout": 300,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
        "retry_sleep_functions": {
            "http": lambda n: 5 * (n + 1),
            "fragment": lambda n: 5 * (n + 1),
        },
        "external_downloader": "aria2c",
        "external_downloader_args": [
            "--min-split-size=1M",
            "--max-connection-per-server=16",
            "--max-concurrent-downloads=16",
            "--split=16",
        ],
    }

    if not is_audio:
        ydl_opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None

            requested_formats = info.get("requested_formats", [])
            if requested_formats:
                for rf in requested_formats:
                    logger.info(f"yt-dlp selected format: {rf.get('format_note', '?')} - {rf.get('vcodec', '?')} / {rf.get('acodec', '?')} - {rf.get('width', '?')}x{rf.get('height', '?')}")
            else:
                logger.info(f"yt-dlp selected format: {info.get('format', '?')}")

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
                        return (m4a_path, None, None)
                return (downloaded, None, None)

            video_codec = _get_video_codec(downloaded)
            file_ext = os.path.splitext(downloaded)[1]
            file_size = os.path.getsize(downloaded)
            logger.info(f"Downloaded: {downloaded}, codec: {video_codec}, ext: {file_ext}, size: {format_file_size(file_size)}")

            if video_codec in ("h264", "avc1"):
                logger.info("Video is already H.264, preparing for streaming (no re-encode)")
                mp4_path = os.path.join(output_dir, f"{filename}_fixed.mp4")
                if _add_faststart(downloaded, mp4_path, bot, chat_id, message_id, loop):
                    os.remove(downloaded)
                    width, height = _get_video_dimensions(mp4_path)
                    return (mp4_path, width, height)
                else:
                    logger.warning("Faststart failed, sending original file")
                    width, height = _get_video_dimensions(downloaded)
                    return (downloaded, width, height)

            if quality == "4k":
                logger.info("4K video — converting AV1/VP9 to H.264")
                mp4_path = os.path.join(output_dir, f"{filename}_converted.mp4")
                if not _convert_4k_to_h264(downloaded, mp4_path, bot, chat_id, message_id, loop):
                    logger.error("Failed to convert 4K to H.264")
                    return None
                if os.path.exists(mp4_path):
                    os.remove(downloaded)
                width, height = _get_video_dimensions(mp4_path)
                return (mp4_path, width, height)

            logger.info(f"Video codec {video_codec} requires conversion to H.264")
            mp4_path = os.path.join(output_dir, f"{filename}_converted.mp4")
            if not _convert_to_phone_mp4(downloaded, mp4_path, bot, chat_id, message_id, loop):
                logger.error("Failed to convert video to phone-compatible format")
                return None
            if os.path.exists(mp4_path):
                os.remove(downloaded)
            width, height = _get_video_dimensions(mp4_path)
            return (mp4_path, width, height)

    except Exception as e:
        logger.error(f"Failed to download video: {e}")
        return None


def _get_video_codec(filepath: str) -> Optional[str]:
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
        return result.stdout.strip().strip(",")
    except Exception:
        return None


def _get_video_dimensions(filepath: str) -> tuple:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        filepath,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        parts = result.stdout.strip().strip(",").split(",")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None, None


def _safe_edit_text(bot, chat_id, message_id, text, loop):
    async def _do_edit():
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=message_id,
            )
        except Exception as e:
            logger.debug(f"Edit message failed (ignored): {e}")

    asyncio.run_coroutine_threadsafe(_do_edit(), loop)


def _add_faststart(input_path: str, output_path: str, bot=None, chat_id=None, message_id=None, loop=None) -> bool:
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c", "copy",
        "-movflags", "+faststart",
        "-y", output_path,
    ]

    logger.info(f"Adding faststart (stream copy, no re-encode)")
    logger.info(f"Command: {' '.join(cmd)}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        start_time = time.time()
        last_update = 0

        for line in process.stdout:
            line_str = line.strip()
            logger.debug(f"FFmpeg faststart: {line_str}")

            now = time.time()
            if now - last_update >= 2 and bot and chat_id and message_id and loop:
                elapsed = int(now - start_time)
                msg = f"Preparing video for streaming... ({elapsed}s)"
                logger.info(msg)
                _safe_edit_text(bot, chat_id, message_id, msg, loop)
                last_update = now

        process.wait(timeout=300)

        if process.returncode != 0:
            logger.error(f"Faststart failed with code {process.returncode}")
            return False

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error("Faststart produced empty output")
            return False

        input_size = os.path.getsize(input_path)
        output_size = os.path.getsize(output_path)
        logger.info(f"Faststart complete: {format_file_size(input_size)} -> {format_file_size(output_size)}")
        return True

    except Exception as e:
        logger.error(f"Faststart failed: {e}")
        return False


def _convert_to_phone_mp4(input_path: str, output_path: str, bot=None, chat_id=None, message_id=None, loop=None) -> bool:
    time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    duration_pattern = re.compile(r"Duration: (\d+):(\d+):(\d+\.\d+)")

    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-y", output_path,
    ]

    logger.info(f"Starting FFmpeg conversion")
    logger.info(f"Command: {' '.join(cmd)}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        input_size = os.path.getsize(input_path)
        start_time = time.time()
        last_update = 0
        total_duration = None

        for line in process.stdout:
            line_str = line.strip()
            logger.debug(f"FFmpeg: {line_str}")

            if total_duration is None:
                dur_match = duration_pattern.search(line_str)
                if dur_match:
                    h, m, s = dur_match.groups()
                    total_duration = int(h) * 3600 + int(m) * 60 + float(s)
                    logger.info(f"Video duration: {total_duration:.1f}s")

            time_match = time_pattern.search(line_str)
            if time_match:
                now = time.time()
                if now - last_update >= 2:
                    h, m, s = time_match.groups()
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)

                    elapsed = now - start_time
                    speed = current_time / elapsed if elapsed > 0 else 0
                    percent = int((current_time / total_duration) * 100) if total_duration else 0

                    msg = f"Converting: {percent}% (speed: {speed:.1f}x)"
                    logger.info(msg)

                    if bot and chat_id and message_id and loop:
                        _safe_edit_text(bot, chat_id, message_id, msg, loop)

                    last_update = now

        process.wait(timeout=7200)

        if process.returncode != 0:
            logger.error(f"FFmpeg conversion failed with code {process.returncode}")
            return False

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error("FFmpeg produced empty output")
            return False

        output_size = os.path.getsize(output_path)
        logger.info(f"FFmpeg conversion complete: {format_file_size(input_size)} -> {format_file_size(output_size)}")
        return True

    except subprocess.TimeoutExpired:
        process.kill()
        logger.error("FFmpeg conversion timed out")
        return False
    except Exception as e:
        logger.error(f"FFmpeg conversion failed: {e}")
        return False


def _convert_4k_to_h264(input_path: str, output_path: str, bot=None, chat_id=None, message_id=None, loop=None) -> bool:
    time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    duration_pattern = re.compile(r"Duration: (\d+):(\d+):(\d+\.\d+)")

    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "30",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-y", output_path,
    ]

    logger.info(f"Starting 4K conversion to H.264")
    logger.info(f"Command: {' '.join(cmd)}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        input_size = os.path.getsize(input_path)
        start_time = time.time()
        last_update = 0
        total_duration = None

        for line in process.stdout:
            line_str = line.strip()
            logger.debug(f"FFmpeg 4K: {line_str}")

            if total_duration is None:
                dur_match = duration_pattern.search(line_str)
                if dur_match:
                    h, m, s = dur_match.groups()
                    total_duration = int(h) * 3600 + int(m) * 60 + float(s)
                    logger.info(f"Video duration: {total_duration:.1f}s")

            time_match = time_pattern.search(line_str)
            if time_match:
                now = time.time()
                if now - last_update >= 2:
                    h, m, s = time_match.groups()
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)

                    elapsed = now - start_time
                    speed = current_time / elapsed if elapsed > 0 else 0
                    percent = int((current_time / total_duration) * 100) if total_duration else 0

                    msg = f"Converting 4K: {percent}% (speed: {speed:.1f}x)"
                    logger.info(msg)

                    if bot and chat_id and message_id and loop:
                        _safe_edit_text(bot, chat_id, message_id, msg, loop)

                    last_update = now

        process.wait(timeout=7200)

        if process.returncode != 0:
            logger.error(f"4K conversion failed with code {process.returncode}")
            return False

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error("4K conversion produced empty output")
            return False

        output_size = os.path.getsize(output_path)
        logger.info(f"4K conversion complete: {format_file_size(input_size)} -> {format_file_size(output_size)}")
        return True

    except subprocess.TimeoutExpired:
        process.kill()
        logger.error("4K conversion timed out")
        return False
    except Exception as e:
        logger.error(f"4K conversion failed: {e}")
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
