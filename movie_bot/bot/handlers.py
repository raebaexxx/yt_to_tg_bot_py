import os
import asyncio
import logging
import time
from typing import Optional
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from bot.states import Search
from bot.keyboards import (
    get_search_results_keyboard,
    get_releases_keyboard,
    get_quality_keyboard,
    get_voiceover_keyboard,
    get_subtitle_keyboard,
    get_seasons_keyboard,
    get_episodes_keyboard,
    get_cancel_keyboard,
)
from services.tmdb import search as tmdb_search, get_details, get_season_episodes
from services.torrent import search as torrent_search, download_torrent
from services.subtitles import search_subtitles, download_subtitle
from services.burner import burn_subtitles
from services.splitter import split_video
from services.metadata import get_video_info, get_duration
from utils.helpers import sanitize_filename, format_file_size, format_duration, parse_release_name, format_eta
from utils.cleanup import cleanup_user_session
from utils.progress import safe_edit_text
from database.models import add_user, add_history
from config import DOWNLOAD_DIR, SUBTITLE_FONT_SIZE

logger = logging.getLogger(__name__)
router = Router()

SESSION_TTL = 600
MAX_SESSIONS = 1000


class SessionEntry:
    __slots__ = ("data", "created_at")

    def __init__(self, data: dict):
        self.data = data
        self.created_at = time.time()

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > SESSION_TTL


user_sessions: dict[int, SessionEntry] = {}
active_downloads: dict[int, object] = {}


def _get_session(user_id: int) -> Optional[dict]:
    entry = user_sessions.get(user_id)
    if entry is None or entry.is_expired:
        user_sessions.pop(user_id, None)
        return None
    return entry.data


def _set_session(user_id: int, data: dict):
    if len(user_sessions) >= MAX_SESSIONS:
        oldest_id = min(user_sessions, key=lambda uid: user_sessions[uid].created_at)
        user_sessions.pop(oldest_id)
    user_sessions[user_id] = SessionEntry(data)


def _clear_session(user_id: int):
    user_sessions.pop(user_id, None)


class DownloadContext:
    __slots__ = ("_cancelled",)

    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    await state.clear()
    await message.answer(
        "🎬 <b>Movie & Series Bot</b>\n\n"
        "Send me a movie or series name to search.\n\n"
        "Features:\n"
        "• Search movies & series (TMDB)\n"
        "• Download from Rutracker\n"
        "• Choose voiceover/quality\n"
        "• Burn-in subtitles (EN, RU, etc.)\n"
        "• Auto-split files >2GB\n\n"
        "Just type a title!"
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_search(message: Message, state: FSMContext):
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Please enter a title with at least 2 characters.")
        return

    await add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )

    status_msg = await message.answer("🔍 Searching...")

    await state.set_state(Search.selecting_result)

    def _do_search():
        return tmdb_search(query)

    results = await asyncio.to_thread(_do_search)

    if not results:
        await status_msg.edit_text("No results found. Try another title.")
        await state.clear()
        return

    _set_session(message.from_user.id, {"query": query})

    keyboard = get_search_results_keyboard(results)
    await status_msg.edit_text(
        f"Found {len(results)} results for '<b>{sanitize_filename(query)}</b>':",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("select_"), Search.selecting_result)
