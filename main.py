import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime

if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_logs.txt', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID_STR = os.getenv('ADMIN_CHAT_ID', '0')
GOOGLE_SHEETS_ID = os.getenv('GOOGLE_SHEETS_ID')
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
SERVICE_ACCOUNT_FILE = os.getenv('SERVICE_ACCOUNT_FILE', 'service_account.json')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found in .env — bot cannot start")
    sys.exit(1)
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not found — AI questions will not work")
if not GOOGLE_SHEETS_ID:
    logger.warning("GOOGLE_SHEETS_ID not found — registrations will not be saved")

try:
    ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_STR)
except ValueError:
    logger.warning(f"Invalid ADMIN_CHAT_ID: '{ADMIN_CHAT_ID_STR}', defaulting to 0")
    ADMIN_CHAT_ID = 0

if ADMIN_CHAT_ID == 0:
    logger.warning("ADMIN_CHAT_ID is 0 — admin notifications disabled")

gc = spreadsheet = sheet = faq_sheet = None

if GOOGLE_SHEETS_ID:
    try:
        if GOOGLE_CREDENTIALS_JSON:
            creds = Credentials.from_service_account_info(
                json.loads(GOOGLE_CREDENTIALS_JSON),
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
        else:
            creds = Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
        sheet = spreadsheet.sheet1
        logger.info("Google Sheets connected")
        try:
            all_ws = spreadsheet.worksheets()
            faq_sheet = next((ws for ws in all_ws if ws.title.lower() == "faq"), None)
            if faq_sheet:
                logger.info(f"FAQ sheet loaded: {faq_sheet.title}")
            else:
                logger.warning(f"FAQ sheet not found. Available: {[ws.title for ws in all_ws]}")
        except Exception as e:
            logger.warning(f"FAQ sheet error: {e}")
    except FileNotFoundError:
        logger.error(f"Service account file '{SERVICE_ACCOUNT_FILE}' not found")
    except Exception as e:
        logger.error(f"Google Sheets error: {e}")

client = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("OpenAI client initialized")


class RegistrationStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_registration_choice = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_level = State()
    waiting_for_time = State()
    waiting_for_goal = State()
    registration_summary = State()
    faq_view = State()
    schedule_view = State()
    reviews_view = State()
    prices_view = State()
    contacts_view = State()
    settings_view = State()
    main_menu = State()
    ask_question = State()


TEXTS = {
    "ru": {
        "welcome": "👋 Привет! Я AI-помощник школы английского Flow English School.\n\nМогу ответить на любой вопрос о школе, ценах и записи — просто напишите в чат.\n\nИли выберите язык 👇",
        "choose_language": "Выберите язык / Тилди тандаңыз:",
        "russian": "🇷🇺 Русский",
        "kyrgyz": "🇰🇬 Кыргызский",
        "want_register": "Хотите записаться на бесплатный пробный урок?",
        "yes": "✅ Да",
        "no": "🙅 Нет, спасибо",
        "main_menu": "📌 Главное меню\n\n🤖 Вы можете написать любой вопрос прямо в чат — AI ответит мгновенно.",
        "faq": "📚 F.A.Q.",
        "ask_question": "🤖 Спросить AI",
        "register": "🎫 Записаться",
        "prices": "💷 Цены",
        "schedule": "⏳ Расписание",
        "reviews": "❤️‍🔥 Отзывы",
        "contacts": "📲 Контакты",
        "settings": "🪞 Настройки",
        "back_to_menu": "🔖 Вернуться в меню",
        "cancel": "✖ Отмена",

        "enter_name": "👤 Введите ваше имя:",
        "invalid_name": "⚠️ Имя должно содержать только буквы. Попробуйте снова:",
        "enter_phone": "📱 Введите номер телефона:",
        "invalid_phone": "⚠️ Некорректный номер. Попробуйте снова (пример: +996 700 123 456):",
        "choose_level": "🎓 Выберите ваш уровень английского:",
        "level_beginner": "🌱 Beginner (A1)",
        "level_elementary": "📖 Elementary (A2)",
        "level_intermediate": "🎯 Intermediate (B1)",
        "level_upper": "🔥 Upper-Intermediate (B2)",
        "level_unknown": "❓ Не знаю",
        "level_test": "🧪 Пройти тест",
        "level_test_msg": "Пройдите бесплатный тест на определение уровня:\nhttps://www.cambridgeenglish.org/test-your-english/\n\nПосле прохождения выберите свой уровень 👇",
        "enter_time": "⏰ Когда удобно заниматься?",
        "time_morning": "🌅 Утро (9:00–12:00)",
        "time_afternoon": "☀️ День (12:00–17:00)",
        "time_evening": "🌙 Вечер (17:00–21:00)",
        "time_flexible": "🔄 Гибкое расписание",
        "invalid_time": "Пожалуйста, выберите время из предложенных вариантов:",
        "enter_goal": "🎯 Какая ваша цель?",
        "goal_exam": "📚 Подготовка к экзамену",
        "goal_conversation": "💬 Разговорный английский",
        "goal_business": "💼 Деловой английский",
        "goal_general": "🎓 Общее развитие",
        "goal_other": "📝 Другое",
        "invalid_goal": "Пожалуйста, выберите цель из предложенных вариантов:",

        "summary": "📋 Ваши данные:",
        "name": "Имя",
        "phone": "Телефон",
        "level": "Уровень",
        "time": "Время",
        "goal": "Цель",
        "edit_name": "✏️ Изменить имя",
        "edit_phone": "✏️ Изменить телефон",
        "edit_level": "✏️ Изменить уровень",
        "edit_time": "✏️ Изменить время",
        "edit_goal": "✏️ Изменить цель",
        "confirm": "✅ Подтвердить запись",
        "success": "✅ Спасибо! Мы свяжемся с вами в ближайшее время.",
        "probny_urok": "🎁 Пробный урок — БЕСПЛАТНО",

        "faq_q1": "Сколько стоят групповые занятия?",
        "faq_a1": "3 500 сом в месяц.",
        "faq_q2": "Как проходят занятия?",
        "faq_a2": "Занятия проходят оффлайн по 1 часу.",
        "faq_q3": "Есть ли скидки на пакеты?",
        "faq_a3": "Нет, скидок на пакеты нет.",
        "faq_q4": "Можно ли заниматься индивидуально?",
        "faq_a4": "Можно. Стоимость индивидуальных занятий обсуждается индивидуально.",

        "schedule_title": "🗓 Расписание занятий:",
        "monday": "Понедельник",
        "tuesday": "Вторник",
        "wednesday": "Среда",
        "thursday": "Четверг",
        "friday": "Пятница",
        "saturday": "Суббота",
        "sunday": "Воскресенье",

        "reviews_title": "👑 Отзывы студентов:",
        "review_1": "✨ За 3 месяца заметил огромный прогресс. Преподаватели — топ! — Алексей",
        "review_2": "✨ Гибкое расписание, адекватные цены. Советую всем! — Мария",
        "review_3": "✨ Лучшая школа в городе. Очень внимательный подход. — Иван",

        "prices_title": "💛 Наши цены:",
        "price_1": "👥 Групповые занятия — 3 500 сом/месяц",
        "price_2": "👤 Индивидуальные занятия — обсуждается индивидуально",
        "price_3": "❌ Скидки на пакеты — отсутствуют",
        "price_4": "🎁 Пробный урок — БЕСПЛАТНО",
        "record_now": "🎫 Записаться",

        "contacts_title": "📌 Контакты:",
        "contact_phone": "",
        "contact_email": "✉️ Email: flow_kg1@gmail.com",
        "contact_instagram": "",
        "contact_location": "📍 Бишкек, ул. Чуй 75",
        "call_admin": "📞 Позвонить администратору",

        "ask_question_text": "✨ Напишите ваш вопрос — AI ответит прямо сейчас:",
        "ai_unavailable": "AI-помощник временно недоступен. Свяжитесь с нами:",
        "question_received": "✅ Ответ на ваш вопрос:",
        "invalid_question": "Вопрос слишком короткий. Напишите подробнее:",
        "ai_dont_know": "Не нашёл ответ в базе. Свяжитесь с нами напрямую:",

        "admin_notification": "🎫 Новая запись!",
        "change_language": "🌐 Сменить язык",
        "sheets_error": "Ошибка при сохранении данных",
        "sheets_not_configured": "Google Sheets не подключён",
        "cancelled": "Действие отменено.",
        "unknown_command": "Используйте кнопки меню или /start для перезапуска.",
    },
    "ky": {
        "welcome": "👋 Салам! Мен Flow English School мектебинин AI-жардамчысымын.\n\nМектеп, баалар жана катталуу боюнча каалаган суроону жазсаңыз болот — дароо жооп берем.\n\nТилди тандаңыз 👇",
        "choose_language": "Тилди тандаңыз / Выберите язык:",
        "russian": "🇷🇺 Русский",
        "kyrgyz": "🇰🇬 Кыргызский",
        "want_register": "Акысыз сынак сабакка катталгыңыз келеби?",
        "yes": "✅ Ооба",
        "no": "🙅 Жок, рахмат",
        "main_menu": "📌 Башкы меню\n\n🤖 Каалаган суроону түздөн-түз чатка жазсаңыз болот — AI дароо жооп берет.",
        "faq": "📚 F.A.Q.",
        "ask_question": "🤖 AI Жардамчы",
        "register": "🎫 Катталуу",
        "prices": "💷 Баалар",
        "schedule": "⏳ Расписание",
        "reviews": "❤️‍🔥 Сын-пикирлер",
        "contacts": "📲 Байланыш",
        "settings": "🪞 Параметрлер",
        "back_to_menu": "🔖 Менюгө кайтуу",
        "cancel": "✖ Жокко чыгаруу",

        "enter_name": "👤 Атыңызды жазыңыз:",
        "invalid_name": "⚠️ Ат тек тамгалардан турушу керек. Кайра аракет кылыңыз:",
        "enter_phone": "📱 Телефон номериңизди жазыңыз:",
        "invalid_phone": "⚠️ Туура эмес номер. Кайра аракет кылыңыз (+996 700 123 456):",
        "choose_level": "🎓 Англис тилиңиздин деңгээлин тандаңыз:",
        "level_beginner": "🌱 Beginner (A1)",
        "level_elementary": "📖 Elementary (A2)",
        "level_intermediate": "🎯 Intermediate (B1)",
        "level_upper": "🔥 Upper-Intermediate (B2)",
        "level_unknown": "❓ Билбейм",
        "level_test": "🧪 Тест тапшыруу",
        "level_test_msg": "Акысыз деңгээл аныктоо тестин тапшырыңыз:\nhttps://www.cambridgeenglish.org/test-your-english/\n\nТапшыргандан кийин деңгээлиңизди тандаңыз 👇",
        "enter_time": "⏰ Качан окуу ыңайлуу?",
        "time_morning": "🌅 Таңкы (9:00–12:00)",
        "time_afternoon": "☀️ Күндүз (12:00–17:00)",
        "time_evening": "🌙 Кечки (17:00–21:00)",
        "time_flexible": "🔄 Ийкемдүү расписание",
        "invalid_time": "Убакытты сунушталган варианттардан тандаңыз:",
        "enter_goal": "🎯 Сиздин максатыңыз кандай?",
        "goal_exam": "📚 Экзаменге даярдык",
        "goal_conversation": "💬 Сүйлөшүү англисчеси",
        "goal_business": "💼 Иш англисчеси",
        "goal_general": "🎓 Жалпы өнүгүү",
        "goal_other": "📝 Башка",
        "invalid_goal": "Максатты сунушталган варианттардан тандаңыз:",

        "summary": "📋 Сиздин маалыматыңыз:",
        "name": "Ат",
        "phone": "Телефон",
        "level": "Деңгээл",
        "time": "Убакыт",
        "goal": "Максат",
        "edit_name": "✏️ Атты өзгөртүү",
        "edit_phone": "✏️ Телефонду өзгөртүү",
        "edit_level": "✏️ Деңгээлди өзгөртүү",
        "edit_time": "✏️ Убакытты өзгөртүү",
        "edit_goal": "✏️ Максатты өзгөртүү",
        "confirm": "✅ Каттоону ырастоо",
        "success": "✅ Рахмат! Жакын убакытта байланышабыз.",
        "probny_urok": "🎁 Сынак сабак — АКЫСЫЗ",

        "faq_q1": "Топтук сабактардын баасы канча?",
        "faq_a1": "Айына 3 500 сом.",
        "faq_q2": "Сабактар кандай өтөт?",
        "faq_a2": "Сабактар оффлайнда 1 саат өтөт.",
        "faq_q3": "Пакеттик арзандатуулар барбы?",
        "faq_a3": "Жок, пакеттик арзандатуулар жок.",
        "faq_q4": "Жекече окуу мүмкүнбү?",
        "faq_a4": "Мүмкүн. Жекече сабактардын баасы жекече талкууланат.",

        "schedule_title": "🗓 Сабактардын расписаниеси:",
        "monday": "Дүйшөмбү",
        "tuesday": "Шейшемби",
        "wednesday": "Чаршемби",
        "thursday": "Бейшемби",
        "friday": "Жума",
        "saturday": "Ишемби",
        "sunday": "Жекшемби",

        "reviews_title": "👑 Студенттердин пикирлери:",
        "review_1": "✨ 3 айда чоң прогресс байкадым. Мугалимдер — эң жакшы! — Алексей",
        "review_2": "✨ Ыңгайлуу расписание, жеткиликтүү баалар. Сунуштайм! — Мария",
        "review_3": "✨ Шаардагы эң жакшы мектеп. Мугалимдер өтө кунт коюшат. — Иван",

        "prices_title": "💛 Биздин баалар:",
        "price_1": "👥 Топтук сабактар — 3 500 сом/айга",
        "price_2": "👤 Жеке сабактар — жекече талкууланат",
        "price_3": "❌ Пакеттик арзандатуулар — жок",
        "price_4": "🎁 Сынак сабак — АКЫСЫЗ",
        "record_now": "🎫 Катталуу",

        "contacts_title": "📌 Байланыш:",
        "contact_phone": "",
        "contact_email": "✉️ Email: flow_kg1@gmail.com",
        "contact_instagram": "",
        "contact_location": "📍 Бишкек, Чүй көчөсү 75",
        "call_admin": "📞 Администраторго чалуу",

        "ask_question_text": "✨ Суроонузду жазыңыз — AI азыр эле жооп берет:",
        "ai_unavailable": "AI убактылуу иштебейт. Бизге түздөн-түз байланышыңыз:",
        "question_received": "✅ Суроонузга жооп:",
        "invalid_question": "Суроо өтө кыска. Толугураак жазыңыз:",
        "ai_dont_know": "Базадан жооп таппадым. Бизге түздөн-түз байланышыңыз:",

        "admin_notification": "🎫 Жаңы катталуу!",
        "change_language": "🌐 Тилди өзгөртүү",
        "sheets_error": "Маалыматты сактоодо ката",
        "sheets_not_configured": "Google Sheets туташтырылган эмес",
        "cancelled": "Аракет жокко чыгарылды.",
        "unknown_command": "Меню баскычтарын колдонуңуз же /start.",
    }
}


def validate_name(text):
    cleaned = text.strip()
    pattern = r"^[а-яА-ЯёЁa-zA-ZҢңӨөҮүЙй\s\-]+$"
    return bool(re.match(pattern, cleaned)) and len(cleaned) >= 2


def validate_phone(text):
    return len(re.sub(r'\D', '', text)) >= 9


def _strip_punct(s):
    return re.sub(r'[^\w\s]', '', s, flags=re.UNICODE)


# Клавиатуры
def get_language_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇰🇬 Кыргызский")]],
        resize_keyboard=True
    )


