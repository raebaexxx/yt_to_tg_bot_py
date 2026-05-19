import os
import asyncio
import logging
import time
from typing import Optional
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from bot.states import VideoDownload, PlaylistDownload
from bot.keyboards import (
    get_quality_keyboard,
    get_playlist_keyboard,
    get_device_keyboard,
    get_cancel_keyboard,
)
from services.youtube import (
    get_video_info,
    get_playlist_videos,
    get_available_qualities,
)
from services.downloader import download_video, download_thumbnail, DownloadContext
from services.splitter import split_video
from utils.helpers import (
    is_youtube_url,
    is_playlist_url,
    format_duration,
    format_file_size,
    sanitize_filename,
)
from utils.cleanup import cleanup_file, cleanup_user_session
from utils.progress import safe_edit_text
from database.models import add_user, add_history
from config import DOWNLOAD_DIR

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
active_downloads: dict[int, DownloadContext] = {}


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


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    await state.clear()
    await message.answer(
        "Welcome! Send me a YouTube link and I'll let you choose the quality.\n\n"
        "Supported:\n"
        "- Single videos\n"
        "- Playlists\n"
        "- Shorts\n\n"
        "Just paste the link!"
    )


@router.message(F.text)
async def handle_url(message: Message, state: FSMContext):
    url = message.text.strip()

    if not is_youtube_url(url):
        await message.answer(
            "This doesn't look like a valid YouTube link. Please send a valid URL."
        )
        return

    await add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )

    status_msg = await message.answer("Getting video info...")

    if is_playlist_url(url):
        await _handle_playlist(message, state, url, status_msg)
    else:
        await _handle_single_video(message, state, url, status_msg)


async def _handle_single_video(
    message: Message, state: FSMContext, url: str, status_msg: Message
):
    info = get_video_info(url)
    if not info:
        await status_msg.edit_text(
            "Failed to get video info. The video might be private or unavailable."
        )
        return

    title = info.get("title", "Unknown")
    duration = info.get("duration", 0)

    available = get_available_qualities(info)

    _set_session(message.from_user.id, {
        "url": url,
        "title": title,
        "info": info,
    })

    await state.set_state(VideoDownload.selecting_quality)

    text = (
        f"<b>{sanitize_filename(title)}</b>\n\n"
        f"Duration: {format_duration(duration)}\n"
        f"Choose quality:"
    )

    keyboard = get_quality_keyboard(available, url)
    await status_msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


async def _handle_playlist(
    message: Message, state: FSMContext, url: str, status_msg: Message
):
    await status_msg.edit_text("Getting playlist info...")

    playlist_info = get_video_info(url)
    if not playlist_info:
        await status_msg.edit_text(
            "Failed to get playlist info. The playlist might be private."
        )
        return

    videos = get_playlist_videos(url)
    if not videos:
        await status_msg.edit_text("No videos found in this playlist.")
        return

    playlist_title = playlist_info.get("title", "Unknown playlist")

    _set_session(message.from_user.id, {
        "url": url,
        "title": playlist_title,
        "videos": videos,
        "playlist_page": 0,
    })

    await state.set_state(PlaylistDownload.selecting_video)

    text = (
        f"<b>Playlist: {sanitize_filename(playlist_title)}</b>\n\n"
        f"Total videos: {len(videos)}\n"
        f"Select a video or download all:"
    )

    keyboard = get_playlist_keyboard(videos, 0)
    await status_msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("quality_"), VideoDownload.selecting_quality)
async def handle_quality_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    quality = callback.data.split("_")[1]
    session = _get_session(callback.from_user.id)

    if not session:
        await callback.answer("Session expired. Send the link again.")
        return

    if quality == "4k":
        session["pending_quality"] = quality
        _set_session(callback.from_user.id, session)
        await state.set_state(VideoDownload.selecting_device)

        await callback.message.edit_text(
            f"<b>{sanitize_filename(session['title'])}</b>\n\n"
            f"4K video detected. Choose your device for optimal playback:\n\n"
            f"• <b>PC / Android</b> — instant, no conversion (AV1 codec)\n"
            f"• <b>iPhone / iOS</b> — converted to HEVC 1080p (~10-20 min)",
            reply_markup=get_device_keyboard(session["url"], quality),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"Selected quality: {quality}\nStarting download..."
    )
    await callback.answer()

    await state.set_state(VideoDownload.downloading)

    user_dir = os.path.join(DOWNLOAD_DIR, str(callback.from_user.id))
    os.makedirs(user_dir, exist_ok=True)

    dl_ctx = DownloadContext()
    active_downloads[callback.from_user.id] = dl_ctx

    filepath = await download_video(
        session["url"],
        quality,
        bot=bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        output_dir=user_dir,
        cancel_ctx=dl_ctx,
    )

    active_downloads.pop(callback.from_user.id, None)

    if not filepath or not os.path.exists(filepath[0]):
        await callback.message.edit_text("Download failed. Try again later.")
        cleanup_user_session(user_dir)
        await state.clear()
        return

    filepath, width, height = filepath
    file_size = os.path.getsize(filepath)
    await callback.message.edit_text(
        f"Download complete! Uploading to Telegram...\nSize: {format_file_size(file_size)}"
    )

    try:
        await _send_video_files(callback.message, filepath, session["title"], session["url"], quality, bot, width, height)
    except Exception as e:
        logger.error(f"Failed to send video: {e}")
        await callback.message.answer("Failed to send video. Try again.")
    finally:
        cleanup_user_session(user_dir)
        await state.clear()


