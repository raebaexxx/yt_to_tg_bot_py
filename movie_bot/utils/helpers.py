import re


def is_valid_query(query: str) -> bool:
    return len(query.strip()) >= 2


def format_duration(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return "Unknown"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {secs}s"


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")
    filename = re.sub(r"\s+", " ", filename).strip()
    return filename[:max_length]


def parse_release_name(name: str) -> dict:
    name_lower = name.lower()
    voiceover = "original"
    quality = "unknown"

    voiceover_map = {
        "lostfilm": "LostFilm",
        "lost film": "LostFilm",
        "кубик в кубе": "Кубик в Кубе",
        "kubik v kube": "Кубик в Кубе",
        "hdrezka": "HDRezka",
        "hd-rezka": "HDRezka",
        "newstudio": "NewStudio",
        "new studio": "NewStudio",
        "sony pictures": "Sony",
        "coldFilm": "ColdFilm",
        "coldfilm": "ColdFilm",
        "авторский": "Авторский",
        "двухголосый": "Двухголосый",
        "многоголосый": "Многоголосый",
        "профессиональный": "Профессиональный",
        "любительский": "Любительский",
    }

    for key, label in voiceover_map.items():
        if key in name_lower:
            voiceover = label
            break

    quality_map = {
        "2160p": "4K",
        "4k": "4K",
        "uhd": "4K",
        "1080p": "1080p",
        "720p": "720p",
        "480p": "480p",
        "360p": "360p",
    }

    for key, label in quality_map.items():
        if key in name_lower:
            quality = label
            break

    return {"voiceover": voiceover, "quality": quality}


def format_eta(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"