def get_yes_no_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXTS[lang]["yes"]), KeyboardButton(text=TEXTS[lang]["no"])]],
        resize_keyboard=True
    )


def get_main_menu_keyboard(lang):
    placeholder = "Напишите любой вопрос — AI ответит..." if lang == "ru" else "Каалаган суроону жазыңыз — AI жооп берет..."
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXTS[lang]["ask_question"]), KeyboardButton(text=TEXTS[lang]["register"])],
            [KeyboardButton(text=TEXTS[lang]["faq"]), KeyboardButton(text=TEXTS[lang]["prices"])],
            [KeyboardButton(text=TEXTS[lang]["schedule"]), KeyboardButton(text=TEXTS[lang]["reviews"])],
            [KeyboardButton(text=TEXTS[lang]["contacts"]), KeyboardButton(text=TEXTS[lang]["settings"])],
        ],
        resize_keyboard=True,
        input_field_placeholder=placeholder
    )


def get_level_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXTS[lang]["level_beginner"]), KeyboardButton(text=TEXTS[lang]["level_elementary"])],
            [KeyboardButton(text=TEXTS[lang]["level_intermediate"]), KeyboardButton(text=TEXTS[lang]["level_upper"])],
            [KeyboardButton(text=TEXTS[lang]["level_unknown"]), KeyboardButton(text=TEXTS[lang]["level_test"])],
            [KeyboardButton(text=TEXTS[lang]["cancel"])],
        ],
        resize_keyboard=True
    )