@router.callback_query(F.data.startswith("device_"), VideoDownload.selecting_device)
async def handle_device_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split("_")
    device = parts[1]
    quality = parts[2]
    session = _get_session(callback.from_user.id)

    if not session:
        await callback.answer("Session expired. Send the link again.")
        return

    await callback.message.edit_text(
        f"Selected: {quality} for {'iPhone' if device == 'ios' else 'PC/Android'}\nStarting download..."
    )
    await callback.answer()

    await state.set_state(VideoDownload.downloading)

    user_dir = os.path.join(DOWNLOAD_DIR, str(callback.from_user.id))
    os.makedirs(user_dir, exist_ok=True)

    dl_ctx = DownloadContext()
    active_downloads[callback.from_user.id] = dl_ctx

    filepath = await download_video(
        session["url"],
        quality,
        bot=bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        output_dir=user_dir,
        cancel_ctx=dl_ctx,
        is_ios=(device == "ios"),
    )

    active_downloads.pop(callback.from_user.id, None)

    if not filepath or not os.path.exists(filepath[0]):
        await callback.message.edit_text("Download failed. Try again later.")
        cleanup_user_session(user_dir)
        await state.clear()
        return

    filepath, width, height = filepath
    file_size = os.path.getsize(filepath)
    await callback.message.edit_text(
        f"Download complete! Uploading to Telegram...\nSize: {format_file_size(file_size)}"
    )

    try:
        await _send_video_files(callback.message, filepath, session["title"], session["url"], quality, bot, width, height)
    except Exception as e:
        logger.error(f"Failed to send video: {e}")
        await callback.message.answer("Failed to send video. Try again.")
    finally:
        cleanup_user_session(user_dir)
        await state.clear()


async def _upload_progress_tracker(
    bot: Bot,
    chat_id: int,
    message_id: int,
    file_size: int,
    stop_event: asyncio.Event,
    part_num: int = None,
    total_parts: int = None,
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
            text = (
                f"{part_info}Uploading to Telegram...\n"
                f"Size: {format_file_size(file_size)}\n"
                f"Elapsed: {int(elapsed)}s"
            )

            await safe_edit_text(bot, chat_id, message_id, text)
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def _send_video_files(
    message: Message, filepath: str, title: str, url: str, quality: str, bot: Bot, width: int = None, height: int = None
):
    user_dir = os.path.dirname(filepath)
    files_to_send = split_video(filepath, user_dir)

    thumb_path = None
    try:
        thumb_path = download_thumbnail(url, user_dir)
    except Exception:
        pass

    total = len(files_to_send)
    for i, file_path in enumerate(files_to_send, 1):
        caption = f"{title}"
        if total > 1:
            caption += f"\nPart {i}/{total}"

        file_size = os.path.getsize(file_path)
        caption += f"\nSize: {format_file_size(file_size)}"

        progress_msg = await message.answer(
            f"Uploading{' part ' + str(i) + '/' + str(total) if total > 1 else ''}...\nSize: {format_file_size(file_size)}"
        )

        stop_event = asyncio.Event()
        tracker_task = asyncio.create_task(
            _upload_progress_tracker(
                bot,
                progress_msg.chat.id,
                progress_msg.message_id,
                file_size,
                stop_event,
                part_num=i if total > 1 else None,
                total_parts=total if total > 1 else None,
            )
        )

        try:
            video_file = FSInputFile(file_path)
            thumb_file = FSInputFile(thumb_path) if thumb_path and os.path.exists(thumb_path) else None

            await message.answer_video(
                video=video_file,
                caption=caption,
                thumbnail=thumb_file,
                supports_streaming=True,
                width=width,
                height=height,
            )

            stop_event.set()
            tracker_task.cancel()
            try:
                await tracker_task
            except asyncio.CancelledError:
                pass

            await progress_msg.delete()

        except Exception:
            stop_event.set()
            tracker_task.cancel()
            try:
                await tracker_task
            except asyncio.CancelledError:
                pass
            raise

    await add_history(message.from_user.id, url, title, quality)
    await message.answer("Done! Send another link if you want.")

    if thumb_path and os.path.exists(thumb_path):
        cleanup_file(thumb_path)


@router.callback_query(F.data.startswith("pl_video_"))
async def handle_playlist_video_select(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[2])
    session = _get_session(callback.from_user.id)

    if not session or "videos" not in session:
        await callback.answer("Session expired.")
        return

    videos = session["videos"]
    if idx >= len(videos):
        await callback.answer("Invalid selection.")
        return

    video = videos[idx]
    video_url = video.get("url") or video.get("webpage_url")

    if not video_url:
        await callback.answer("Cannot get video URL.")
        return

    session["selected_video_url"] = video_url
    session["selected_video_title"] = video.get("title", "Unknown")

    await callback.message.edit_text("Getting video info...")

    info = get_video_info(video_url)
    if not info:
        await callback.message.edit_text("Failed to get video info.")
        return

    available = get_available_qualities(info)
    session["info"] = info

    await state.set_state(PlaylistDownload.selecting_quality)

    text = (
        f"<b>{sanitize_filename(video.get('title', 'Unknown'))}</b>\n\n"
        f"Choose quality:"
    )

    keyboard = get_quality_keyboard(available, video_url)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("pl_page_"))
