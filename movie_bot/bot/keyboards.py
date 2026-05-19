from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_search_results_keyboard(results: list) -> InlineKeyboardMarkup:
    rows = []
    for i, item in enumerate(results[:10]):
        year = item.get("year", "?")
        title = item.get("title", "Unknown")
        vtype = "🎬" if item.get("type") == "movie" else "📺"
        vote = item.get("vote", 0)
        label = f"{vtype} {title} ({year}) ⭐{vote:.1f}"
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"select_{item['tmdb_id']}_{item['type']}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_releases_keyboard(releases: list) -> InlineKeyboardMarkup:
    rows = []
    for i, release in enumerate(releases[:15]):
        title = release.get("title", "Unknown")[:60]
        voiceover = release.get("voiceover", "unknown")
        quality = release.get("quality", "unknown")
        label = f"{quality} | {voiceover} | {title}"
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"release_{release['id']}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="Cancel", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_quality_keyboard(qualities: list) -> InlineKeyboardMarkup:
    rows = []
    quality_labels = {
        "4K": "4K (2160p)",
        "1080p": "1080p (Full HD)",
        "720p": "720p (HD)",
        "480p": "480p",
        "360p": "360p",
    }
    for q in qualities:
        rows.append([
            InlineKeyboardButton(
                text=quality_labels.get(q, q),
                callback_data=f"quality_{q}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="Cancel", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_voiceover_keyboard(voiceovers: list) -> InlineKeyboardMarkup:
    rows = []
    for vo in voiceovers:
        rows.append([
            InlineKeyboardButton(
                text=vo,
                callback_data=f"voiceover_{vo}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="Cancel", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_subtitle_keyboard(languages: list) -> InlineKeyboardMarkup:
    rows = []
    lang_labels = {
        "eng": "🇬🇧 English",
        "rus": "🇷🇺 Russian",
        "ukr": "🇺🇦 Ukrainian",
        "fra": "🇫🇷 French",
        "deu": "🇩🇪 German",
        "spa": "🇪🇸 Spanish",
        "ita": "🇮🇹 Italian",
        "jpn": "🇯🇵 Japanese",
        "kor": "🇰🇷 Korean",
        "chi": "🇨🇳 Chinese",
        "ara": "🇸🇦 Arabic",
    }
    for lang in languages:
        rows.append([
            InlineKeyboardButton(
                text=lang_labels.get(lang, lang),
                callback_data=f"subtitle_{lang}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="No subtitles", callback_data="subtitle_none")
    ])
    rows.append([
        InlineKeyboardButton(text="Cancel", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_seasons_keyboard(seasons: int) -> InlineKeyboardMarkup:
    rows = []
    for s in range(1, seasons + 1):
        rows.append([
            InlineKeyboardButton(
                text=f"Season {s}",
                callback_data=f"season_{s}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="Cancel", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_episodes_keyboard(episodes: list) -> InlineKeyboardMarkup:
    rows = []
    for ep in episodes:
        num = ep.get("episode_number", "?")
        title = ep.get("title", f"Episode {num}")[:40]
        rows.append([
            InlineKeyboardButton(
                text=f"E{num}: {title}",
                callback_data=f"episode_{num}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="Cancel", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data="cancel")]
        ]
    )