def get_time_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXTS[lang]["time_morning"]), KeyboardButton(text=TEXTS[lang]["time_afternoon"])],
            [KeyboardButton(text=TEXTS[lang]["time_evening"]), KeyboardButton(text=TEXTS[lang]["time_flexible"])],
            [KeyboardButton(text=TEXTS[lang]["cancel"])],
        ],
        resize_keyboard=True
    )


def get_goal_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXTS[lang]["goal_exam"]), KeyboardButton(text=TEXTS[lang]["goal_conversation"])],
            [KeyboardButton(text=TEXTS[lang]["goal_business"]), KeyboardButton(text=TEXTS[lang]["goal_general"])],
            [KeyboardButton(text=TEXTS[lang]["goal_other"])],
            [KeyboardButton(text=TEXTS[lang]["cancel"])],
        ],
        resize_keyboard=True
    )


def get_faq_keyboard(lang):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXTS[lang]["faq_q1"], callback_data="faq_1")],
            [InlineKeyboardButton(text=TEXTS[lang]["faq_q2"], callback_data="faq_2")],
            [InlineKeyboardButton(text=TEXTS[lang]["faq_q3"], callback_data="faq_3")],
            [InlineKeyboardButton(text=TEXTS[lang]["faq_q4"], callback_data="faq_4")],
            [InlineKeyboardButton(text=TEXTS[lang]["back_to_menu"], callback_data="back_to_menu")],
        ]
    )


