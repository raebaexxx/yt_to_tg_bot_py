import os
import subprocess
import logging
from config import MAX_FILE_SIZE_BYTES

logger = logging.getLogger(__name__)


def get_file_size(filepath: str) -> int:
    return os.path.getsize(filepath)


def needs_split(filepath: str) -> bool:
    return get_file_size(filepath) > MAX_FILE_SIZE_BYTES


def split_video(filepath: str, output_dir: str) -> list:
    if not needs_split(filepath):
        return [filepath]

    logger.info(f"Splitting video: {filepath}")
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    ext = os.path.splitext(filepath)[1]

    duration = _get_duration(filepath)
    if duration <= 0:
        logger.error("Cannot determine video duration")
        return [filepath]

    file_size = get_file_size(filepath)
    part_duration = int(
        (MAX_FILE_SIZE_BYTES * 0.95 / file_size) * duration
    )

    if part_duration <= 0:
        part_duration = max(60, int(duration / 10))

    output_pattern = os.path.join(output_dir, f"{base_name}_part_%03d{ext}")

    cmd = [
        "ffmpeg",
        "-i",
        filepath,
        "-c",
        "copy",
        "-map",
        "0",
        "-f",
        "segment",
        "-segment_time",
        str(part_duration),
        "-reset_timestamps",
        "1",
        output_pattern,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if result.returncode != 0:
            logger.error(f"FFmpeg split failed: {result.stderr}")
            return [filepath]

        parts = sorted(
            [
                os.path.join(output_dir, f)
                for f in os.listdir(output_dir)
                if f.startswith(f"{base_name}_part_") and f.endswith(ext)
            ]
        )
        logger.info(f"Split into {len(parts)} parts")
        return parts

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg split timed out")
        return [filepath]
    except Exception as e:
        logger.error(f"Failed to split video: {e}")
        return [filepath]


def _get_duration(filepath: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        filepath,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"Failed to get duration: {e}")
        return 0
