import yt_dlp
import logging
from typing import Optional

logger = logging.getLogger(__name__)

QUALITY_OPTIONS = {
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "audio": "bestaudio/best",
}


def get_video_info(url: str) -> Optional[dict]:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Failed to get video info: {e}")
        return None


def get_playlist_videos(url: str) -> list:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if "entries" in info:
                return [
                    entry
                    for entry in info["entries"]
                    if entry and entry.get("url")
                ]
            return []
    except Exception as e:
        logger.error(f"Failed to get playlist videos: {e}")
        return []


def get_available_qualities(video_info: dict) -> list:
    formats = video_info.get("formats", [])
    heights = set()
    for f in formats:
        h = f.get("height")
        if h and h > 0:
            heights.add(h)

    available = []
    for label in ["1080p", "720p", "480p", "360p"]:
        h = int(label.replace("p", ""))
        if any(available_h >= h for available_h in heights):
            available.append(label)

    if video_info.get("ext") in ["mp3", "m4a", "webm", "ogg"] or any(
        f.get("vcodec") == "none" for f in formats
    ):
        available.append("audio")

    return available if available else ["360p"]
