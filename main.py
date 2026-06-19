import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import gspread
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Информация о школе для AI
SCHOOL_INFO = """
Ты помощник школы английского Fountaine English в Бишкеке.
Отвечай только на вопросы про английский язык и нашу школу.
Отвечай кратко, дружелюбно, на том языке на котором спрашивают.

О школе:
- Название: Fountaine English
- Город: Бишкек, Кыргызстан
- Уровни: Beginner, Elementary, Intermediate, Upper-Intermediate
- Форматы: группы и индивидуально
- Запись: через этого бота командой /start
- Для вопросов о цене: написать менеджеру в директ @Fountaine_xBot
"""
from google.oauth2.service_account import Credentials

# -------------------------- Config --------------------------
from config import BOT_TOKEN, ADMIN_CHAT_ID, SHEET_ID, SERVICE_ACCOUNT_FILE, LANGUAGES

# -------------------------- Logging --------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------- Bot & Dispatcher ------------------
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# -------------------------- Google Sheets --------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
worksheet = sh.worksheet("Лист1")  # ensure sheet name matches

# -------------------------- Texts ---------------------------
TEXTS = {
    "ru": {
        "welcome": "Добро пожаловать! Выберите язык:",
        "choose_lang": "Выберите язык / Тилди тандоо:",
        "ask_name": "Введите ваше имя:",
        "ask_phone": "Введите ваш номер телефона (формат: +996 XXX XXX XXX или 0XXX XXX XXX):",
        "invalid_phone": "Номер телефона некорректен. Попробуйте ещё раз.",
        "ask_level": "Какой у вас уровень английского?",
        "level_beginner": "Beginner",
        "level_elementary": "Elementary",
        "level_intermediate": "Intermediate",
        "level_unknown": "Не знаю / Билбейм",
        "test_intro": "Давайте определим ваш уровень коротким тестом из 3 вопросов.",
        "test_q1": "Вопрос 1: My name ___ John.",
        "test_q1_opts": ["is", "am", "are", "be"],
        "test_q2": "Вопрос 2: She ___ to school every day.",
        "test_q2_opts": ["go", "goes", "going", "went"],
        "test_q3": "Вопрос 3: They ___ at the moment.",
        "test_q3_opts": ["study", "studies", "studying", "studied"],
        "test_correct": "Правильно!",
        "test_wrong": "Неправильно. Правильный ответ: {answer}",
        "ask_goal": "Какова ваша цель изучения английского?",
        "goal_work": "Работа/Иш",
        "goal_study": "Учеба/Окуу",
        "goal_travel": "Путешествия/Саякат",
        "goal_other": "Другое/Башка",
        "ask_time": "Когда вам удобно заниматься?",
        "time_morning": "Утро/Эртең",
        "time_day": "День/Күн",
        "time_evening": "Вечер/Кеч",
        "time_manual": "Ввести вручную",
        "enter_time_manual": "Введите удобное время (например: 19:00 или по будням):",
        "summary": "Проверьте введённые данные:\n"
                   "<b>Имя:</b> {name}\n"
                   "<b>Телефон:</b> {phone}\n"
                   "<b>Уровень:</b> {level}\n"
                   "<b>Цель:</b> {goal}\n"
                   "<b>Время:</b> {time}\n"
                   "Всё верно?",
        "confirm_yes": "Всё верно / Өзгөртүү",
        "confirm_no": "Изменить / Түзөтүү",
        "restart": "Начинаем сначала. Выберите язык:",
        "success": "Заявка принята! Менеджер свяжется с вами в течение часа.",
        "back": "Назад",
        "language_chosen": "Язык выбран: {lang}",
    },
    "ky": {
        "welcome": "Кош келдиніз! Тилди тандаңыз:",
        "choose_lang": "Выберите язык / Тилди тандоо:",
        "ask_name": "Атыңызды жазыңыз:",
        "ask_phone": "Телефон нөмуңүздү жазыңыз (+996 XXX XXX XXX же 0XXX XXX XXX):",
        "invalid_phone": "Телефон ному жараaysyz. Кайрадан уруксат чыгарыңыз.",
        "ask_level": "Англис тилиндеги заявилчылыгыңыз кандай?",
        "level_beginner": "Beginner",
        "level_elementary": "Elementary",
        "level_intermediate": "Intermediate",
        "level_unknown": "Не знаю / Билбейм",
        "test_intro": "Сиздин дегенгилеңизди 3 суроолук тестте аныктайбыз.",
        "test_q1": "Суроо 1: My name ___ John.",
        "test_q1_opts": ["is", "am", "are", "be"],
        "test_q2": "Суроо 2: She ___ to school every day.",
        "test_q2_opts": ["go", "goes", "going", "went"],
        "test_q3": "Суроо 3: They ___ at the moment.",
        "test_q3_opts": ["study", "studies", "studying", "studied"],
        "test_correct": "Тоого!",
        "test_wrong": "Жок. Тоодоорону javobi: {answer}",
        "ask_goal": "Англис тилинди окуйтуңуздун максады кандай?",
        "goal_work": "Иш",
        "goal_study": "Окуу",
        "goal_travel": "Саякат",
        "goal_other": "Башка",
        "ask_time": "Кайда siz үчün уютту bolsun?",
        "time_morning": "Эртең",
        "time_day": "Күн",
        "time_evening": "Кеч",
        "time_manual": "Мануалда киргизиңиз",
        "enter_time_manual": "Убакытты жазыңыз ( misal: 19:00 ЖОКТО Же бирgé либо):",
        "summary": "Маалыматты текшерриңиз:\n"
                   "<b>Аты:</b> {name}\n"
                   "<b>Телефон:</b> {phone}\n"
                   "<b>Уровень:</b> {level}\n"
                   "<b>Цель:</b> {goal}\n"
                   "<b>Время:</b> {time}\n"
                   "Бардыкто туура эми?",
        "confirm_yes": "Бардык туура / Өзгөртүү",
        "confirm_no": "Түзөтүү / Алга",
        "restart": "Бас	throwандан баштайыбыз. Тилди тандоңуз:",
        "success": "Муржаат кабул болду! Оператор саатた_hour ичинде байланышат.",
        "back": "Алга",
        "language_chosen": "Тил тандалды: {lang}",
    }
}