def get_schedule_keyboard(lang):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXTS[lang]["monday"], callback_data="schedule_mon")],
            [InlineKeyboardButton(text=TEXTS[lang]["tuesday"], callback_data="schedule_tue")],
            [InlineKeyboardButton(text=TEXTS[lang]["wednesday"], callback_data="schedule_wed")],
            [InlineKeyboardButton(text=TEXTS[lang]["thursday"], callback_data="schedule_thu")],
            [InlineKeyboardButton(text=TEXTS[lang]["friday"], callback_data="schedule_fri")],
            [InlineKeyboardButton(text=TEXTS[lang]["saturday"], callback_data="schedule_sat")],
            [InlineKeyboardButton(text=TEXTS[lang]["sunday"], callback_data="schedule_sun")],
            [InlineKeyboardButton(text=TEXTS[lang]["back_to_menu"], callback_data="back_to_menu")],
        ]
    )


def get_reviews_keyboard(lang):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXTS[lang]["record_now"], callback_data="register")],
            [InlineKeyboardButton(text=TEXTS[lang]["back_to_menu"], callback_data="back_to_menu")],
        ]
    )


def get_prices_keyboard(lang):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXTS[lang]["record_now"], callback_data="register")],
            [InlineKeyboardButton(text=TEXTS[lang]["back_to_menu"], callback_data="back_to_menu")],
        ]
    )


def get_contacts_keyboard(lang):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXTS[lang]["call_admin"], callback_data="call_admin")],
            [InlineKeyboardButton(text=TEXTS[lang]["back_to_menu"], callback_data="back_to_menu")],
        ]
    )


def get_edit_keyboard(lang):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXTS[lang]["edit_name"], callback_data="edit_name")],
            [InlineKeyboardButton(text=TEXTS[lang]["edit_phone"], callback_data="edit_phone")],
            [InlineKeyboardButton(text=TEXTS[lang]["edit_level"], callback_data="edit_level")],
            [InlineKeyboardButton(text=TEXTS[lang]["edit_time"], callback_data="edit_time")],
            [InlineKeyboardButton(text=TEXTS[lang]["edit_goal"], callback_data="edit_goal")],
            [InlineKeyboardButton(text=TEXTS[lang]["confirm"], callback_data="confirm_registration")],
        ]
    )


def get_settings_keyboard(lang):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXTS[lang]["change_language"], callback_data="change_language")],
            [InlineKeyboardButton(text=TEXTS[lang]["back_to_menu"], callback_data="back_to_menu")],
        ]
    )


# ===== ВСПОМОГАТЕЛЬНЫЕ =====

