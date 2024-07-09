import os
import sys
import shutil
import logging
import asyncio
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.types import (
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    FSInputFile,
    Message,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from aiogram.client.telegram import TelegramAPIServer
from aiogram.client.session.aiohttp import AiohttpSession
from yt_dlp import YoutubeDL

TOKEN = "7276293026:AAFTcX0tlhNYpqW6FetLYKlrpgPn04qwmBY"
api_server = TelegramAPIServer.from_base("http://telegram-bot-api:8081")

bot = Bot(TOKEN, session=AiohttpSession(api=api_server))
dp = Dispatcher()

db = sqlite3.connect("video-downloader.db")
cr = db.cursor()

cr.execute(
    "CREATE TABLE IF NOT EXISTS downloads \
    (file_id VARCHAR(100), \
    url VARCHAR(200), \
    download_type VARCHAR(10), \
    desired_format VARCHAR(30), \
    convert_to VARCHAR(10))"
)


class DownloadState(StatesGroup):
    url = State()
    download_type = State()
    desired_format = State()
    convert_to = State()
    available_formats = State()


@dp.message(Command("start"))
async def send_welcome(message: Message):
    await message.reply(
        "Welcome to Video Downloader bot!\nSend /download to start downloading.\nSend /cancel to cancel at any time."
    )


@dp.message(Command("download"))
async def download_init(message: Message, state: FSMContext):
    await state.set_state(DownloadState.url)
    await message.reply("Please enter the video URL:")


@dp.message(Command("cancel"))
async def download_cancel(message: Message, state: FSMContext):
    if (await state.get_state()) is not None:
        await state.set_state(None)
        await message.reply(
            "Download progress has been canceled.", reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.reply("Nothing to cancel.")


@dp.message(DownloadState.url)
async def process_url(message: Message, state: FSMContext):
    await state.update_data(url=message.text)
    await state.set_state(DownloadState.download_type)

    download_type_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="video"), KeyboardButton(text="audio")]],
        resize_keyboard=True,
    )

    await message.reply(
        "Please select the download type:", reply_markup=download_type_keyboard
    )


@dp.message(DownloadState.download_type)
async def process_download_type(message: Message, state: FSMContext):
    await state.update_data(download_type=message.text)
    data = await state.get_data()
    url = data["url"]
    download_type = data["download_type"]

    formats = await fetch_formats(message, url, download_type)
    if formats is None:
        await state.set_state(None)
        return
    await state.update_data(available_formats=formats)
    await state.set_state(DownloadState.desired_format)

    format_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=format_item)] for format_item in formats[download_type]
        ],
        resize_keyboard=True,
    )

    await message.reply(
        f"Please select the desired format:", reply_markup=format_keyboard
    )


@dp.message(DownloadState.desired_format)
async def process_desired_format(message: Message, state: FSMContext):
    await state.update_data(desired_format=message.text)
    await state.set_state(DownloadState.convert_to)

    convert_to_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="original"),
                KeyboardButton(text="mp4"),
                KeyboardButton(text="mp3"),
            ],
            [
                KeyboardButton(text="mkv"),
                KeyboardButton(text="wav"),
                KeyboardButton(text="webm"),
                KeyboardButton(text="m4a"),
            ],
        ],
        resize_keyboard=True,
    )

    await message.reply(
        "Please select the conversion format:", reply_markup=convert_to_keyboard
    )


@dp.message(DownloadState.convert_to)
async def process_convert_to(message: Message, state: FSMContext):
    await state.update_data(convert_to=message.text)

    data = await state.get_data()
    await state.clear()
    url = data["url"]
    download_type = data["download_type"]
    desired_format = data["desired_format"]
    available_formats = data["available_formats"]
    convert_to = data["convert_to"]
    output_path = str(message.from_user.id)
    file_name = "%(title)s"

    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path)

    await download(
        message,
        url,
        download_type,
        desired_format,
        available_formats,
        output_path,
        file_name,
        convert_to,
    )


async def fetch_formats(message, url, download_type):
    try:
        with YoutubeDL({"cookiefile": "cookies.txt"}) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = {"video": [], "audio": []}

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
                await bot.send_message(
                    message.chat.id,
                    "No format found.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return None
            return formats

    except Exception as e:
        await bot.send_message(
            message.chat.id, f"Error occurred: {e}", reply_markup=ReplyKeyboardRemove()
        )
        return None


async def download(
    message,
    url,
    download_type,
    desired_format,
    available_formats,
    output_path,
    file_name,
    convert_to,
):
    ffmpeg_location = shutil.which("ffmpeg")
    if not ffmpeg_location:
        await bot.send_message(
            message.chat.id,
            "FFmpeg is not installed. Please install FFmpeg to proceed.",
        )
        return

    sql = "SELECT file_id FROM downloads \
        WHERE url = ? \
        AND download_type = ? \
        AND desired_format = ? \
        AND convert_to = ?"
    val = (url, download_type, desired_format, convert_to)
    cr.execute(sql, val)

    file_id = cr.fetchone()
    if file_id is not None:
        await bot.send_document(
            message.chat.id, file_id[0], reply_markup=ReplyKeyboardRemove()
        )
        return

    ydl_opts = {
        "format": get_format(download_type, desired_format, available_formats),
        "outtmpl": os.path.join(output_path, f"{file_name}.%(ext)s"),
        "ffmpeg_location": ffmpeg_location,
        "cookiefile": "cookies.txt",
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

            result = await bot.send_document(message.chat.id, FSInputFile(file_path))
            file_id = (result.document or result.video or result.audio).file_id

            sql = "INSERT INTO downloads \
                (file_id, url, download_type, desired_format, convert_to) \
                VALUES (?, ?, ?, ?, ?)"
            val = (file_id, url, download_type, desired_format, convert_to)

            cr.execute(sql, val)
            db.commit()

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
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(dp.start_polling(bot))