# -------------------------- FSM ---------------------------
class RegisterForm(StatesGroup):
    language = State()
    name = State()
    phone = State()
    level = State()
    test_q1 = State()
    test_q2 = State()
    test_q3 = State()
    test_score = State()
    goal = State()
    time = State()
    confirm = State()

# -------------------------- Keyboards ----------------------
def lang_kb():
    builder = ReplyKeyboardBuilder()
    for code, name in LANGUAGES.items():
        builder.add(types.KeyboardButton(text=name))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def back_kb(lang):
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text=TEXTS[lang]["back"]))
    return builder.as_markup(resize_keyboard=True)

def level_kb(lang):
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text=TEXTS[lang]["level_beginner"]))
    builder.add(types.KeyboardButton(text=TEXTS[lang]["level_elementary"]))
    builder.add(types.KeyboardButton(text=TEXTS[lang]["level_intermediate"]))
    builder.add(types.KeyboardButton(text=TEXTS[lang]["level_unknown"]))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def test_kb(options):
    builder = ReplyKeyboardBuilder()
    for opt in options:
        builder.add(types.KeyboardButton(text=opt))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def goal_kb(lang):
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text=TEXTS[lang]["goal_work"]))
    builder.add(types.KeyboardButton(text=TEXTS[lang]["goal_study"]))
    builder.add(types.KeyboardButton(text=TEXTS[lang]["goal_travel"]))
    builder.add(types.KeyboardButton(text=TEXTS[lang]["goal_other"]))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def time_kb(lang):
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text=TEXTS[lang]["time_morning"]))
    builder.add(types.KeyboardButton(text=TEXTS[lang]["time_day"]))
    builder.add(types.KeyboardButton(text=TEXTS[lang]["time_evening"]))
    builder.add(types.KeyboardButton(text=TEXTS[lang]["time_manual"]))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def confirm_kb(lang):
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text=TEXTS[lang]["confirm_yes"]))
    builder.add(types.KeyboardButton(text=TEXTS[lang]["confirm_no"]))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# -------------------------- Helpers -----------------------
def get_text(lang, key):
    return TEXTS.get(lang, TEXTS["ru"]).get(key, "")

def validate_phone(text: str) -> bool:
    # Accept +996 XXX XXX XXX or 0XXX XXX XXX (with spaces optional)
    import re
    pattern = r'^(\+996\s?\d{3}\s?\d{3}\s?\d{3}|0\s?\d{3}\s?\d{3}\s?\d{3})$'
    return bool(re.match(pattern, text))

def determine_level_from_test(score: int) -> str:
    if score <= 1:
        return "Beginner"
    elif score == 2:
        return "Elementary"
    else:
        return "Intermediate"

# -------------------------- Handlers ----------------------
@dp.message(Command("start"))
@dp.message(F.text == TEXTS["ru"]["back"], StateFilter(None))  # if back pressed outside FSM
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(get_text("ru", "welcome"), reply_markup=lang_kb())
    await state.set_state(RegisterForm.language)