async def handle_playlist_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[2])
    session = _get_session(callback.from_user.id)

    if not session or "videos" not in session:
        await callback.answer("Session expired.")
        return

    session["playlist_page"] = page
    videos = session["videos"]
    playlist_title = session.get("title", "Playlist")

    text = (
        f"<b>Playlist: {sanitize_filename(playlist_title)}</b>\n\n"
        f"Total videos: {len(videos)}\n"
        f"Select a video or download all:"
    )

    keyboard = get_playlist_keyboard(videos, page)
    await callback.message.edit_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "pl_download_all")
async def handle_download_all(callback: CallbackQuery, state: FSMContext, bot: Bot):
    session = _get_session(callback.from_user.id)

    if not session or "videos" not in session:
        await callback.answer("Session expired.")
        return

    videos = session["videos"]
    await callback.message.edit_text(
        f"Downloading all {len(videos)} videos...\nThis may take a while."
    )
    await callback.answer()

    await state.set_state(PlaylistDownload.downloading)

    user_dir = os.path.join(DOWNLOAD_DIR, str(callback.from_user.id))
    os.makedirs(user_dir, exist_ok=True)

    success_count = 0
    fail_count = 0

    for i, video in enumerate(videos, 1):
        video_url = video.get("url") or video.get("webpage_url")
        if not video_url:
            fail_count += 1
            continue

        video_title = video.get("title", f"Video {i}")
        progress_msg = await callback.message.answer(
            f"Downloading {i}/{len(videos)}: {sanitize_filename(video_title)}"
        )

        info = get_video_info(video_url)
        if not info:
            fail_count += 1
            continue

        available = get_available_qualities(info)
        quality = "720p" if "720p" in available else available[0] if available else "360p"

        dl_ctx = DownloadContext()
        active_downloads[callback.from_user.id] = dl_ctx

        filepath = await download_video(
            video_url,
            quality,
            bot=bot,
            chat_id=progress_msg.chat.id,
            message_id=progress_msg.message_id,
            output_dir=user_dir,
            cancel_ctx=dl_ctx,
        )

        active_downloads.pop(callback.from_user.id, None)

        if filepath and os.path.exists(filepath[0]):
            filepath, width, height = filepath
            file_size = os.path.getsize(filepath)
            await progress_msg.edit_text(
                f"Download complete! Uploading to Telegram...\nSize: {format_file_size(file_size)}"
            )
            try:
                await _send_video_files(
                    callback.message, filepath, video_title, video_url, quality, bot, width, height
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send {video_title}: {e}")
                fail_count += 1
        else:
            fail_count += 1

        cleanup_user_session(user_dir)
        os.makedirs(user_dir, exist_ok=True)

    cleanup_user_session(user_dir)
    await callback.message.answer(
        f"Playlist download complete!\n"
        f"Success: {success_count}\n"
        f"Failed: {fail_count}"
    )
    await state.clear()


@router.callback_query(F.data.startswith("quality_"), PlaylistDownload.selecting_quality)
async def handle_playlist_quality_selection(
    callback: CallbackQuery, state: FSMContext, bot: Bot
):
    quality = callback.data.split("_")[1]
    session = _get_session(callback.from_user.id)

    if not session:
        await callback.answer("Session expired.")
        return

    video_url = session.get("selected_video_url")
    video_title = session.get("selected_video_title", "Unknown")

    if not video_url:
        await callback.answer("No video selected.")
        return

    if quality == "4k":
        session["pending_quality"] = quality
        _set_session(callback.from_user.id, session)
        await state.set_state(PlaylistDownload.selecting_device)

        await callback.message.edit_text(
            f"<b>{sanitize_filename(video_title)}</b>\n\n"
            f"4K video detected. Choose your device for optimal playback:\n\n"
            f"• <b>PC / Android</b> — instant, no conversion (AV1 codec)\n"
            f"• <b>iPhone / iOS</b> — converted to HEVC 1080p (~10-20 min)",
            reply_markup=get_device_keyboard(video_url, quality),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"Selected quality: {quality}\nStarting download..."
    )
    await callback.answer()

    await state.set_state(PlaylistDownload.downloading)

    user_dir = os.path.join(DOWNLOAD_DIR, str(callback.from_user.id))
    os.makedirs(user_dir, exist_ok=True)

    dl_ctx = DownloadContext()
    active_downloads[callback.from_user.id] = dl_ctx

    filepath = await download_video(
        video_url,
        quality,
        bot=bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        output_dir=user_dir,
        cancel_ctx=dl_ctx,
    )

    active_downloads.pop(callback.from_user.id, None)

    if not filepath or not os.path.exists(filepath[0]):
        await callback.message.edit_text("Download failed.")
        cleanup_user_session(user_dir)
        await state.clear()
        return

    filepath, width, height = filepath
    file_size = os.path.getsize(filepath)
    await callback.message.edit_text(
        f"Download complete! Uploading to Telegram...\nSize: {format_file_size(file_size)}"
    )

    try:
        await _send_video_files(
            callback.message, filepath, video_title, video_url, quality, bot, width, height
        )
    except Exception as e:
        logger.error(f"Failed to send video: {e}")
        await callback.message.answer("Failed to send video.")
    finally:
        cleanup_user_session(user_dir)
        await state.clear()


@router.callback_query(F.data.startswith("device_"), PlaylistDownload.selecting_device)
async def handle_playlist_device_selection(
    callback: CallbackQuery, state: FSMContext, bot: Bot
):
    parts = callback.data.split("_")
    device = parts[1]
    quality = parts[2]
    session = _get_session(callback.from_user.id)

    if not session:
        await callback.answer("Session expired.")
        return

    video_url = session.get("selected_video_url")
    video_title = session.get("selected_video_title", "Unknown")

    if not video_url:
        await callback.answer("No video selected.")
        return

    await callback.message.edit_text(
        f"Selected: {quality} for {'iPhone' if device == 'ios' else 'PC/Android'}\nStarting download..."
    )
    await callback.answer()

    await state.set_state(PlaylistDownload.downloading)

    user_dir = os.path.join(DOWNLOAD_DIR, str(callback.from_user.id))
    os.makedirs(user_dir, exist_ok=True)

    dl_ctx = DownloadContext()
    active_downloads[callback.from_user.id] = dl_ctx

    filepath = await download_video(
        video_url,
        quality,
        bot=bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        output_dir=user_dir,
        cancel_ctx=dl_ctx,
        is_ios=(device == "ios"),
    )

    active_downloads.pop(callback.from_user.id, None)

    if not filepath or not os.path.exists(filepath[0]):
        await callback.message.edit_text("Download failed.")
        cleanup_user_session(user_dir)
        await state.clear()
        return

    filepath, width, height = filepath
    file_size = os.path.getsize(filepath)
    await callback.message.edit_text(
        f"Download complete! Uploading to Telegram...\nSize: {format_file_size(file_size)}"
    )

    try:
        await _send_video_files(
            callback.message, filepath, video_title, video_url, quality, bot, width, height
        )
    except Exception as e:
        logger.error(f"Failed to send video: {e}")
        await callback.message.answer("Failed to send video.")
    finally:
        cleanup_user_session(user_dir)
        await state.clear()


@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    dl_ctx = active_downloads.pop(user_id, None)
    if dl_ctx:
        dl_ctx.cancel()

    _clear_session(user_id)
    await state.clear()
    await callback.message.edit_text("Cancelled. Send a new link.")
    await callback.answer()
