from aiogram.fsm.state import State, StatesGroup


class VideoDownload(StatesGroup):
    waiting_for_url = State()
    selecting_quality = State()
    downloading = State()


class PlaylistDownload(StatesGroup):
    selecting_video = State()
    selecting_quality = State()
    downloading = State()
