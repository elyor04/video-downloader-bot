from aiogram import Bot, Dispatcher
from aiogram.client.telegram import TelegramAPIServer
from aiogram.client.session.aiohttp import AiohttpSession

from bot.config import BOT_TOKEN, API_SERVER_URL
from bot.handlers import register_handlers
from bot.database import init_db

api_server = TelegramAPIServer.from_base(API_SERVER_URL)

bot = Bot(BOT_TOKEN, session=AiohttpSession(api=api_server))
dp = Dispatcher()

register_handlers(dp)
init_db()