@dp.message(Command("ask"))
async def cmd_ask(message: types.Message, state: FSMContext):
    # Сбрасываем состояние анкеты если активно
    current_state = await state.get_state()
    
    question = message.text.replace("/ask", "").strip()
    
    if not question:
        await message.answer(
            "✨ Напиши вопрос после команды:\n"
            "/ask Какие направления есть?"
        )
        return
    
    await message.bot.send_chat_action(message.chat.id, "typing")
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SCHOOL_INFO},
                {"role": "user", "content": question}
            ],
            max_tokens=300
        )
        answer = response.choices[0].message.content
        await message.answer(f"🤖 {answer}")
        
    except Exception as e:
        await message.answer("❌ Не удалось получить ответ. Попробуй позже.")

# Language selection
@dp.message(StateFilter(RegisterForm.language))
async def process_language(message: types.Message, state: FSMContext):
    lang_code = None
    for code, name in LANGUAGES.items():
        if message.text == name:
            lang_code = code
            break
    if not lang_code:
        await message.answer(get_text("ru", "choose_lang"), reply_markup=lang_kb())
        return
    await state.update_data(language=lang_code)
    await state.set_state(RegisterForm.name)
    await message.answer(get_text(lang_code, "ask_name"), reply_markup=types.ReplyKeyboardRemove())

# Name
@dp.message(StateFilter(RegisterForm.name))
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    data = await state.get_data()
    lang = data["language"]
    await state.set_state(RegisterForm.phone)
    await message.answer(get_text(lang, "ask_phone"), reply_markup=back_kb(lang))

# Phone
@dp.message(StateFilter(RegisterForm.phone))
async def process_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    if message.text == TEXTS[lang]["back"]:
        await state.set_state(RegisterForm.name)
        await message.answer(get_text(lang, "ask_name"), reply_markup=types.ReplyKeyboardRemove())
        return
    if not validate_phone(message.text):
        await message.answer(get_text(lang, "invalid_phone"), reply_markup=back_kb(lang))
        return
    await state.update_data(phone=message.text.strip())
    await state.set_state(RegisterForm.level)
    await message.answer(get_text(lang, "ask_level"), reply_markup=level_kb(lang))

