import os
import re
import time
import subprocess
import logging
from typing import Optional
from utils.helpers import format_file_size, format_eta

logger = logging.getLogger(__name__)


def burn_subtitles(
    input_path: str,
    subtitle_path: str,
    output_path: str,
    font_size: int = 24,
    progress_callback=None,
    cancel_ctx=None,
) -> bool:
    escaped_input = input_path.replace(":", "\\:").replace("'", "\\'")
    escaped_subs = subtitle_path.replace(":", "\\:").replace("'", "\\'")

    style = (
        f"FontSize={font_size},"
        f"PrimaryColour=&HFFFFFF&,"
        f"OutlineColour=&H000000&,"
        f"BorderStyle=4,"
        f"Outline=2,"
        f"Shadow=1,"
        f"MarginV=30"
    )

    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-vf", f"subtitles='{escaped_subs}':force_style='{style}'",
        "-c:a", "copy",
        "-c:s", "copy",
        "-movflags", "+faststart",
        "-y", output_path,
    ]

    logger.info(f"Starting subtitle burn-in")
    logger.info(f"Command: {' '.join(cmd)}")

    time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    duration_pattern = re.compile(r"Duration: (\d+):(\d+):(\d+\.\d+)")

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
            if cancel_ctx and cancel_ctx.is_cancelled:
                process.kill()
                logger.info("Burn-in cancelled by user")
                return False

            line_str = line.strip()
            logger.debug(f"FFmpeg burn-in: {line_str}")

            if total_duration is None:
                dur_match = duration_pattern.search(line_str)
                if dur_match:
                    h, m, s = dur_match.groups()
                    total_duration = int(h) * 3600 + int(m) * 60 + float(s)
                    logger.info(f"Video duration: {total_duration:.1f}s")

            time_match = time_pattern.search(line_str)
            if time_match:
                now = time.time()
                if now - last_update >= 3:
                    h, m, s = time_match.groups()
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)

                    elapsed = now - start_time
                    speed = current_time / elapsed if elapsed > 0 else 0
                    percent = int((current_time / total_duration) * 100) if total_duration else 0

                    remaining_time = ""
                    if speed > 0 and total_duration:
                        remaining_seconds = (total_duration - current_time) / speed
                        remaining_time = f"\nRemaining: {format_eta(remaining_seconds)}"

                    current_size = 0
                    if os.path.exists(output_path):
                        try:
                            current_size = os.path.getsize(output_path)
                        except OSError:
                            pass

                    msg = (
                        f"Burning subtitles: {percent}%\n"
                        f"Speed: {speed:.2f}x\n"
                        f"Input: {format_file_size(input_size)}\n"
                        f"Output: {format_file_size(current_size)}{remaining_time}"
                    )
                    logger.info(msg)

                    if progress_callback:
                        progress_callback(percent, speed, current_time, total_duration, current_size, input_size)

                    last_update = now

        process.wait(timeout=86400)

        if process.returncode != 0:
            logger.error(f"Burn-in failed with code {process.returncode}")
            return False

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error("Burn-in produced empty output")
            return False

        output_size = os.path.getsize(output_path)
        logger.info(f"Burn-in complete: {format_file_size(input_size)} -> {format_file_size(output_size)}")
        return True

    except subprocess.TimeoutExpired:
        process.kill()
        logger.error("Burn-in timed out")
        return False
    except Exception as e:
        logger.error(f"Burn-in failed: {e}")
        return False
