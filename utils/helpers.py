import re
import os


def is_youtube_url(url: str) -> bool:
    patterns = [
        r"(https?://)?(www\.)?(youtube\.com/watch\?v=[\w-]+)",
        r"(https?://)?(www\.)?(youtu\.be/[\w-]+)",
        r"(https?://)?(www\.)?(youtube\.com/shorts/[\w-]+)",
        r"(https?://)?(www\.)?(youtube\.com/playlist\?list=[\w-]+)",
        r"(https?://)?(www\.)?(youtube\.com/channel/[\w-]+)",
    ]
    return any(re.match(p, url) for p in patterns)


def is_playlist_url(url: str) -> bool:
    return "playlist?list=" in url or "/playlists" in url


def format_duration(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def sanitize_filename(filename: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")
    return filename[:100]
