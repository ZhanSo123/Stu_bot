from aiogram import Dispatcher
from aiogram.types import Message

async def start(message: Message):
    await message.answer("Привет! Я STUbot 🤖")

def register_handlers(dp: Dispatcher):
    dp.message.register(start, commands=["start"])