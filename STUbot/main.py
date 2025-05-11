import logging
import sqlite3
import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.utils.i18n import gettext as _
from aiogram import types
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

from aiogram import html
from aiogram import BaseMiddleware
from aiogram import flags

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

import matplotlib.pyplot as plt
from io import BytesIO

TOKEN = "7696336002:AAEYLmJ0DyxPm5HT93CWJWN9xJDJ5Nv-BVI"

# --- DATABASE ---
conn = sqlite3.connect('stubot.db')
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS deadlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    subject TEXT,
    task TEXT,
    due_date TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    amount REAL,
    date TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    day TEXT,
    time TEXT,
    subject TEXT
)''')

conn.commit()

# --- DISPATCHER ---
router = Router()
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

main_kb = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
    [KeyboardButton(text="/дедлайны"), KeyboardButton(text="/расписание")],
    [KeyboardButton(text="/расходы"), KeyboardButton(text="/добавить_дедлайн")],
    [KeyboardButton(text="/добавить_пару"), KeyboardButton(text="/добавить_расход")]
])

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer("Привет! Я STUbot — твой многофункциональный помощник студента. Выбери, с чего начнём:", reply_markup=main_kb)

@router.message(F.text == "/добавить_дедлайн")
async def add_deadline(message: Message):
    await message.answer("Введите дедлайн в формате: Предмет | Задание | 2025-05-15", parse_mode=ParseMode.MARKDOWN)

@router.message(lambda msg: '|' in msg.text and '-' in msg.text and len(msg.text.split('|')) == 3)
async def save_deadline(message: Message):
    subject, task, due_date = [s.strip() for s in message.text.split('|')]
    cursor.execute("INSERT INTO deadlines (user_id, subject, task, due_date) VALUES (?, ?, ?, ?)",
                   (message.from_user.id, subject, task, due_date))
    conn.commit()
    await message.answer("✅ Дедлайн сохранён!")

@router.message(F.text == "/дедлайны")
async def show_deadlines(message: Message):
    cursor.execute("SELECT subject, task, due_date FROM deadlines WHERE user_id=? ORDER BY due_date ASC", (message.from_user.id,))
    rows = cursor.fetchall()
    if not rows:
        await message.answer("У тебя пока нет дедлайнов ✍️")
    else:
        text = "📌 Твои дедлайны:\n\n"
        for subject, task, due_date in rows:
            text += f"{due_date}: {subject} — {task}\n"
        await message.answer(text)

@router.message(F.text == "/добавить_расход")
async def add_expense(message: Message):
    await message.answer("Введите расход в формате: Категория | Сумма, например: Еда | 1500")

@router.message(lambda msg: '|' in msg.text and len(msg.text.split('|')) == 2)
async def save_expense(message: Message):
    try:
        category, amount = [s.strip() for s in message.text.split('|')]

        # Проверяем, является ли сумма числом
        if not amount.replace('.', '', 1).isdigit():
            await message.answer("Ошибка: сумма должна быть числовым значением.")
            return

        amount = float(amount)  # Преобразуем сумму в число
        date = datetime.date.today().isoformat()

        cursor.execute("INSERT INTO expenses (user_id, category, amount, date) VALUES (?, ?, ?, ?)",
                       (message.from_user.id, category, amount, date))
        conn.commit()
        await message.answer("✅ Расход сохранён!")
    except Exception as e:
        await message.answer(f"Ошибка при обработке запроса: {e}")

@router.message(F.text == "/расходы")
async def show_expenses(message: Message):
    cursor.execute("SELECT category, amount, date FROM expenses WHERE user_id=? ORDER BY date DESC", (message.from_user.id,))
    rows = cursor.fetchall()
    if not rows:
        await message.answer("У тебя пока нет записанных расходов 💸")
    else:
        text = "💰 Последние расходы:\n\n"
        for category, amount, date in rows[:10]:
            text += f"{date}: {category} — {amount} ₸\n"
        await message.answer(text)

@router.message(F.text == "/добавить_пару")
async def add_class(message: Message):
    await message.answer("Введите пару в формате: День | Время | Предмет, например: Понедельник | 10:00 | История")

@router.message(lambda msg: '|' in msg.text and len(msg.text.split('|')) == 3)
async def save_class(message: Message):
    day, time, subject = [s.strip() for s in message.text.split('|')]
    cursor.execute("INSERT INTO schedule (user_id, day, time, subject) VALUES (?, ?, ?, ?)",
                   (message.from_user.id, day.capitalize(), time, subject))
    conn.commit()
    await message.answer("✅ Пара добавлена в расписание!")

@router.message(F.text == "/расписание")
async def show_schedule(message: Message):
    weekday = datetime.datetime.today().strftime('%A')
    cursor.execute("SELECT time, subject FROM schedule WHERE user_id=? AND day=? ORDER BY time",
                   (message.from_user.id, weekday.capitalize()))
    rows = cursor.fetchall()
    if not rows:
        await message.answer("На сегодня пар нет 🎉")
    else:
        text = f"📚 Расписание на сегодня ({weekday}):\n\n"
        for time, subject in rows:
            text += f"{time} — {subject}\n"
        await message.answer(text)

# --- Напоминания ---
async def send_deadline_reminders():
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    cursor.execute("SELECT subject, task, due_date FROM deadlines")
    rows = cursor.fetchall()

    for subject, task, due_date in rows:
        try:
            deadline_date = datetime.strptime(due_date, "%Y-%m-%d").date()
            if deadline_date == tomorrow:
                await bot.send_message(
                    7334707979,  # 🔁 временно сюда свой ID (или сохраним user_id при команде start)
                    f"📌 Завтра дедлайн по: <b>{subject}</b> — {task}",
                    parse_mode="HTML"
                )
        except Exception as e:
            print("❌ Ошибка при отправке напоминания:", e)

# Планировщик для ежедневных напоминаний
def start_scheduler():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_deadline_reminders, trigger="cron", hour=8)  # ⏰ каждый день в 8:00
    scheduler.start()

# Основной запуск бота
async def main():
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    start_scheduler()  # Запуск планировщика
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

@router.message(F.text == "/график_расходов")
async def send_expenses_chart(message: Message):
    # Извлекаем данные расходов из базы данных
    cursor.execute("SELECT category, SUM(amount) FROM expenses WHERE user_id=? GROUP BY category", (message.from_user.id,))
    rows = cursor.fetchall()

    if not rows:
        await message.answer("У тебя пока нет расходов для отображения на графике 💸")
        return

    # Подготовка данных для диаграммы
    categories = [row[0] for row in rows]
    amounts = [row[1] for row in rows]

    # Создание круговой диаграммы
    fig, ax = plt.subplots()
    ax.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Сделать круг

    # Сохранение графика в буфер
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)

    # Отправка графика пользователю
    await message.answer("📊 Вот твой график расходов по категориям:", file=buf)
    buf.close()

@router.message(F.text.startswith("/поиск_дедлайна"))
async def search_deadline(message: Message):
    subject = message.text[len("/поиск_дедлайна "):].strip()
    cursor.execute("SELECT subject, task, due_date FROM deadlines WHERE user_id=? AND subject LIKE ? ORDER BY due_date ASC", 
                   (message.from_user.id, f"%{subject}%"))
    rows = cursor.fetchall()

    if not rows:
        await message.answer(f"Нет дедлайнов по предмету: {subject}")
    else:
        text = f"📌 Дедлайны по предмету {subject}:\n\n"
        for subject, task, due_date in rows:
            text += f"{due_date}: {subject} — {task}\n"
        await message.answer(text)

@router.message(F.text == "/пары завтра")
async def show_classes_tomorrow(message: Message):
    tomorrow = (datetime.datetime.today() + timedelta(days=1)).strftime('%A')
    cursor.execute("SELECT time, subject FROM schedule WHERE user_id=? AND day=? ORDER BY time", 
                   (message.from_user.id, tomorrow.capitalize()))
    rows = cursor.fetchall()

    if not rows:
        await message.answer(f"На завтра ({tomorrow}) нет пар 🎉")
    else:
        text = f"📚 Расписание на завтра ({tomorrow}):\n\n"
        for time, subject in rows:
            text += f"{time} — {subject}\n"
        await message.answer(text)

@router.message(F.text == "/расходы за апрель")
async def show_expenses_for_month(message: Message):
    cursor.execute("SELECT category, SUM(amount), strftime('%m', date) FROM expenses WHERE user_id=? AND strftime('%m', date)='04' GROUP BY category", 
                   (message.from_user.id,))
    rows = cursor.fetchall()

    if not rows:
        await message.answer("У тебя нет расходов за апрель 💸")
    else:
        text = "💰 Расходы за апрель:\n\n"
        for category, amount, _ in rows:
            text += f"{category}: {amount} ₸\n"
        await message.answer(text)

@router.message(F.text == "/добавить_дедлайн")
async def add_deadline(message: Message):
    await message.answer("Введите дедлайн в формате: Предмет | Задание | 2025-05-15. Вы можете прикрепить файл (например, PDF или фото).")

@router.message(lambda msg: '|' in msg.text and '-' in msg.text and len(msg.text.split('|')) == 3)
async def save_deadline(message: Message):
    subject, task, due_date = [s.strip() for s in message.text.split('|')]
    file_id = None

    # Проверяем, есть ли файл
    if message.document:
        file_id = message.document.file_id

    cursor.execute("INSERT INTO deadlines (user_id, subject, task, due_date, file_id) VALUES (?, ?, ?, ?, ?)",
                   (message.from_user.id, subject, task, due_date, file_id))
    conn.commit()
    await message.answer("✅ Дедлайн сохранён!")

@router.message(F.text == "/дедлайны")
async def show_deadlines(message: Message):
    cursor.execute("SELECT subject, task, due_date, file_id FROM deadlines WHERE user_id=? ORDER BY due_date ASC", (message.from_user.id,))
    rows = cursor.fetchall()

    if not rows:
        await message.answer("У тебя пока нет дедлайнов ✍️")
    else:
        text = "📌 Твои дедлайны:\n\n"
        for subject, task, due_date, file_id in rows:
            text += f"{due_date}: {subject} — {task}\n"
            if file_id:
                await message.answer_document(file_id)
        await message.answer(text)

@router.message(F.text == "/удалить_дедлайн")
async def delete_deadline(message: Message):
    cursor.execute("SELECT id, subject, task, due_date FROM deadlines WHERE user_id=?", (message.from_user.id,))
    rows = cursor.fetchall()

    if not rows:
        await message.answer("У тебя нет дедлайнов для удаления.")
        return

    # Создаём клавиатуру с кнопками для удаления дедлайнов
    keyboard = InlineKeyboardMarkup(row_width=1)
    for row in rows:
        deadline_id, subject, task, due_date = row
        button_text = f"{subject} — {task} ({due_date})"
        button = InlineKeyboardButton(text=button_text, callback_data=f"delete_deadline_{deadline_id}")
        keyboard.add(button)

    await message.answer("Выбери дедлайн для удаления:", reply_markup=keyboard)

# Обработчик callback данных для удаления дедлайна
@router.callback_query(lambda c: c.data.startswith('delete_deadline_'))
async def handle_deadline_deletion(callback_query: types.CallbackQuery):
    deadline_id = int(callback_query.data.split('_')[-1])  # Извлекаем ID из callback_data
    cursor.execute("DELETE FROM deadlines WHERE id=? AND user_id=?", (deadline_id, callback_query.from_user.id))
    conn.commit()
    await callback_query.answer("✅ Дедлайн удалён!")
    await callback_query.message.edit_text("Дедлайн был успешно удалён.", reply_markup=None)

@router.message(F.text == "/удалить_расход")
async def delete_expense(message: Message):
    cursor.execute("SELECT id, category, amount, date FROM expenses WHERE user_id=?", (message.from_user.id,))
    rows = cursor.fetchall()

    if not rows:
        await message.answer("У тебя нет расходов для удаления.")
        return

    # Создаём клавиатуру с кнопками для удаления расходов
    keyboard = InlineKeyboardMarkup(row_width=1)
    for row in rows:
        expense_id, category, amount, date = row
        button_text = f"{category} — {amount} ₸ ({date})"
        button = InlineKeyboardButton(text=button_text, callback_data=f"delete_expense_{expense_id}")
        keyboard.add(button)

    await message.answer("Выбери расход для удаления:", reply_markup=keyboard)

# Обработчик callback данных для удаления расхода
@router.callback_query(lambda c: c.data.startswith('delete_expense_'))
async def handle_expense_deletion(callback_query: types.CallbackQuery):
    expense_id = int(callback_query.data.split('_')[-1])  # Извлекаем ID из callback_data
    cursor.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (expense_id, callback_query.from_user.id))
    conn.commit()
    await callback_query.answer("✅ Расход удалён!")
    await callback_query.message.edit_text("Расход был успешно удалён.", reply_markup=None)