async def show_summary(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")
    summary_text = (
        f"{TEXTS[lang]['summary']}\n\n"
        f"{TEXTS[lang]['name']}: {data.get('name', '—')}\n"
        f"{TEXTS[lang]['phone']}: {data.get('phone', '—')}\n"
        f"{TEXTS[lang]['level']}: {data.get('level', '—')}\n"
        f"{TEXTS[lang]['time']}: {data.get('time', '—')}\n"
        f"{TEXTS[lang]['goal']}: {data.get('goal', '—')}\n\n"
        f"{TEXTS[lang]['probny_urok']}"
    )
    await message.answer(summary_text, reply_markup=get_edit_keyboard(lang))
    await state.set_state(RegistrationStates.registration_summary)


async def show_main_menu(message: types.Message, state: FSMContext, lang: str):
    await message.answer(TEXTS[lang]["main_menu"], reply_markup=get_main_menu_keyboard(lang))
    await state.set_state(RegistrationStates.main_menu)


def _build_static_school_info(lang: str) -> str:
    t = TEXTS[lang]
    if lang == "ky":
        return (
            "=== МЕКТЕП ЖӨНҮНДӨ МААЛЫМАТ ===\n\n"
            "БААЛАР:\n"
            "- Топтук сабактар: айына 3 500 сом\n"
            "- Жеке сабактар: жекече талкууланат\n"
            "- 1 сабактын өзүнчө баасы жок (айлык абонемент)\n"
            "- Пакеттик арзандатуулар жок\n"
            "- Сынак сабак — АКЫСЫЗ\n\n"
            "МЕКТЕП ЖӨНҮНДӨ:\n"
            "- Сабактар оффлайнда өтөт, 1 саат\n"
            "- График: 10:00–21:00\n"
            "- Бардык деңгээлдер бар\n"
            "- Жекече жана топтук сабактар бар\n"
            "- Курстан кийин сертификат берилет\n"
            "- Каттоо үчүн документ керек эмес\n"
            "- 7 жаштан кабыл алабыз\n\n"
            "БАЙЛАНЫШ:\n"
            f"- {t['contact_phone']}\n"
            f"- {t['contact_email']}\n"
            f"- {t['contact_instagram']}\n"
            f"- {t['contact_location']}\n\n"
            "КЕП БЕРИЛҮҮЧҮ СУРООЛОР:\n"
            f"Q: {t['faq_q1']}\nA: {t['faq_a1']}\n\n"
            f"Q: {t['faq_q2']}\nA: {t['faq_a2']}\n\n"
            f"Q: {t['faq_q3']}\nA: {t['faq_a3']}\n\n"
            f"Q: {t['faq_q4']}\nA: {t['faq_a4']}\n"
        )
    else:
        return (
            "=== ИНФОРМАЦИЯ О ШКОЛЕ ===\n\n"
            "ЦЕНЫ:\n"
            "- Групповые занятия: 3 500 сом в месяц\n"
            "- Индивидуальные занятия: обсуждается индивидуально\n"
            "- Цены за 1 урок отдельно нет (только абонемент)\n"
            "- Скидок на пакеты нет\n"
            "- Пробный урок — БЕСПЛАТНО\n\n"
            "О ШКОЛЕ:\n"
            "- Занятия проходят оффлайн, по 1 часу\n"
            "- График работы: 10:00–21:00\n"
            "- Есть все уровни английского\n"
            "- Групповые и персональные занятия\n"
            "- Сертификат после курса — есть\n"
            "- Документы для регистрации — не нужны\n"
            "- Принимаем учеников от 7 лет\n\n"
            "КОНТАКТЫ:\n"
            f"- {t['contact_phone']}\n"
            f"- {t['contact_email']}\n"
            f"- {t['contact_instagram']}\n"
            f"- {t['contact_location']}\n\n"
            "ЧАСТО ЗАДАВАЕМЫЕ ВОПРОСЫ:\n"
            f"Q: {t['faq_q1']}\nA: {t['faq_a1']}\n\n"
            f"Q: {t['faq_q2']}\nA: {t['faq_a2']}\n\n"
            f"Q: {t['faq_q3']}\nA: {t['faq_a3']}\n\n"
            f"Q: {t['faq_q4']}\nA: {t['faq_a4']}\n"
        )


async def _log_gpt_to_sheet(username: str, full_name: str, question: str, answer: str):
    if not spreadsheet:
        return
    try:
        try:
            log_sheet = spreadsheet.worksheet("GPT Logs")
        except gspread.exceptions.WorksheetNotFound:
            log_sheet = spreadsheet.add_worksheet(title="GPT Logs", rows=1000, cols=5)
            await asyncio.to_thread(log_sheet.append_row, ["Дата", "@username", "Имя", "Вопрос", "Ответ GPT"])
        await asyncio.to_thread(log_sheet.append_row, [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            f"@{username}" if username else "—",
            full_name,
            question,
            answer
        ])
    except Exception as e:
        logger.error(f"GPT log sheet error: {e}")


async def ask_chatgpt_rag(question: str, lang: str, username: str = "", full_name: str = "") -> str:
    if not client:
        return None
    try:
        context = _build_static_school_info(lang)
        if faq_sheet:
            try:
                all_rows = await asyncio.to_thread(faq_sheet.get_all_values)
                logger.info(f"FAQ loaded: {len(all_rows)} rows")

                question_lower = _strip_punct(question.lower())
                question_words = set(question_lower.split())
                # Убираем стоп-слова
                stop_words = {"а", "в", "и", "на", "по", "с", "у", "к", "о", "не", "за", "от", "до", "из", "для"}
                question_words -= stop_words

                relevant_answers = []
                for row in all_rows[1:]:
                    if len(row) >= 2 and row[0] and row[1]:
                        faq_words = set(_strip_punct(row[0].lower()).split()) - stop_words
                        common = question_words & faq_words
                        if len(common) >= 2:
                            relevant_answers.append(f"Q: {row[0]}\nA: {row[1]}")

                if relevant_answers:
                    context += "\n\nДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ ИЗ FAQ:\n\n" + "\n\n".join(relevant_answers)
                    logger.info(f"RAG: found {len(relevant_answers)} relevant answers")
                else:
                    # Берём весь FAQ как дополнительный контекст
                    all_qa = [f"Q: {r[0]}\nA: {r[1]}" for r in all_rows[1:] if len(r) >= 2 and r[0] and r[1]]
                    if all_qa:
                        context += "\n\nДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ:\n\n" + "\n\n".join(all_qa)
                    logger.info("RAG: using full FAQ as context")

            except Exception as e:
                logger.error(f"FAQ sheet read error: {e}")

        if lang == "ky":
            system_prompt = (
                "Сен Flow English School мектебинин жардамчысысың.\n\n"
                "МААНИЛҮҮ ЭРЕЖЕЛЕР:\n"
                "1. Төмөндөгү маалымат базасынан ГАНА жооп бер.\n"
                "2. Өз билимиңди же болжолдорду КОЛДОНБА.\n"
                "3. Эгер жооп базада болсо — аны ДАРОО ТЫК цитирле, кайра жазба, умтулба.\n"
                "4. Баа жөнүндө суроо болсо — БААЛАР бөлүмүнөн так сан менен жооп бер.\n"
                "5. Эгер базада маалымат жок болсо — так: \"Мен бул сурамга жооп бере албайм\" деп жооп бер.\n\n"
                f"МААЛЫМАТ БАЗАСЫ:\n{context}"
            )
        else:
            system_prompt = (
                "Ты помощник школы английского языка Flow English School.\n\n"
                "СТРОГИЕ ПРАВИЛА:\n"
                "1. Отвечай ТОЛЬКО на основе данных ниже.\n"
                "2. НЕ используй свои общие знания или домыслы.\n"
                "3. Если ответ есть в данных — процитируй его ТОЧНО с конкретными цифрами, не перефразируй уклончиво.\n"
                "4. На вопрос о ценах — всегда давай точные суммы из раздела ЦЕНЫ ниже.\n"
                "5. Никогда не отвечай «уточните у менеджера» если ответ есть в данных ниже.\n"
                "6. Если информации действительно нет в данных — ответь ТОЧНО: \"Я не знаю ответ на этот вопрос\".\n\n"
                f"ДАННЫЕ ШКОЛЫ:\n{context}"
            )

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            temperature=0.0,
            max_tokens=500
        )
        answer = response.choices[0].message.content.strip()
        logger.info(f"ChatGPT answer: {answer[:100]}...")
        await _log_gpt_to_sheet(username, full_name, question, answer)

        no_answer_phrases = ["я не знаю ответ на этот вопрос", "мен бул сурамга жооп бере албайм"]
        if any(p in answer.lower() for p in no_answer_phrases):
            return None

        return answer

    except Exception as e:
        logger.error(f"ChatGPT error: {e}")
        return None


# ===== ОБРАБОТЧИКИ =====

async def start(message: types.Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} started bot")
    await state.clear()
    await message.answer(TEXTS["ru"]["welcome"], reply_markup=get_language_keyboard())
    await state.set_state(RegistrationStates.waiting_for_language)


async def cancel_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")
    await state.update_data(editing=False)
    await message.answer(TEXTS[lang]["cancelled"])
    await show_main_menu(message, state, lang)


async def handle_language(message: types.Message, state: FSMContext):
    if "Русский" in message.text:
        lang = "ru"
    elif "Кыргызский" in message.text:
        lang = "ky"
    else:
        await message.answer(TEXTS["ru"]["choose_language"], reply_markup=get_language_keyboard())
        return

    await state.update_data(language=lang)
    await message.answer(TEXTS[lang]["want_register"], reply_markup=get_yes_no_keyboard(lang))
    await state.set_state(RegistrationStates.waiting_for_registration_choice)


