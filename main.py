import logging
import os
import shutil
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    InputFile,
)
from yt_dlp import YoutubeDL
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

API_TOKEN = "6687387133:AAEv3POxdGC8cqLStkILKCYqmLiKbzaiB-A"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())


class DownloadState(StatesGroup):
    url = State()
    download_type = State()
    desired_format = State()
    convert_to = State()


available_formats = {}


@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    await message.reply("Welcome! Send /download to start downloading a video.")


@dp.message_handler(commands=["download"])
async def download_init(message: types.Message):
    await DownloadState.url.set()
    await message.reply("Please enter the video URL:")


@dp.message_handler(state=DownloadState.url)
async def process_url(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["url"] = message.text
    await DownloadState.next()

    download_type_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    download_type_keyboard.add(KeyboardButton("video"), KeyboardButton("audio"))

    await message.reply(
        "Please select the download type:", reply_markup=download_type_keyboard
    )


@dp.message_handler(state=DownloadState.download_type)
async def process_download_type(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["download_type"] = message.text.lower()
    await DownloadState.next()
    url = data["url"]
    download_type = data["download_type"]

    formats = await fetch_formats(message, url, download_type)
    available_formats[message.from_user.id] = formats

    format_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    for format_item in formats[download_type]:
        format_keyboard.add(KeyboardButton(format_item))

    await message.reply(
        f"Please select the desired format:", reply_markup=format_keyboard
    )


@dp.message_handler(state=DownloadState.desired_format)
async def process_desired_format(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["desired_format"] = message.text
    await DownloadState.next()

    convert_to_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    convert_to_keyboard.add(
        KeyboardButton("original"), KeyboardButton("mp4"), KeyboardButton("mkv")
    )
    convert_to_keyboard.add(
        KeyboardButton("webm"),
        KeyboardButton("mp3"),
        KeyboardButton("m4a"),
        KeyboardButton("wav"),
    )

    await message.reply(
        "Please select the conversion format:", reply_markup=convert_to_keyboard
    )


@dp.message_handler(state=DownloadState.convert_to)
async def process_convert_to(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["convert_to"] = message.text

    await state.finish()
    url = data["url"]
    download_type = data["download_type"]
    desired_format = data["desired_format"]
    convert_to = data["convert_to"]
    output_path = "downloads"
    file_name = "%(title)s"

    if not os.path.exists(output_path):
        os.makedirs(output_path)

    await download(
        message, url, download_type, desired_format, output_path, file_name, convert_to
    )


async def fetch_formats(message, url, download_type):
    formats = {"video": [], "audio": []}
    try:
        with YoutubeDL() as ydl:
            info = ydl.extract_info(url, download=False)

            for f in info.get("formats", []):
                if f["audio_ext"] != "none":
                    formats["audio"].append(f["ext"])
                elif f["video_ext"] != "none":
                    formats["video"].append((f["height"], f["ext"]))

            formats["audio"] = sorted(set(formats["audio"]), reverse=True)
            formats["video"] = [
                f"{f[0]}p {f[1]}" for f in sorted(set(formats["video"]), reverse=True)
            ]

            if not formats[download_type]:
                await bot.send_message(message.chat.id, "No format found.")

    except Exception as e:
        await bot.send_message(message.chat.id, f"Error occurred: {e}")
    return formats


async def download(
    message, url, download_type, desired_format, output_path, file_name, convert_to
):
    ffmpeg_location = shutil.which("ffmpeg")
    if not ffmpeg_location:
        await bot.send_message(
            message.chat.id,
            "FFmpeg is not installed. Please install FFmpeg to proceed.",
        )
        return

    ydl_opts = {
        "format": get_format(
            download_type, desired_format, available_formats[message.from_user.id]
        ),
        "outtmpl": os.path.join(output_path, f"{file_name}.%(ext)s"),
        "ffmpeg_location": ffmpeg_location,
    }

    if convert_to != "original":
        ydl_opts["postprocessors"] = [get_postprocessor(download_type, convert_to)]

    msg = await bot.send_message(
        message.chat.id, "⏳", reply_markup=ReplyKeyboardRemove()
    )
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        for file in os.listdir(output_path):
            file_path = os.path.join(output_path, file)
            if download_type == "video":
                await bot.send_video(message.chat.id, InputFile(file_path))
            else:
                await bot.send_audio(message.chat.id, InputFile(file_path))
            os.remove(file_path)

        await bot.send_message(message.chat.id, "Download completed successfully.")
    except Exception as e:
        await bot.send_message(message.chat.id, f"Error occurred: {e}")
    await bot.delete_message(msg.chat.id, msg.message_id)


def get_format(download_type, desired_format, available_formats):
    if download_type == "audio":
        return f"bestaudio[ext={desired_format}]"

    q, f = desired_format.split()
    if not available_formats["audio"]:
        return f"best[height={q[:-1]}][ext={f}]"

    if f in available_formats["audio"]:
        audio = f
    elif "m4a" in available_formats["audio"]:
        audio = "m4a"
    else:
        audio = None

    if not audio:
        return f"bestvideo[height={q[:-1]}][ext={f}]+bestaudio"
    return f"bestvideo[height={q[:-1]}][ext={f}]+bestaudio[ext={audio}]/best"


def get_postprocessor(download_type, convert_to):
    if download_type == "audio":
        return {
            "key": "FFmpegExtractAudio",
            "preferredcodec": convert_to,
        }
    return {
        "key": "FFmpegVideoConvertor",
        "preferedformat": convert_to,
    }


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