# Level
@dp.message(StateFilter(RegisterForm.level))
async def process_level(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    if message.text == TEXTS[lang]["back"]:
        await state.set_state(RegisterForm.phone)
        await message.answer(get_text(lang, "ask_phone"), reply_markup=back_kb(lang))
        return
    if message.text == TEXTS[lang]["level_unknown"]:
        await state.set_state(RegisterForm.test_q1)
        await message.answer(get_text(lang, "test_intro"))
        await message.answer(get_text(lang, "test_q1"), reply_markup=test_kb(TEXTS[lang]["test_q1_opts"]))
        return
    # known level
    await state.update_data(level=message.text)
    await state.set_state(RegisterForm.goal)
    await message.answer(get_text(lang, "ask_goal"), reply_markup=goal_kb(lang))

# Test Q1
@dp.message(StateFilter(RegisterForm.test_q1))
async def process_test_q1(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    if message.text == TEXTS[lang]["back"]:
        await state.set_state(RegisterForm.level)
        await message.answer(get_text(lang, "ask_level"), reply_markup=level_kb(lang))
        return
    correct = TEXTS[lang]["test_q1_opts"][0]  # "is"
    if message.text == correct:
        await message.answer(get_text(lang, "test_correct"))
        await state.update_data(test_score=1)
    else:
        await message.answer(get_text(lang, "test_wrong").format(answer=correct))
        await state.update_data(test_score=0)
    await state.set_state(RegisterForm.test_q2)
    await message.answer(get_text(lang, "test_q2"), reply_markup=test_kb(TEXTS[lang]["test_q2_opts"]))

# Test Q2
@dp.message(StateFilter(RegisterForm.test_q2))
async def process_test_q2(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    if message.text == TEXTS[lang]["back"]:
        await state.set_state(RegisterForm.test_q1)
        await message.answer(get_text(lang, "test_q1"), reply_markup=test_kb(TEXTS[lang]["test_q1_opts"]))
        return
    correct = TEXTS[lang]["test_q2_opts"][1]  # "goes"
    score = data.get("test_score", 0)
    if message.text == correct:
        await message.answer(get_text(lang, "test_correct"))
        await state.update_data(test_score=score + 1)
    else:
        await message.answer(get_text(lang, "test_wrong").format(answer=correct))
        await state.update_data(test_score=score)
    await state.set_state(RegisterForm.test_q3)
    await message.answer(get_text(lang, "test_q3"), reply_markup=test_kb(TEXTS[lang]["test_q3_opts"]))

# Test Q3
@dp.message(StateFilter(RegisterForm.test_q3))
async def process_test_q3(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    if message.text == TEXTS[lang]["back"]:
        await state.set_state(RegisterForm.test_q2)
        await message.answer(get_text(lang, "test_q2"), reply_markup=test_kb(TEXTS[lang]["test_q2_opts"]))
        return
    correct = TEXTS[lang]["test_q3_opts"][2]  # "studying"
    score = data.get("test_score", 0)
    if message.text == correct:
        await message.answer(get_text(lang, "test_correct"))
        await state.update_data(test_score=score + 1)
    else:
        await message.answer(get_text(lang, "test_wrong").format(answer=correct))
        await state.update_data(test_score=score)
    # Determine level from score
    level = determine_level_from_test(data.get("test_score", 0))
    await state.update_data(level=level)
    await state.set_state(RegisterForm.goal)
    await message.answer(get_text(lang, "ask_goal"), reply_markup=goal_kb(lang))

# Goal
@dp.message(StateFilter(RegisterForm.goal))
async def process_goal(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    if message.text == TEXTS[lang]["back"]:
        # If we came from test, go back to test? Simpler: go to level
        await state.set_state(RegisterForm.level)
        await message.answer(get_text(lang, "ask_level"), reply_markup=level_kb(lang))
        return
    await state.update_data(goal=message.text)
    await state.set_state(RegisterForm.time)
    await message.answer(get_text(lang, "ask_time"), reply_markup=time_kb(lang))

# Time
@dp.message(StateFilter(RegisterForm.time))
async def process_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    if message.text == TEXTS[lang]["back"]:
        await state.set_state(RegisterForm.goal)
        await message.answer(get_text(lang, "ask_goal"), reply_markup=goal_kb(lang))
        return
    if message.text == TEXTS[lang]["time_manual"]:
        await state.set_state(RegisterForm.time)  # stay in same state but ask manual
        await message.answer(get_text(lang, "enter_time_manual"), reply_markup=back_kb(lang))
        return
    # store selected time
    await state.update_data(time=message.text)
    await state.set_state(RegisterForm.confirm)
    await show_summary(message, state)

async def show_summary(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    summary_txt = get_text(lang, "summary").format(
        name=data.get("name", "-"),
        phone=data.get("phone", "-"),
        level=data.get("level", "-"),
        goal=data.get("goal", "-"),
        time=data.get("time", "-")
    )
    await message.answer(summary_txt, parse_mode="HTML", reply_markup=confirm_kb(lang))

# Confirm
@dp.message(StateFilter(RegisterForm.confirm))
async def process_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    if message.text == TEXTS[lang]["back"]:
        await state.set_state(RegisterForm.time)
        await message.answer(get_text(lang, "ask_time"), reply_markup=time_kb(lang))
        return
    if message.text == TEXTS[lang]["confirm_yes"]:
        # Save to Google Sheets
        await save_to_sheets(data)
        # Notify admin
        await notify_admin(data)
        await state.set_state(RegisterForm.language)  # reset for next user
        await message.answer(get_text(lang, "success"), reply_markup=lang_kb())
    else:  # confirm_no -> go back to start? Let's go to language selection to redo
        await state.set_state(RegisterForm.language)
        await message.answer(get_text(lang, "restart"), reply_markup=lang_kb())

# Save to Google Sheets
async def save_to_sheets(data: dict):
    try:
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        row = [
            now,
            data.get("name", ""),
            data.get("phone", ""),
            data.get("level", ""),
            data.get("time", ""),
            "Telegram Bot",
            "Новая",
            data.get("goal", "")
        ]
        worksheet.append_row(row)
        logger.info("Saved to Google Sheets: %s", row)
    except Exception as e:
        logger.error("Failed to save to Google Sheets: %s", e)

# Notify admin
async def notify_admin(data: dict):
    try:
        text = (
            f"Новая заявка от бота:\n"
            f"Имя: {data.get('name')}\n"
            f"Телефон: {data.get('phone')}\n"
            f"Уровень: {data.get('level')}\n"
            f"Цель: {data.get('goal')}\n"
            f"Время: {data.get('time')}\n"
            f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        await bot.send_message(ADMIN_CHAT_ID, text)
    except Exception as e:
        logger.error("Failed to notify admin: %s", e)

@dp.message(Command("ask"))
async def cmd_ask(message: types.Message):
    # Убираем /ask из текста
    question = message.text.replace("/ask", "").strip()
    
    if not question:
        await message.answer(
            "✨ Напиши вопрос после команды:\n"
            "/ask Сколько стоят уроки?"
        )
        return
    
    # Показываем что печатаем
    await message.bot.send_chat_action(message.chat.id, "typing")
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SCHOOL_INFO},
                {"role": "user", "content": question}
            ],
            max_tokens=300
        )
        answer = response.choices[0].message.content
        await message.answer(f"🤖 {answer}")
        
    except Exception as e:
        await message.answer("❌ Не удалось получить ответ. Попробуй позже.")
from aiogram.fsm.state import default_state


# -------------------------- Main --------------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