async def handle_select_result(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split("_")
    tmdb_id = int(parts[1])
    media_type = parts[2]

    session = _get_session(callback.from_user.id)
    if not session:
        await callback.answer("Session expired.")
        return

    await callback.message.edit_text("⏳ Getting details...")
    await callback.answer()

    def _get_details():
        return get_details(tmdb_id, media_type)

    details = await asyncio.to_thread(_get_details)
    if not details:
        await callback.message.edit_text("Failed to get details. Try again.")
        return

    session.update({
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "title": details["title"],
        "year": details["year"],
        "imdb_id": details.get("imdb_id"),
        "runtime": details.get("runtime", 0),
        "seasons": details.get("seasons", 0),
        "episodes": details.get("episodes", 0),
    })
    _set_session(callback.from_user.id, session)

    if media_type == "tv" and details.get("seasons", 0) > 1:
        await state.set_state(Search.selecting_season)
        keyboard = get_seasons_keyboard(details["seasons"])
        await callback.message.edit_text(
            f"📺 <b>{sanitize_filename(details['title'])}</b> ({details['year']})\n\n"
            f"Seasons: {details['seasons']}\n"
            f"Total episodes: {details['episodes']}\n\n"
            f"Select a season:",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await _search_releases(callback, state, bot, session)


@router.callback_query(F.data.startswith("season_"), Search.selecting_season)
async def handle_select_season(callback: CallbackQuery, state: FSMContext, bot: Bot):
    season_num = int(callback.data.split("_")[1])
    session = _get_session(callback.from_user.id)
    if not session:
        await callback.answer("Session expired.")
        return

    session["season"] = season_num
    _set_session(callback.from_user.id, session)

    await callback.message.edit_text("⏳ Getting episodes...")
    await callback.answer()

    def _get_eps():
        return get_season_episodes(session["tmdb_id"], season_num)

    episodes = await asyncio.to_thread(_get_eps)

    if not episodes:
        await _search_releases(callback, state, bot, session)
        return

    session["episodes_list"] = episodes
    _set_session(callback.from_user.id, session)

    keyboard = get_episodes_keyboard(episodes)
    await callback.message.edit_text(
        f"📺 <b>{sanitize_filename(session['title'])}</b> — Season {season_num}\n\n"
        f"Select an episode:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(Search.selecting_episode)


@router.callback_query(F.data.startswith("episode_"), Search.selecting_episode)
async def handle_select_episode(callback: CallbackQuery, state: FSMContext, bot: Bot):
    ep_num = int(callback.data.split("_")[1])
    session = _get_session(callback.from_user.id)
    if not session:
        await callback.answer("Session expired.")
        return

    session["episode"] = ep_num
    _set_session(callback.from_user.id, session)

    await callback.answer()
    await _search_releases(callback, state, bot, session)


async def _search_releases(callback, state, bot, session):
    title = session.get("title", "")
    year = session.get("year", "")
    season = session.get("season")
    episode = session.get("episode")

    search_query = title
    if year:
        search_query += f" {year}"
    if season:
        search_query += f" S{season:02d}"
    if episode:
        search_query += f"E{episode:02d}"

    await callback.message.edit_text(f"🔍 Searching releases for '<b>{sanitize_filename(search_query)}</b>'...")

    def _do_torrent_search():
        return torrent_search(search_query)

    releases = await asyncio.to_thread(_do_torrent_search)

    if not releases:
        await callback.message.edit_text(
            "No releases found on Rutracker. Try another title."
        )
        return

    parsed_releases = []
    for r in releases:
        parsed = parse_release_name(r["title"])
        r.update(parsed)
        parsed_releases.append(r)

    session["releases"] = parsed_releases
    _set_session(callback.from_user.id, session)

    await state.set_state(Search.selecting_release)

    keyboard = get_releases_keyboard(parsed_releases)
    await callback.message.edit_text(
        f"📦 Found {len(parsed_releases)} releases for '<b>{sanitize_filename(search_query)}</b>':\n\n"
        f"Select a release:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("release_"), Search.selecting_release)
async def handle_select_release(callback: CallbackQuery, state: FSMContext, bot: Bot):
    release_id = int(callback.data.split("_")[1])
    session = _get_session(callback.from_user.id)
    if not session:
        await callback.answer("Session expired.")
        return

    releases = session.get("releases", [])
    release = next((r for r in releases if r["id"] == release_id), None)
    if not release:
        await callback.answer("Invalid selection.")
        return

    session["selected_release"] = release
    _set_session(callback.from_user.id, session)

    voiceovers = list(set(r["voiceover"] for r in releases))
    if len(voiceovers) > 1:
        await state.set_state(Search.selecting_voiceover)
        keyboard = get_voiceover_keyboard(sorted(voiceovers))
        await callback.message.edit_text(
            f"Selected: <b>{sanitize_filename(release['title'][:50])}</b>\n\n"
            f"Choose voiceover:",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        await callback.answer()
    else:
        session["voiceover"] = voiceovers[0] if voiceovers else "original"
        _set_session(callback.from_user.id, session)
        await _ask_quality(callback, state, bot, session)


@router.callback_query(F.data.startswith("voiceover_"), Search.selecting_voiceover)
async def handle_select_voiceover(callback: CallbackQuery, state: FSMContext, bot: Bot):
    voiceover = callback.data.split("_", 1)[1]
    session = _get_session(callback.from_user.id)
    if not session:
        await callback.answer("Session expired.")
        return

    session["voiceover"] = voiceover
    _set_session(callback.from_user.id, session)

    await callback.answer()
    await _ask_quality(callback, state, bot, session)


async def _ask_quality(callback, state, bot, session):
    release = session.get("selected_release", {})
    quality = release.get("quality", "1080p")

    session["quality"] = quality
    _set_session(callback.from_user.id, session)

    await state.set_state(Search.selecting_subtitles)

    keyboard = get_subtitle_keyboard(["eng", "rus", "ukr", "fra", "deu", "spa"])
    await callback.message.edit_text(
        f"✅ <b>{sanitize_filename(release['title'][:50])}</b>\n"
        f"Quality: {quality}\n"
        f"Voiceover: {session.get('voiceover', 'original')}\n\n"
        f"Add subtitles? (burned into video)",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("subtitle_"), Search.selecting_subtitles)
async def handle_select_subtitles(callback: CallbackQuery, state: FSMContext, bot: Bot):
    lang = callback.data.split("_", 1)[1]
    session = _get_session(callback.from_user.id)
    if not session:
        await callback.answer("Session expired.")
        return

    session["subtitles"] = lang if lang != "none" else None
    _set_session(callback.from_user.id, session)

    await callback.message.edit_text(
        f"🚀 Starting download...\n"
        f"Subtitles: {'None' if lang == 'none' else lang}"
    )
    await callback.answer()

    await state.set_state(Search.downloading)

    user_dir = os.path.join(DOWNLOAD_DIR, str(callback.from_user.id))
    os.makedirs(user_dir, exist_ok=True)

    dl_ctx = DownloadContext()
    active_downloads[callback.from_user.id] = dl_ctx

    release = session.get("selected_release", {})
    magnet = await asyncio.to_thread(lambda: None)

    def _get_magnet():
        from services.torrent import get_magnet
        return get_magnet(release["id"])

    magnet = await asyncio.to_thread(_get_magnet)
    if not magnet:
        await callback.message.edit_text("Failed to get download link. Try another release.")
        cleanup_user_session(user_dir)
        active_downloads.pop(callback.from_user.id, None)
        await state.clear()
        return

    def _progress_cb(progress, speed, downloaded, remaining, eta, total):
        speed_str = format_file_size(int(speed)) + "/s"
        eta_str = format_eta(eta)
        text = (
            f"📥 Downloading: {progress:.1f}%\n"
            f"Speed: {speed_str}\n"
            f"Total: {format_file_size(total)}\n"
            f"Remaining: {format_file_size(remaining)}\n"
            f"ETA: {eta_str}"
        )
        asyncio.run_coroutine_threadsafe(
            safe_edit_text(bot, callback.message.chat.id, callback.message.message_id, text),
            asyncio.get_event_loop(),
        )

    filepath = await download_torrent(
        magnet, user_dir, _progress_cb, dl_ctx,
    )

    active_downloads.pop(callback.from_user.id, None)

    if not filepath or not os.path.exists(filepath):
        await callback.message.edit_text("Download failed. Try again.")
        cleanup_user_session(user_dir)
        await state.clear()
        return

    if session.get("subtitles"):
        await _burn_subtitles(callback, state, bot, session, filepath, user_dir)
    else:
        await _send_video(callback, state, bot, session, filepath, user_dir)


async def _burn_subtitles(callback, state, bot, session, filepath, user_dir):
    lang = session.get("subtitles")
    imdb_id = session.get("imdb_id")
    title = session.get("title", "")

    await callback.message.edit_text("🔍 Searching subtitles...")

    def _search_subs():
        return search_subtitles(imdb_id=imdb_id, query=title, languages=[lang])

    subs = await asyncio.to_thread(_search_subs)

    if not subs:
        await callback.message.edit_text(
            "Subtitles not found. Sending video without subtitles."
        )
        await _send_video(callback, state, bot, session, filepath, user_dir)
        return

    sub_file = subs[0]
    sub_path = os.path.join(user_dir, f"subtitles_{lang}.srt")

    await callback.message.edit_text("📥 Downloading subtitles...")

    def _dl_sub():
        return download_subtitle(str(sub_file["file_id"]), sub_path)

    success = await asyncio.to_thread(_dl_sub)
    if not success or not os.path.exists(sub_path):
        await callback.message.edit_text(
            "Failed to download subtitles. Sending video without subtitles."
        )
        await _send_video(callback, state, bot, session, filepath, user_dir)
        return

    await callback.message.edit_text("🔥 Burning subtitles into video...\nThis may take a while for long videos.")

    output_path = os.path.join(user_dir, "video_with_subs.mp4")

    def _progress_cb(percent, speed, current_time, total_duration, current_size, input_size):
        remaining_time = ""
        if speed > 0 and total_duration:
            remaining_seconds = (total_duration - current_time) / speed
            remaining_time = f"\nRemaining: {format_eta(remaining_seconds)}"

        text = (
            f"🔥 Burning subtitles: {percent}%\n"
            f"Speed: {speed:.2f}x\n"
            f"Output: {format_file_size(current_size)}{remaining_time}"
        )
        asyncio.run_coroutine_threadsafe(
            safe_edit_text(bot, callback.message.chat.id, callback.message.message_id, text),
            asyncio.get_event_loop(),
        )

    def _do_burn():
        return burn_subtitles(filepath, sub_path, output_path, SUBTITLE_FONT_SIZE, _progress_cb)

    result = await asyncio.to_thread(_do_burn)

    if result and os.path.exists(output_path):
        os.remove(filepath)
        os.remove(sub_path)
        await _send_video(callback, state, bot, session, output_path, user_dir)
    else:
        await callback.message.edit_text(
            "Subtitle burn-in failed. Sending original video."
        )
        await _send_video(callback, state, bot, session, filepath, user_dir)


async def _send_video(callback, state, bot, session, filepath, user_dir):
    files_to_send = split_video(filepath, user_dir)
    total = len(files_to_send)

    title = session.get("title", "Unknown")
    year = session.get("year", "")
    quality = session.get("quality", "")
    voiceover = session.get("voiceover", "")
    subtitles = session.get("subtitles", "none")

    for i, file_path in enumerate(files_to_send, 1):
        caption = f"🎬 {title}"
        if year:
            caption += f" ({year})"
        if total > 1:
            caption += f"\nPart {i}/{total}"
        caption += f"\nQuality: {quality} | Voiceover: {voiceover}"
        if subtitles and subtitles != "none":
            caption += f"\nSubtitles: {subtitles}"

        file_size = os.path.getsize(file_path)
        caption += f"\nSize: {format_file_size(file_size)}"

        progress_msg = await callback.message.answer(
            f"📤 Uploading{' part ' + str(i) + '/' + str(total) if total > 1 else ''}...\nSize: {format_file_size(file_size)}"
        )

        stop_event = asyncio.Event()
        tracker_task = asyncio.create_task(
            _upload_progress_tracker(
                bot, progress_msg.chat.id, progress_msg.message_id,
                file_size, stop_event,
                part_num=i if total > 1 else None,
                total_parts=total if total > 1 else None,
            )
        )

        try:
            video_file = FSInputFile(file_path)
            video_info = get_video_info(file_path)

            await callback.message.answer_video(
                video=video_file,
                caption=caption,
                supports_streaming=True,
                width=video_info.get("width"),
                height=video_info.get("height"),
            )

            stop_event.set()
            tracker_task.cancel()
            try:
                await tracker_task
            except asyncio.CancelledError:
                pass

            await progress_msg.delete()

        except Exception as e:
            stop_event.set()
            tracker_task.cancel()
            try:
                await tracker_task
            except asyncio.CancelledError:
                pass
            logger.error(f"Failed to send video: {e}")
            await callback.message.answer("Failed to send video. Try again.")

    await add_history(
        callback.from_user.id, title, year,
        session.get("media_type", "movie"),
        quality, voiceover, subtitles or "none",
    )
    await callback.message.answer("✅ Done! Send another title to search.")

    cleanup_user_session(user_dir)
    await state.clear()


async def _upload_progress_tracker(
    bot: Bot, chat_id: int, message_id: int,
    file_size: int, stop_event: asyncio.Event,
    part_num: int = None, total_parts: int = None,
):
    start_time = time.time()
    last_update = 0

    try:
        while not stop_event.is_set():
            now = time.time()
            if now - last_update < 2:
                await asyncio.sleep(0.5)
                continue

            last_update = now
            elapsed = now - start_time

            part_info = f"Part {part_num}/{total_parts} " if total_parts and total_parts > 1 else ""
            total_str = format_file_size(file_size)

            speed_str = "calculating..."
            eta_str = "calculating..."
            percent_str = "0%"

            if elapsed > 3:
                speed = file_size / elapsed if elapsed > 0 else 0
                speed_str = f"{format_file_size(int(speed))}/s"

                if speed > 0:
                    eta_seconds = file_size / speed
                    eta_str = format_eta(eta_seconds)

                uploaded = min(file_size, int(speed * elapsed))
                percent = int((uploaded / file_size) * 100) if file_size > 0 else 0
                percent_str = f"{percent}%"

            text = (
                f"{part_info}📤 Uploading to Telegram...\n"
                f"Progress: {percent_str}\n"
                f"Total: {total_str}\n"
                f"Speed: {speed_str}\n"
                f"ETA: {eta_str}"
            )

            await safe_edit_text(bot, chat_id, message_id, text)
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    dl_ctx = active_downloads.pop(user_id, None)
    if dl_ctx:
        dl_ctx.cancel()

    _clear_session(user_id)
    await state.clear()
    await callback.message.edit_text("❌ Cancelled. Send a new title to search.")
    await callback.answer()
