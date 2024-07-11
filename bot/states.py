from aiogram.fsm.state import State, StatesGroup


class DownloadState(StatesGroup):
    url = State()
    download_type = State()
    desired_format = State()
    convert_to = State()
    available_formats = State()