async def handle_registration_choice(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    if TEXTS[lang]["yes"] in message.text:
        await message.answer(TEXTS[lang]["enter_name"], reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(RegistrationStates.waiting_for_name)
    else:
        await show_main_menu(message, state, lang)


async def handle_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    if not validate_name(message.text):
        await message.answer(TEXTS[lang]["invalid_name"])
        return

    await state.update_data(name=message.text.strip())

    # БАГ ИСПРАВЛЕН: если редактирование — возвращаемся к резюме
    if data.get("editing"):
        await state.update_data(editing=False)
        await show_summary(message, state)
    else:
        await message.answer(TEXTS[lang]["enter_phone"])
        await state.set_state(RegistrationStates.waiting_for_phone)


async def handle_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    if not validate_phone(message.text):
        await message.answer(TEXTS[lang]["invalid_phone"])
        return

    await state.update_data(phone=message.text.strip())

    if data.get("editing"):
        await state.update_data(editing=False)
        await show_summary(message, state)
    else:
        await message.answer(TEXTS[lang]["choose_level"], reply_markup=get_level_keyboard(lang))
        await state.set_state(RegistrationStates.waiting_for_level)


async def handle_level(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    if message.text.strip() == TEXTS[lang]["level_test"]:
        await message.answer(TEXTS[lang]["level_test_msg"], reply_markup=get_level_keyboard(lang))
        return

    await state.update_data(level=message.text.strip())

    if data.get("editing"):
        await state.update_data(editing=False)
        await show_summary(message, state)
    else:
        await message.answer(TEXTS[lang]["enter_time"], reply_markup=get_time_keyboard(lang))
        await state.set_state(RegistrationStates.waiting_for_time)


async def handle_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    time_keys = ["time_morning", "time_afternoon", "time_evening", "time_flexible"]
    valid_times = {TEXTS[lang][k] for k in time_keys}
    if message.text.strip() not in valid_times:
        await message.answer(TEXTS[lang]["invalid_time"], reply_markup=get_time_keyboard(lang))
        return

    await state.update_data(time=message.text.strip())

    if data.get("editing"):
        await state.update_data(editing=False)
        await show_summary(message, state)
    else:
        await message.answer(TEXTS[lang]["enter_goal"], reply_markup=get_goal_keyboard(lang))
        await state.set_state(RegistrationStates.waiting_for_goal)


async def handle_goal(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    goal_keys = ["goal_exam", "goal_conversation", "goal_business", "goal_general", "goal_other"]
    valid_goals = {TEXTS[lang][k] for k in goal_keys}
    if message.text.strip() not in valid_goals:
        await message.answer(TEXTS[lang]["invalid_goal"], reply_markup=get_goal_keyboard(lang))
        return

    await state.update_data(goal=message.text.strip())

    if data.get("editing"):
        await state.update_data(editing=False)
    await show_summary(message, state)


async def handle_edit_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    # БАГ ИСПРАВЛЕН: помечаем что идёт редактирование, а не новая анкета
    if callback.data == "edit_name":
        await state.update_data(editing=True)
        await callback.message.answer(TEXTS[lang]["enter_name"], reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(RegistrationStates.waiting_for_name)
    elif callback.data == "edit_phone":
        await state.update_data(editing=True)
        await callback.message.answer(TEXTS[lang]["enter_phone"], reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(RegistrationStates.waiting_for_phone)
    elif callback.data == "edit_level":
        await state.update_data(editing=True)
        await callback.message.answer(TEXTS[lang]["choose_level"], reply_markup=get_level_keyboard(lang))
        await state.set_state(RegistrationStates.waiting_for_level)
    elif callback.data == "edit_time":
        await state.update_data(editing=True)
        await callback.message.answer(TEXTS[lang]["enter_time"], reply_markup=get_time_keyboard(lang))
        await state.set_state(RegistrationStates.waiting_for_time)
    elif callback.data == "edit_goal":
        await state.update_data(editing=True)
        await callback.message.answer(TEXTS[lang]["enter_goal"], reply_markup=get_goal_keyboard(lang))
        await state.set_state(RegistrationStates.waiting_for_goal)
    elif callback.data == "confirm_registration":
        await confirm_registration(callback.message, state)

    await callback.answer()


async def confirm_registration(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    if sheet:
        try:
            await asyncio.to_thread(sheet.append_row, [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                data.get('name', ''),
                data.get('phone', ''),
                data.get('level', ''),
                data.get('time', ''),
                'Telegram',
                'Новая',
                data.get('goal', '')
            ])
            logger.info(f"Registration saved for {data.get('name')}")
        except Exception as e:
            logger.error(f"Google Sheets error: {e}")
            await message.answer(f"{TEXTS[lang]['sheets_error']}: {e}")
    else:
        await message.answer(TEXTS[lang]["sheets_not_configured"])

    if ADMIN_CHAT_ID:
        admin_text = (
            f"{TEXTS[lang]['admin_notification']}\n\n"
            f"{TEXTS[lang]['name']}: {data.get('name')}\n"
            f"{TEXTS[lang]['phone']}: {data.get('phone')}\n"
            f"{TEXTS[lang]['level']}: {data.get('level')}\n"
            f"{TEXTS[lang]['time']}: {data.get('time')}\n"
            f"{TEXTS[lang]['goal']}: {data.get('goal')}\n"
            f"Telegram ID: {message.chat.id}"
        )
        try:
            await message.bot.send_message(ADMIN_CHAT_ID, admin_text)
        except Exception as e:
            logger.error(f"Admin notify failed: {e}")

    await message.answer(TEXTS[lang]["success"])
    await show_main_menu(message, state, lang)


async def handle_main_menu(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")
    text = message.text
    if not text:
        return

    if TEXTS[lang]["faq"] in text:
        await message.answer(TEXTS[lang]["faq"], reply_markup=get_faq_keyboard(lang))
        await state.set_state(RegistrationStates.faq_view)

    elif TEXTS[lang]["ask_question"] in text:
        await message.answer(TEXTS[lang]["ask_question_text"])
        await state.set_state(RegistrationStates.ask_question)

    elif TEXTS[lang]["schedule"] in text:
        await message.answer(TEXTS[lang]["schedule_title"], reply_markup=get_schedule_keyboard(lang))
        await state.set_state(RegistrationStates.schedule_view)

    elif TEXTS[lang]["reviews"] in text:
        reviews_text = (
            f"{TEXTS[lang]['reviews_title']}\n\n"
            f"{TEXTS[lang]['review_1']}\n\n"
            f"{TEXTS[lang]['review_2']}\n\n"
            f"{TEXTS[lang]['review_3']}"
        )
        await message.answer(reviews_text, reply_markup=get_reviews_keyboard(lang))
        await state.set_state(RegistrationStates.reviews_view)

    elif TEXTS[lang]["prices"] in text:
        prices_text = (
            f"{TEXTS[lang]['prices_title']}\n\n"
            f"{TEXTS[lang]['price_1']}\n"
            f"{TEXTS[lang]['price_2']}\n"
            f"{TEXTS[lang]['price_3']}\n"
            f"{TEXTS[lang]['price_4']}"
        )
        await message.answer(prices_text, reply_markup=get_prices_keyboard(lang))
        await state.set_state(RegistrationStates.prices_view)

    elif TEXTS[lang]["contacts"] in text:
        lines = [TEXTS[lang]['contacts_title'], ""]
        for key in ["contact_phone", "contact_email", "contact_instagram", "contact_location"]:
            val = TEXTS[lang][key]
            if val:
                lines.append(val)
        contacts_text = "\n".join(lines)
        await message.answer(contacts_text, reply_markup=get_contacts_keyboard(lang))
        await state.set_state(RegistrationStates.contacts_view)

    elif TEXTS[lang]["register"] in text:
        await message.answer(TEXTS[lang]["enter_name"], reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(RegistrationStates.waiting_for_name)

    elif TEXTS[lang]["settings"] in text:
        await message.answer(TEXTS[lang]["main_menu"], reply_markup=get_settings_keyboard(lang))
        await state.set_state(RegistrationStates.settings_view)

    else:
        # Любой текст в главном меню — отправить в AI
        await message.bot.send_chat_action(message.chat.id, "typing")
        username = message.from_user.username or ""
        full_name = message.from_user.full_name or ""
        answer = await ask_chatgpt_rag(text, lang, username=username, full_name=full_name)
        if answer:
            await message.answer(answer)
        else:
            await message.answer(
                f"{TEXTS[lang]['ai_dont_know']}\n\n"
                f"{TEXTS[lang]['contact_phone']}\n"
                f"{TEXTS[lang]['contact_email']}"
            )


async def handle_ask_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")
    question_text = message.text.strip()

    if question_text in (TEXTS[lang]["back_to_menu"], TEXTS["ru"]["back_to_menu"], TEXTS["ky"]["back_to_menu"]):
        await show_main_menu(message, state, lang)
        return

    if len(question_text) < 3:
        await message.answer(TEXTS[lang]["invalid_question"])
        return

    if not client:
        await message.answer(
            f"{TEXTS[lang]['ai_unavailable']}\n\n{TEXTS[lang]['contact_phone']}\n{TEXTS[lang]['contact_email']}"
        )
        await show_main_menu(message, state, lang)
        return

    await message.bot.send_chat_action(message.chat.id, "typing")
    logger.info(f"Question from {message.from_user.id}: {question_text}")

    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    answer = await ask_chatgpt_rag(question_text, lang, username=username, full_name=full_name)

    if answer:
        await message.answer(answer)
    else:
        await message.answer(
            f"{TEXTS[lang]['ai_dont_know']}\n\n"
            f"{TEXTS[lang]['contact_phone']}\n"
            f"{TEXTS[lang]['contact_email']}\n"
            f"{TEXTS[lang]['contact_instagram']}"
        )

    await show_main_menu(message, state, lang)


async def handle_faq_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    faq_map = {
        "faq_1": ("faq_q1", "faq_a1"),
        "faq_2": ("faq_q2", "faq_a2"),
        "faq_3": ("faq_q3", "faq_a3"),
        "faq_4": ("faq_q4", "faq_a4"),
    }

    if callback.data in faq_map:
        q_key, a_key = faq_map[callback.data]
        await callback.message.answer(
            f"*{TEXTS[lang][q_key]}*\n\n{TEXTS[lang][a_key]}",
            reply_markup=get_faq_keyboard(lang),
            parse_mode="Markdown"
        )
    elif callback.data == "back_to_menu":
        await callback.message.answer(TEXTS[lang]["main_menu"], reply_markup=get_main_menu_keyboard(lang))
        await state.set_state(RegistrationStates.main_menu)

    await callback.answer()


async def handle_schedule_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    schedule_map = {
        "schedule_mon": f"{TEXTS[lang]['monday']}: 10:00 (Beginner), 14:00 (Intermediate), 18:00 (Upper)",
        "schedule_tue": f"{TEXTS[lang]['tuesday']}: 09:00 (Elementary), 15:00 (Intermediate), 19:00 (Beginner)",
        "schedule_wed": f"{TEXTS[lang]['wednesday']}: 11:00 (Beginner), 16:00 (Upper), 20:00 (Elementary)",
        "schedule_thu": f"{TEXTS[lang]['thursday']}: 10:00 (Intermediate), 14:30 (Beginner), 18:30 (Upper)",
        "schedule_fri": f"{TEXTS[lang]['friday']}: 09:30 (Upper), 13:00 (Elementary), 17:00 (Intermediate)",
        "schedule_sat": f"{TEXTS[lang]['saturday']}: 10:00 (Beginner), 12:00 (Intermediate), 14:00 (Upper)",
        "schedule_sun": f"{TEXTS[lang]['sunday']}: 11:00 (Elementary), 15:00 (Beginner), 18:00 (Intermediate)",
    }

    if callback.data in schedule_map:
        await callback.message.answer(schedule_map[callback.data], reply_markup=get_schedule_keyboard(lang))
    elif callback.data == "back_to_menu":
        await callback.message.answer(TEXTS[lang]["main_menu"], reply_markup=get_main_menu_keyboard(lang))
        await state.set_state(RegistrationStates.main_menu)

    await callback.answer()


async def handle_reviews_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    if callback.data == "register":
        await callback.message.answer(TEXTS[lang]["enter_name"], reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(RegistrationStates.waiting_for_name)
    elif callback.data == "back_to_menu":
        await callback.message.answer(TEXTS[lang]["main_menu"], reply_markup=get_main_menu_keyboard(lang))
        await state.set_state(RegistrationStates.main_menu)

    await callback.answer()


async def handle_prices_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    if callback.data == "register":
        await callback.message.answer(TEXTS[lang]["enter_name"], reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(RegistrationStates.waiting_for_name)
    elif callback.data == "back_to_menu":
        await callback.message.answer(TEXTS[lang]["main_menu"], reply_markup=get_main_menu_keyboard(lang))
        await state.set_state(RegistrationStates.main_menu)

    await callback.answer()


async def handle_contacts_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")

    if callback.data == "call_admin":
        await callback.message.answer(f"{TEXTS[lang]['contact_phone']}")
    elif callback.data == "back_to_menu":
        await callback.message.answer(TEXTS[lang]["main_menu"], reply_markup=get_main_menu_keyboard(lang))
        await state.set_state(RegistrationStates.main_menu)

    await callback.answer()


async def handle_settings_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "change_language":
        await callback.message.answer(TEXTS["ru"]["choose_language"], reply_markup=get_language_keyboard())
        await state.set_state(RegistrationStates.waiting_for_language)
    elif callback.data == "back_to_menu":
        data = await state.get_data()
        lang = data.get("language", "ru")
        await callback.message.answer(TEXTS[lang]["main_menu"], reply_markup=get_main_menu_keyboard(lang))
        await state.set_state(RegistrationStates.main_menu)

    await callback.answer()


async def ask_command(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "ru")
    await message.answer(TEXTS[lang]["ask_question_text"])
    await state.set_state(RegistrationStates.ask_question)


async def help_command(message: types.Message):
    help_text = (
        "ℹ️ *Справка по боту*\n\n"
        "Этот бот помогает записаться на пробный урок в Flow English School "
        "и отвечает на вопросы о школе.\n\n"
        "*Доступные команды:*\n"
        "/start — перезапустить бота\n"
        "/ask — задать вопрос AI напрямую\n"
        "/help — эта справка\n\n"
        "*Кнопки меню:*\n"
        "📖 F.A.Q — частые вопросы\n"
        "✨ Задать вопрос — AI-ответ по базе школы\n"
        "🎫 Записаться — запись на пробный урок\n"
        "💛 Цены — прайс-лист\n"
        "🗓 Расписание — время занятий\n"
        "👑 Отзывы — отзывы студентов\n"
        "📌 Контакты — как с нами связаться\n"
        "🪞 Настройки — смена языка"
    )
    await message.answer(help_text, parse_mode="Markdown")


async def stats_command(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID and message.chat.id != ADMIN_CHAT_ID:
        await message.answer("❌ Команда доступна только администратору.")
        return

    if not sheet:
        await message.answer("Google Sheets не подключён — статистика недоступна.")
        return

    try:
        all_rows = await asyncio.to_thread(sheet.get_all_values)
        total = max(0, len(all_rows) - 1)  # минус заголовок

        # Считаем регистрации за сегодня
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = sum(1 for r in all_rows[1:] if r and r[0].startswith(today))

        stats_text = (
            f"📊 *Статистика регистраций*\n\n"
            f"Всего: *{total}*\n"
            f"Сегодня: *{today_count}*"
        )
        await message.answer(stats_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await message.answer(f"Ошибка получения статистики: {e}")


async def handle_unknown_callback(callback: types.CallbackQuery):
    logger.warning(f"Unknown callback: {callback.data} from {callback.from_user.id}")
    await callback.answer("Неизвестная команда", show_alert=True)


# ===== БОТ И DISPATCHER =====
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Команды
dp.message.register(start, Command("start"))
dp.message.register(ask_command, Command("ask"))
dp.message.register(help_command, Command("help"))
dp.message.register(stats_command, Command("stats"))

# Отмена в процессе регистрации
_cancel_texts = F.text.in_({"✖ Отмена", "✖ Жокко чыгаруу"})
_cancel_states = [
    RegistrationStates.waiting_for_name,
    RegistrationStates.waiting_for_phone,
    RegistrationStates.waiting_for_level,
    RegistrationStates.waiting_for_time,
    RegistrationStates.waiting_for_goal,
    RegistrationStates.registration_summary,
]
for _st in _cancel_states:
    dp.message.register(cancel_handler, _st, _cancel_texts)

# Выбор языка и старт
dp.message.register(handle_language, RegistrationStates.waiting_for_language)
dp.message.register(handle_registration_choice, RegistrationStates.waiting_for_registration_choice)

# Шаги регистрации
dp.message.register(handle_name, RegistrationStates.waiting_for_name)
dp.message.register(handle_phone, RegistrationStates.waiting_for_phone)
dp.message.register(handle_level, RegistrationStates.waiting_for_level)
dp.message.register(handle_time, RegistrationStates.waiting_for_time)
dp.message.register(handle_goal, RegistrationStates.waiting_for_goal)

# Главное меню
dp.message.register(handle_main_menu, RegistrationStates.main_menu)

# AI вопросы
dp.message.register(handle_ask_question, RegistrationStates.ask_question)

# БАГ ИСПРАВЛЕН: handle_main_menu работает из любого раздела-просмотра
# Если пользователь нажимает кнопку меню находясь в FAQ/цены/расписание — бот реагирует
_view_states = [
    RegistrationStates.faq_view,
    RegistrationStates.schedule_view,
    RegistrationStates.reviews_view,
    RegistrationStates.prices_view,
    RegistrationStates.contacts_view,
    RegistrationStates.settings_view,
]
for _st in _view_states:
    dp.message.register(handle_main_menu, _st)

# Callbacks
dp.callback_query.register(handle_edit_callback, RegistrationStates.registration_summary)
dp.callback_query.register(handle_faq_callback, RegistrationStates.faq_view)
dp.callback_query.register(handle_schedule_callback, RegistrationStates.schedule_view)
dp.callback_query.register(handle_reviews_callback, RegistrationStates.reviews_view)
dp.callback_query.register(handle_prices_callback, RegistrationStates.prices_view)
dp.callback_query.register(handle_contacts_callback, RegistrationStates.contacts_view)
dp.callback_query.register(handle_settings_callback, RegistrationStates.settings_view)
dp.callback_query.register(handle_unknown_callback)


async def main():
    logger.info("Bot started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
