import os
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_video_info(filepath: str) -> dict:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height",
        "-of", "csv=p=0",
        filepath,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        parts = result.stdout.strip().strip(",").split(",")
        if len(parts) == 3:
            return {"codec": parts[0], "width": int(parts[1]), "height": int(parts[2])}
        elif len(parts) == 1:
            return {"codec": parts[0], "width": None, "height": None}
    except Exception as e:
        logger.error(f"Failed to get video info: {e}")
    return {"codec": None, "width": None, "height": None}


def get_duration(filepath: str) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filepath,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"Failed to get duration: {e}")
        return 0


def get_audio_tracks(filepath: str) -> list:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index,codec_name,language,title",
        "-of", "json",
        filepath,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        import json
        data = json.loads(result.stdout)
        tracks = []
        for stream in data.get("streams", []):
            tracks.append({
                "index": stream.get("index"),
                "codec": stream.get("codec_name"),
                "language": stream.get("tags", {}).get("language", "unknown"),
                "title": stream.get("tags", {}).get("title", ""),
            })
        return tracks
    except Exception as e:
        logger.error(f"Failed to get audio tracks: {e}")
        return []
