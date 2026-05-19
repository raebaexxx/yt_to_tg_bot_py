from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.youtube import QUALITY_OPTIONS


def get_quality_keyboard(available_qualities: list, url: str = None) -> InlineKeyboardMarkup:
    quality_labels = {
        "4k": "4K (2160p)",
        "1080p": "1080p (Full HD)",
        "720p": "720p (HD)",
        "480p": "480p",
        "360p": "360p",
        "audio": "Audio only",
    }

    rows = []
    for q in available_qualities:
        callback_data = f"quality_{q}"
        if url:
            callback_data = f"quality_{q}_{hash(url) % 10000}"
        rows.append([
            InlineKeyboardButton(
                text=quality_labels.get(q, q),
                callback_data=callback_data,
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_playlist_keyboard(
    videos: list, current_page: int = 0, per_page: int = 10
) -> InlineKeyboardMarkup:
    rows = []

    start = current_page * per_page
    end = start + per_page
    page_videos = videos[start:end]

    for i, video in enumerate(page_videos):
        idx = start + i
        title = video.get("title", f"Video {idx + 1}")[:50]
        rows.append([
            InlineKeyboardButton(
                text=f"{idx + 1}. {title}",
                callback_data=f"pl_video_{idx}",
            )
        ])

    nav_row = []
    if current_page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="Previous", callback_data=f"pl_page_{current_page - 1}"
            )
        )
    if end < len(videos):
        nav_row.append(
            InlineKeyboardButton(
                text="Next", callback_data=f"pl_page_{current_page + 1}"
            )
        )

    rows.append([
        InlineKeyboardButton(
            text="Download all",
            callback_data="pl_download_all",
        )
    ])

    if nav_row:
        rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Cancel",
                    callback_data="cancel",
                )
            ]
        ]
    )
