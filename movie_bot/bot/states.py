from aiogram.fsm.state import State, StatesGroup


class Search(StatesGroup):
    waiting_for_query = State()
    selecting_result = State()
    selecting_release = State()
    selecting_quality = State()
    selecting_voiceover = State()
    selecting_subtitles = State()
    selecting_season = State()
    selecting_episode = State()
    downloading = State()
    burning_subtitles = State()
