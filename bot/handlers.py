import os
import shutil

from aiogram import Dispatcher
from aiogram.types import (
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    FSInputFile,
    Message,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.states import DownloadState
from bot.utils import fetch_formats, download_media
from bot.database import cr, db


def register_handlers(dp: Dispatcher):
    dp.message.register(send_welcome, Command("start"))
    dp.message.register(download_init, Command("download"))
    dp.message.register(download_cancel, Command("cancel"))
    dp.message.register(process_url, DownloadState.url)
    dp.message.register(process_download_type, DownloadState.download_type)
    dp.message.register(process_desired_format, DownloadState.desired_format)
    dp.message.register(process_convert_to, DownloadState.convert_to)


async def send_welcome(message: Message):
    await message.reply(
        "Welcome to Video Downloader bot!\nSend /download to start downloading.\nSend /cancel to cancel at any time."
    )


async def download_init(message: Message, state: FSMContext):
    await state.set_state(DownloadState.url)
    await message.reply("Please enter the video URL:")


async def download_cancel(message: Message, state: FSMContext):
    if (await state.get_state()) is not None:
        await state.set_state(None)
        await message.reply(
            "Download progress has been canceled.", reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.reply("Nothing to cancel.")


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


async def process_download_type(message: Message, state: FSMContext):
    await state.update_data(download_type=message.text)
    data = await state.get_data()
    url = data["url"]
    download_type = data["download_type"]

    formats = fetch_formats(url, download_type)
    if formats.get("message"):
        await state.set_state(None)
        await message.answer(formats.get("message"), reply_markup=ReplyKeyboardRemove())
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


async def process_desired_format(message: Message, state: FSMContext):
    await state.update_data(desired_format=message.text)
    await state.set_state(DownloadState.convert_to)

    convert_to_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="original")],
            [KeyboardButton(text="mp4"), KeyboardButton(text="mp3")],
            [KeyboardButton(text="avi"), KeyboardButton(text="wav")],
        ],
        resize_keyboard=True,
    )

    await message.reply(
        "Please select the conversion format:", reply_markup=convert_to_keyboard
    )


async def process_convert_to(message: Message, state: FSMContext):
    await state.update_data(convert_to=message.text)
    data = await state.get_data()
    await state.clear()

    url = data["url"]
    download_type = data["download_type"]
    desired_format = data["desired_format"]
    available_formats = data["available_formats"]
    convert_to = data["convert_to"]
    output_path = f"downloads/{message.from_user.id}"
    file_name = "%(title)s"

    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path)

    media_id = available_formats["media_id"]
    desired_format_split = desired_format.split()

    if convert_to in {"original", desired_format_split[-1]}:
        media_format = desired_format
    elif (convert_to in {"mp3", "wav"}) or (len(desired_format_split) == 1):
        media_format = convert_to
    else:
        media_format = f"{desired_format_split[0]} {convert_to}"

    sql = "SELECT file_id FROM downloads \
        WHERE media_id = ? \
        AND media_format = ?"
    cr.execute(sql, (media_id, media_format))

    if len(media_format.split()) == 2:
        send_media = message.answer_video
    else:
        send_media = message.answer_audio

    file_id = cr.fetchone()
    if file_id:
        await send_media(
            file_id[0],
            caption="Downloaded by @video_downloader_2024_bot",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    msg = await message.answer("⏳", reply_markup=ReplyKeyboardRemove())

    error = download_media(
        url,
        download_type,
        desired_format,
        available_formats,
        output_path,
        file_name,
        convert_to,
    )

    if error:
        await message.answer(error)
        await msg.delete()
        return

    file = os.listdir(output_path)[0]
    file_path = os.path.join(output_path, file)

    result = await send_media(
        FSInputFile(file_path), caption="Downloaded by @video_downloader_2024_bot"
    )
    file_id = (result.video or result.audio or result.document).file_id

    sql = "INSERT INTO downloads \
        (file_id, media_id, media_format) \
        VALUES (?, ?, ?)"
    cr.execute(sql, (file_id, media_id, media_format))

    db.commit()
    await msg.delete()
