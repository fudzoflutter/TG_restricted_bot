import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ContentType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BusinessConnection,
    BusinessMessagesDeleted,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    TelegramObject,
    FSInputFile,
)

import config
import database as db
from locales import t

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

SAVE_TRIGGERS = {"!", ".", "+", "save", "сохранить", "сейв", "/save", "s", "с"}
BOT_USERNAME = ""

try:
    from aiogram.enums import ButtonStyle
    STYLE_SUCCESS = ButtonStyle.SUCCESS
    STYLE_PRIMARY = ButtonStyle.PRIMARY
    STYLE_DANGER = ButtonStyle.DANGER
except Exception:
    STYLE_SUCCESS = "success"
    STYLE_PRIMARY = "primary"
    STYLE_DANGER = "danger"

# Official custom-emoji IDs (Bot API HTML <tg-emoji>). Animated if bot owner has Premium.
E_WAVE = "5312241539987038474"
E_SPY = "5924490652745212033"
E_SHIELD = "5924649605189869607"
E_FIRE = "5931801052155222589"
E_CHECK = "5274232449511988793"
E_GEAR = "5276246852666758580"
E_CHART = "5377312262123803976"
E_LANG = "5413704112220949842"
E_SAVE = "5271600761883117622"


def ae(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if isinstance(event, Message) and event.business_connection_id:
            return await handler(event, data)
        if user is None:
            return await handler(event, data)
        if await db.is_allowed(user.id):
            return await handler(event, data)
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            await event.answer(t("uz", "access_denied"))
        elif isinstance(event, CallbackQuery):
            await event.answer("⛔️", show_alert=True)
        return None


dp.message.middleware(AccessMiddleware())
dp.callback_query.middleware(AccessMiddleware())


def kb(
    text: str,
    style: Optional[str] = None,
    icon: Optional[str] = None,
) -> KeyboardButton:
    kwargs: Dict[str, Any] = {"text": text}
    if style:
        kwargs["style"] = style
    if icon:
        kwargs["icon_custom_emoji_id"] = icon
    return KeyboardButton(**kwargs)


def get_main_menu_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    if lang == "en":
        rows = [
            [kb("Connect", STYLE_SUCCESS, E_CHECK), kb("How does the bot work?", STYLE_PRIMARY, E_SPY)],
            [kb("Statistics", STYLE_PRIMARY, E_CHART), kb("Settings", STYLE_PRIMARY, E_GEAR)],
            [kb("Language", icon=E_LANG), kb("Save Mode", STYLE_PRIMARY, E_SAVE)],
        ]
    elif lang == "uz":
        rows = [
            [kb("Ulash", STYLE_SUCCESS, E_CHECK), kb("Bot qanday ishlaydi?", STYLE_PRIMARY, E_SPY)],
            [kb("Statistika", STYLE_PRIMARY, E_CHART), kb("Sozlamalar", STYLE_PRIMARY, E_GEAR)],
            [kb("Til", icon=E_LANG), kb("Saqlash rejimi", STYLE_PRIMARY, E_SAVE)],
        ]
    else:
        rows = [
            [kb("Подключить", STYLE_SUCCESS, E_CHECK), kb("Как работает бот?", STYLE_PRIMARY, E_SPY)],
            [kb("Статистика", STYLE_PRIMARY, E_CHART), kb("Настройки", STYLE_PRIMARY, E_GEAR)],
            [kb("Язык", icon=E_LANG), kb("Режим сохр.", STYLE_PRIMARY, E_SAVE)],
        ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=False)


def format_sender_header(cached: Any, settings: Dict[str, Any], lang: str) -> str:
    lines = []
    fname = cached.get("sender_first_name", "")
    lname = cached.get("sender_last_name", "")
    uname = cached.get("sender_username", "")
    uid = cached.get("sender_id", 0)

    if (settings["show_first_name"] and fname) or (settings["show_last_name"] and lname):
        name_parts = []
        if settings["show_first_name"] and fname:
            name_parts.append(fname)
        if settings["show_last_name"] and lname:
            name_parts.append(lname)
        label = t(lang, "btn_show_fname")
        lines.append(f"👤 <b>{label}:</b> {' '.join(name_parts)}")

    if settings["show_username"] and uname:
        lines.append(f"🔗 <b>Username:</b> @{uname}")

    if settings["show_user_id"] and uid:
        lines.append(f"🆔 <b>ID:</b> <code>{uid}</code>")

    if not lines:
        lines.append(f"🆔 <b>ID:</b> <code>{uid}</code>")

    return "\n".join(lines)


def make_topic_title(chat: Any) -> str:
    if chat.title:
        return f"{chat.title[:100]} [{chat.id}]"
    parts = [p for p in [chat.first_name, chat.last_name] if p]
    if chat.username:
        parts.append(f"(@{chat.username})")
    full_name = " ".join(parts)
    return f"{full_name[:100]} [{chat.id}]" if full_name else f"User [{chat.id}]"


async def get_or_create_pm_thread(owner_id: int, business_chat: Any) -> Optional[int]:
    st = await db.get_user_settings(owner_id)
    if not st["threaded_mode"]:
        return None
    thread_id = await db.get_user_topic(owner_id, business_chat.id)
    if thread_id:
        return thread_id
    topic_title = make_topic_title(business_chat)
    try:
        topic = await bot.create_forum_topic(chat_id=owner_id, name=topic_title)
        await db.save_user_topic(owner_id, business_chat.id, topic.message_thread_id, topic_title)
        return topic.message_thread_id
    except TelegramBadRequest as e:
        logging.warning(f"Failed to create forum topic: {e}")
        return None


async def send_to_owner(owner_id: int, business_chat: Any, send_func, **kwargs):
    thread_id = await get_or_create_pm_thread(owner_id, business_chat)
    try:
        return await send_func(chat_id=owner_id, message_thread_id=thread_id, **kwargs)
    except TelegramBadRequest as e:
        if any(err in str(e).lower() for err in ["topic", "thread"]):
            topic_title = make_topic_title(business_chat)
            try:
                new_topic = await bot.create_forum_topic(chat_id=owner_id, name=topic_title)
                await db.save_user_topic(owner_id, business_chat.id, new_topic.message_thread_id, topic_title)
                return await send_func(chat_id=owner_id, message_thread_id=new_topic.message_thread_id, **kwargs)
            except Exception:
                pass
        return await send_func(chat_id=owner_id, message_thread_id=None, **kwargs)


async def dispatch_media_message(owner_id: int, chat: Any, content_type: str, file_id: str, caption: Optional[str] = None):
    if content_type in ("photo", ContentType.PHOTO):
        return await send_to_owner(owner_id, chat, bot.send_photo, photo=file_id, caption=caption)
    if content_type in ("video", ContentType.VIDEO):
        return await send_to_owner(owner_id, chat, bot.send_video, video=file_id, caption=caption)
    if content_type in ("voice", ContentType.VOICE):
        return await send_to_owner(owner_id, chat, bot.send_voice, voice=file_id, caption=caption)
    if content_type in ("video_note", ContentType.VIDEO_NOTE):
        return await send_to_owner(owner_id, chat, bot.send_video_note, video_note=file_id)
    if content_type in ("audio", ContentType.AUDIO):
        return await send_to_owner(owner_id, chat, bot.send_audio, audio=file_id, caption=caption)
    if content_type in ("document", ContentType.DOCUMENT):
        return await send_to_owner(owner_id, chat, bot.send_document, document=file_id, caption=caption)
    if content_type in ("animation", ContentType.ANIMATION):
        return await send_to_owner(owner_id, chat, bot.send_animation, animation=file_id, caption=caption)
    if content_type in ("sticker", ContentType.STICKER):
        return await send_to_owner(owner_id, chat, bot.send_sticker, sticker=file_id)
    return None


def ib(
    text: str,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
    style: Optional[str] = None,
    icon: Optional[str] = None,
) -> InlineKeyboardButton:
    kwargs: Dict[str, Any] = {"text": text}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url
    if style:
        kwargs["style"] = style
    if icon:
        kwargs["icon_custom_emoji_id"] = icon
    return InlineKeyboardButton(**kwargs)


def get_settings_keyboard(st: Dict[str, Any]) -> InlineKeyboardMarkup:
    lang = st["language"]
    th_status = t(lang, "status_on") if st["threaded_mode"] else t(lang, "status_off")
    save_m_text = t(lang, "btn_mode_trigger") if st["save_media_mode"] == "trigger" else t(lang, "btn_mode_all")
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(t(lang, "btn_header"), callback_data="menu_header", style=STYLE_PRIMARY, icon=E_SPY)],
        [ib(
            f"{t(lang, 'btn_threads')}: {th_status}",
            callback_data="toggle_threaded",
            style=STYLE_SUCCESS if st["threaded_mode"] else STYLE_DANGER,
        )],
        [ib(f"{t(lang, 'btn_save_mode')}: {save_m_text}", callback_data="menu_save_mode", style=STYLE_PRIMARY, icon=E_SAVE)],
        [ib(t(lang, "btn_lang"), callback_data="menu_lang", icon=E_LANG)],
    ])


def get_header_keyboard(st: Dict[str, Any]) -> InlineKeyboardMarkup:
    lang = st["language"]

    def btn_txt(name, val):
        return f"{name}: {t(lang, 'status_on') if val else t(lang, 'status_off')}"

    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(btn_txt(t(lang, "btn_show_fname"), st["show_first_name"]), callback_data="toggle_hdr_first_name")],
        [ib(btn_txt(t(lang, "btn_show_lname"), st["show_last_name"]), callback_data="toggle_hdr_last_name")],
        [ib(btn_txt(t(lang, "btn_show_uname"), st["show_username"]), callback_data="toggle_hdr_username")],
        [ib(btn_txt(t(lang, "btn_show_id"), st["show_user_id"]), callback_data="toggle_hdr_user_id")],
        [ib(t(lang, "btn_back"), callback_data="menu_main")],
    ])


def get_save_mode_keyboard(st: Dict[str, Any]) -> InlineKeyboardMarkup:
    lang = st["language"]
    cur = st["save_media_mode"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(
            t(lang, "btn_mode_trigger"),
            callback_data="set_smode_trigger",
            style=STYLE_SUCCESS if cur == "trigger" else STYLE_PRIMARY,
        )],
        [ib(
            t(lang, "btn_mode_all"),
            callback_data="set_smode_all",
            style=STYLE_SUCCESS if cur == "all" else STYLE_PRIMARY,
        )],
        [ib(t(lang, "btn_back"), callback_data="menu_main")],
    ])


def get_lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib("🇷🇺 Русский", callback_data="set_lang_ru")],
        [ib("🇬🇧 English", callback_data="set_lang_en")],
        [ib("🇺🇿 O'zbekcha", callback_data="set_lang_uz")],
        [ib("⬅️ Back / Назад", callback_data="menu_main")],
    ])


def connect_keyboard() -> InlineKeyboardMarkup:
    # tg://settings/edit → profil tahrirlash (Chatbots shu yerda).
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib("Connect", url="tg://settings/edit", style=STYLE_SUCCESS, icon=E_CHECK)],
    ])


def how_it_works_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "uz":
        back = "⬅️ Orqaga"
    elif lang == "en":
        back = "⬅️ Back"
    else:
        back = "⬅️ Назад"
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(back, callback_data="back_start")],
    ])


def welcome_caption(lang: str) -> str:
    bot_mention = f"@{BOT_USERNAME}" if BOT_USERNAME else "bot"
    if lang == "en":
        return (
            f"{ae(E_WAVE, '👋')} Welcome!\n\n"
            f"{ae(E_SPY, '🕵️')} I catch deleted and edited messages\n"
            "and save photos, videos, voice, video notes and view-once media.\n\n"
            f"{ae(E_SHIELD, '🔒')} Each user only sees their own chats.\n\n"
            "Connect:\n"
            "1\ufe0f\u20e3 Tap Connect (opens Profile → Edit)\n"
            "2\ufe0f\u20e3 Chatbots / Chat Automation\n"
            f"3\ufe0f\u20e3 Add {bot_mention}\n\n"
            f"{ae(E_FIRE, '🛠')} Tools are on the keyboard below."
        )
    if lang == "uz":
        return (
            f"{ae(E_WAVE, '👋')} Xush kelibsiz!\n\n"
            f"{ae(E_SPY, '🕵️')} O'chirilgan va tahrirlangan xabarlarni ushlayman,\n"
            "rasm, video, ovoz, video-xabar va bir martalik medialarni saqlayman.\n\n"
            f"{ae(E_SHIELD, '🔒')} Har bir foydalanuvchi faqat o'z chatlarini ko'radi.\n\n"
            "Ulash:\n"
            "1\ufe0f\u20e3 Connect — profil tahrirlash (Edit)\n"
            "2\ufe0f\u20e3 Chatbots / Chat Automation\n"
            f"3\ufe0f\u20e3 {bot_mention} ni qo'shing\n\n"
            f"{ae(E_FIRE, '🛠')} Qurollar pastda."
        )
    return (
        f"{ae(E_WAVE, '👋')} Добро пожаловать!\n\n"
        f"{ae(E_SPY, '🕵️')} Ловлю удалённые и отредактированные сообщения,\n"
        "фото, видео, голосовые, кружки и одноразовые медиа.\n\n"
        f"{ae(E_SHIELD, '🔒')} Каждый пользователь видит только свои чаты.\n\n"
        "Подключение:\n"
        "1\ufe0f\u20e3 Connect — редактирование профиля (Edit)\n"
        "2\ufe0f\u20e3 Chatbots / Chat Automation\n"
        f"3\ufe0f\u20e3 Добавьте {bot_mention}\n\n"
        f"{ae(E_FIRE, '🛠')} Инструменты внизу."
    )


async def send_welcome(bot_instance, chat_id: int, lang: str):
    photo_path = FSInputFile("mooodypic.jpg")
    markup = connect_keyboard()
    try:
        return await bot_instance.send_photo(
            chat_id, photo=photo_path, caption=welcome_caption(lang), reply_markup=markup,
        )
    except TelegramBadRequest:
        if BOT_USERNAME:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [ib("Connect", url=f"https://t.me/{BOT_USERNAME}?startattach", style=STYLE_SUCCESS, icon=E_CHECK)],
            ])
        return await bot_instance.send_photo(
            chat_id, photo=photo_path, caption=welcome_caption(lang), reply_markup=markup,
        )


def how_it_works_text(lang: str) -> str:
    if lang == "en":
        return (
            f"{ae(E_SPY, '😎')} <b>How does the bot work?</b>\n\n"
            "1. Open <b>Settings → Edit profile</b> (Connect button)\n"
            "2. Chatbots / Chat Automation — add this bot\n"
            "3. Deleted/edited messages and media are sent only to you\n"
            "4. View-once photos/videos are cached immediately\n\n"
            "⚡️ Real-time, even offline\n"
            "🔐 Isolated per user"
        )
    if lang == "uz":
        return (
            f"{ae(E_SPY, '😎')} <b>Bot qanday ishlaydi?</b>\n\n"
            "1. <b>Sozlamalar → Profilni tahrirlash</b> (Connect)\n"
            "2. Chatbots / Chat Automation — botni qo'shing\n"
            "3. O'chirilgan/tahrirlangan xabarlar faqat sizga ketadi\n"
            "4. Bir martalik media darhol keshga tushadi\n\n"
            "⚡️ Real vaqt, oflayn ham\n"
            "🔐 Ma'lumot aralashmaydi"
        )
    return (
        f"{ae(E_SPY, '😎')} <b>Как работает бот?</b>\n\n"
        "1. <b>Настройки → Редактировать профиль</b> (Connect)\n"
        "2. Chatbots / Chat Automation — добавьте бота\n"
        "3. Удалённые/изменённые сообщения приходят только вам\n"
        "4. Одноразовые медиа сразу кэшируются\n\n"
        "⚡️ В реальном времени, даже офлайн\n"
        "🔐 Данные не смешиваются"
    )


@dp.message(CommandStart())
async def cmd_start(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    lang = st["language"]

    if await db.has_connection(msg.from_user.id):
        text = (
            "✅ <b>Bot is already connected and working!</b>\n"
            "I'm catching deleted/edited messages in your chats."
            if lang == "en" else
            "✅ <b>Bot allaqachon ulangan va ishlayapti!</b>\n"
            "Men sizning chatlaringizdagi o'chirilgan/tahrirlangan xabarlarni ushlayapman."
            if lang == "uz" else
            "✅ <b>Бот уже подключен и работает!</b>\n"
            "Я перехватываю удалённые/отредактированные сообщения в ваших чатах."
        )
        await msg.answer(text, reply_markup=get_main_menu_keyboard(lang))
        return

    await send_welcome(bot, msg.chat.id, lang)
    tools_txt = (
        "🛠 The tools below are always available." if lang == "en"
        else "🛠 Quyidagi qurollar doim mavjud." if lang == "uz"
        else "🛠 Инструменты ниже всегда доступны."
    )
    await msg.answer(tools_txt, reply_markup=get_main_menu_keyboard(lang))


def _parse_uid(text: str) -> Optional[int]:
    parts = (text or "").split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


@dp.message(Command("allow"))
async def cmd_allow(msg: Message):
    if not db.is_admin(msg.from_user.id):
        await msg.answer(t((await db.get_user_settings(msg.from_user.id))["language"], "admin_only"))
        return
    uid = _parse_uid(msg.text or "")
    lang = (await db.get_user_settings(msg.from_user.id))["language"]
    if not uid:
        await msg.answer(t(lang, "need_uid"))
        return
    await db.allow_user(uid, msg.from_user.id)
    await msg.answer(t(lang, "allowed_ok").format(uid=uid))


@dp.message(Command("deny"))
async def cmd_deny(msg: Message):
    if not db.is_admin(msg.from_user.id):
        await msg.answer(t((await db.get_user_settings(msg.from_user.id))["language"], "admin_only"))
        return
    uid = _parse_uid(msg.text or "")
    lang = (await db.get_user_settings(msg.from_user.id))["language"]
    if not uid:
        await msg.answer(t(lang, "need_uid").replace("/allow", "/deny"))
        return
    await db.deny_user(uid)
    await msg.answer(t(lang, "denied_ok").format(uid=uid))


@dp.message(Command("allowed"))
async def cmd_allowed(msg: Message):
    if not db.is_admin(msg.from_user.id):
        await msg.answer(t((await db.get_user_settings(msg.from_user.id))["language"], "admin_only"))
        return
    ids = await db.list_allowed()
    lang = (await db.get_user_settings(msg.from_user.id))["language"]
    lines = "\n".join(f"• <code>{i}</code>" + (" (admin)" if db.is_admin(i) else "") for i in ids)
    await msg.answer(t(lang, "allowed_list").format(list=lines or "—"))


@dp.message(Command("settings"))
async def cmd_settings(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    await msg.answer(t(st["language"], "settings_title"), reply_markup=get_settings_keyboard(st))


@dp.message(Command("menu"))
async def cmd_menu(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    lang = st["language"]
    await msg.answer(
        "🛠 Menu" if lang == "en" else "🛠 Menyu",
        reply_markup=get_main_menu_keyboard(lang),
    )


CONNECT_TEXTS = {"Ulash", "Connect", "Подключить"}
HOW_TEXTS = {"Bot qanday ishlaydi?", "How does the bot work?", "Как работает бот?"}
STATS_TEXTS = {"Statistika", "Statistics", "Статистика"}
SETTINGS_TEXTS = {"Sozlamalar", "Settings", "Настройки"}
LANG_TEXTS = {"Til", "Language", "Язык"}
SAVE_MODE_TEXTS = {"Saqlash rejimi", "Save Mode", "Режим сохр."}


@dp.message(F.text.in_(CONNECT_TEXTS))
async def btn_connect(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    lang = st["language"]
    mention = f"@{BOT_USERNAME}" if BOT_USERNAME else "bot"
    text = (
        "🟢 <b>To connect:</b>\n\n"
        "1️⃣ Tap <b>Connect</b> → Profile Edit\n"
        f"2️⃣ Add <b>{mention}</b> in Chatbots ✅"
        if lang == "en" else
        "🟢 <b>Ulash:</b>\n\n"
        "1️⃣ <b>Connect</b> — profil tahrirlash\n"
        f"2️⃣ Chatbots da <b>{mention}</b> ni qo'shing ✅"
        if lang == "uz" else
        "🟢 <b>Подключение:</b>\n\n"
        "1️⃣ <b>Connect</b> — редактирование профиля\n"
        f"2️⃣ В Chatbots добавьте <b>{mention}</b> ✅"
    )
    await msg.answer(text, reply_markup=connect_keyboard())


@dp.message(F.text.in_(HOW_TEXTS))
async def btn_how(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    lang = st["language"]
    await msg.answer(how_it_works_text(lang), reply_markup=how_it_works_keyboard(lang))


@dp.message(F.text.in_(STATS_TEXTS))
async def btn_stats(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    lang = st["language"]
    text = (
        "📊 <b>Statistics</b>\n\nNo statistics yet."
        if lang == "en" else
        "📊 <b>Statistika</b>\n\nHozircha statistika yo'q."
        if lang == "uz" else
        "📊 <b>Статистика</b>\n\nПока нет данных."
    )
    await msg.answer(text)


@dp.message(F.text.in_(SETTINGS_TEXTS))
async def btn_settings(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    await msg.answer(t(st["language"], "settings_title"), reply_markup=get_settings_keyboard(st))


@dp.message(F.text.in_(LANG_TEXTS))
async def btn_lang(msg: Message):
    await msg.answer("🌐", reply_markup=get_lang_keyboard())


@dp.message(F.text.in_(SAVE_MODE_TEXTS))
async def btn_save_mode(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    await msg.answer(t(st["language"], "save_mode_title"), reply_markup=get_save_mode_keyboard(st))


@dp.callback_query(F.data == "back_start")
async def cb_back_start(call: CallbackQuery):
    st = await db.get_user_settings(call.from_user.id)
    lang = st["language"]
    try:
        await call.message.edit_text(how_it_works_text(lang), reply_markup=how_it_works_keyboard(lang))
    except TelegramBadRequest:
        await send_welcome(bot, call.message.chat.id, lang)
    await call.answer()


@dp.callback_query(F.data.startswith("menu_"))
async def cb_menus(call: CallbackQuery):
    st = await db.get_user_settings(call.from_user.id)
    lang = st["language"]
    menu = call.data.split("_")[1]
    if menu == "main":
        await call.message.edit_text(t(lang, "settings_title"), reply_markup=get_settings_keyboard(st))
    elif menu == "header":
        await call.message.edit_text(t(lang, "hdr_settings_title"), reply_markup=get_header_keyboard(st))
    elif menu == "lang":
        await call.message.edit_text(t(lang, "lang_settings_title"), reply_markup=get_lang_keyboard())
    elif menu == "save":
        await call.message.edit_text(t(lang, "save_mode_title"), reply_markup=get_save_mode_keyboard(st))
    await call.answer()


@dp.callback_query(F.data.startswith("set_smode_"))
async def cb_set_save_mode(call: CallbackQuery):
    mode = call.data.replace("set_smode_", "")
    await db.update_user_setting(call.from_user.id, "save_media_mode", mode)
    st = await db.get_user_settings(call.from_user.id)
    await call.message.edit_text(t(st["language"], "save_mode_title"), reply_markup=get_save_mode_keyboard(st))
    await call.answer()


@dp.callback_query(F.data.startswith("toggle_hdr_"))
async def cb_toggle_hdr(call: CallbackQuery):
    field = call.data.replace("toggle_hdr_", "show_")
    st = await db.get_user_settings(call.from_user.id)
    new_val = not st[field]
    await db.update_user_setting(call.from_user.id, field, new_val)
    st[field] = new_val
    await call.message.edit_reply_markup(reply_markup=get_header_keyboard(st))
    await call.answer()


@dp.callback_query(F.data == "toggle_threaded")
async def cb_toggle_threaded(call: CallbackQuery):
    st = await db.get_user_settings(call.from_user.id)
    new_val = not st["threaded_mode"]
    await db.update_user_setting(call.from_user.id, "threaded_mode", new_val)
    st["threaded_mode"] = new_val
    await call.message.edit_reply_markup(reply_markup=get_settings_keyboard(st))
    await call.answer()


@dp.callback_query(F.data.startswith("set_lang_"))
async def cb_set_lang(call: CallbackQuery):
    lang = call.data.split("_")[2]
    await db.update_user_setting(call.from_user.id, "language", lang)
    st = await db.get_user_settings(call.from_user.id)
    await call.message.edit_text(t(lang, "settings_title"), reply_markup=get_settings_keyboard(st))
    await call.answer()


@dp.message(F.forum_topic_edited)
async def on_topic_edited(msg: Message):
    await db.update_user_topic_name(msg.chat.id, msg.message_thread_id, msg.forum_topic_edited.name)


@dp.business_connection()
async def on_business_connection(conn: BusinessConnection):
    if not await db.is_allowed(conn.user.id):
        st = await db.get_user_settings(conn.user.id)
        try:
            await bot.send_message(conn.user.id, t(st["language"], "not_allowed_connect"))
        except Exception:
            pass
        return
    if conn.is_enabled:
        await db.save_connection(conn.id, conn.user.id)
        st = await db.get_user_settings(conn.user.id)
        lang = st["language"]
        text = (
            "✅ <b>Successfully connected!</b>\nI'm now catching deleted/edited messages in your chats."
            if lang == "en" else
            "✅ <b>Muvaffaqiyatli ulandi!</b>\nEndi chatlaringizdagi o'chirilgan/tahrirlangan xabarlarni ushlayman."
            if lang == "uz" else
            "✅ <b>Успешно подключено!</b>\nТеперь я перехватываю удалённые/отредактированные сообщения в ваших чатах."
        )
        try:
            await bot.send_message(conn.user.id, text, reply_markup=get_main_menu_keyboard(lang))
        except Exception:
            pass


async def _deliver_protected_media(owner_id: int, msg: Message, file_id: str, content_type: str):
    st = await db.get_user_settings(owner_id)
    lang = st["language"]
    author_data = {
        "sender_first_name": msg.from_user.first_name if msg.from_user else "",
        "sender_last_name": msg.from_user.last_name if msg.from_user else "",
        "sender_username": msg.from_user.username if msg.from_user else "",
        "sender_id": msg.from_user.id if msg.from_user else 0,
    }
    caption = f"{t(lang, 'saved_media_title')}\n{format_sender_header(author_data, st, lang)}"
    if msg.caption:
        caption += f"\n💬 <b>{t(lang, 'caption_label')}</b> {msg.caption}"
    try:
        sent = await dispatch_media_message(owner_id, msg.chat, content_type, file_id, caption)
        if sent and content_type == "video_note":
            await sent.reply(caption)
    except Exception as e:
        logging.error(f"protected media deliver error: {e}")


@dp.business_message()
async def on_business_message(msg: Message):
    owner_id = await db.get_owner_by_connection(msg.business_connection_id)
    if not owner_id or not await db.is_allowed(owner_id):
        return

    await db.cache_message(msg, owner_id)

    content_type, file_id = db.extract_media(msg)
    if file_id and getattr(msg, "has_protected_content", False):
        asyncio.create_task(_deliver_protected_media(owner_id, msg, file_id, content_type))

    if not msg.reply_to_message:
        return
    replied = msg.reply_to_message
    if not (msg.from_user and msg.from_user.id == owner_id):
        return

    st = await db.get_user_settings(owner_id)
    user_text = (msg.text or "").strip().lower()
    if st["save_media_mode"] == "trigger" and user_text not in SAVE_TRIGGERS:
        return

    _, rfile = db.extract_media(replied)
    if not rfile:
        return
    lang = st["language"]
    author_data = {
        "sender_first_name": replied.from_user.first_name if replied.from_user else "",
        "sender_last_name": replied.from_user.last_name if replied.from_user else "",
        "sender_username": replied.from_user.username if replied.from_user else "",
        "sender_id": replied.from_user.id if replied.from_user else 0,
    }
    caption = f"{t(lang, 'saved_media_title')}\n{format_sender_header(author_data, st, lang)}"
    if replied.caption:
        caption += f"\n💬 <b>{t(lang, 'caption_label')}</b> {replied.caption}"
    try:
        sent = await dispatch_media_message(owner_id, msg.chat, replied.content_type, rfile, caption)
        if sent and replied.video_note:
            await sent.reply(caption)
    except Exception as e:
        logging.error(f"Error saving media reply: {e}")


@dp.edited_business_message()
async def on_edited_business_message(msg: Message):
    owner_id = await db.get_owner_by_connection(msg.business_connection_id)
    if not owner_id or not await db.is_allowed(owner_id):
        return

    cached = await db.get_cached_message(owner_id, msg.chat.id, msg.message_id)
    st = await db.get_user_settings(owner_id)
    lang = st["language"]

    new_text = msg.text or msg.caption or ""
    old_text = cached["text_content"] if cached else None

    if old_text != new_text:
        author_data = cached or {
            "sender_first_name": msg.from_user.first_name if msg.from_user else "",
            "sender_last_name": msg.from_user.last_name if msg.from_user else "",
            "sender_username": msg.from_user.username if msg.from_user else "",
            "sender_id": msg.from_user.id if msg.from_user else 0,
        }
        title = t(lang, "edit_caption_title") if (msg.photo or msg.video or msg.document) else t(lang, "edit_text_title")
        old_val = old_text if old_text is not None else t(lang, "not_cached")
        body = (
            f"{title}\n"
            f"{format_sender_header(author_data, st, lang)}\n\n"
            f"🔴 <b>{t(lang, 'old_label')}</b>\n{old_val if old_val else t(lang, 'empty')}\n\n"
            f"🟢 <b>{t(lang, 'new_label')}</b>\n{new_text if new_text else t(lang, 'empty')}"
        )
        try:
            await send_to_owner(owner_id, msg.chat, bot.send_message, text=body)
        except Exception as e:
            logging.error(f"Error sending edit notification: {e}")

    await db.cache_message(msg, owner_id)


@dp.deleted_business_messages()
async def on_business_messages_deleted(event: BusinessMessagesDeleted):
    owner_id = await db.get_owner_by_connection(event.business_connection_id)
    if not owner_id or not await db.is_allowed(owner_id):
        return
    st = await db.get_user_settings(owner_id)
    lang = st["language"]

    async def _one(msg_id: int):
        cached = await db.get_cached_message(owner_id, event.chat.id, msg_id)
        if not cached:
            return
        sender_hdr = format_sender_header(cached, st, lang)
        content_type = cached["content_type"]
        file_id = cached["file_id"]
        text_content = cached["text_content"]
        try:
            if content_type == "text" or not file_id:
                body = (
                    f"{t(lang, 'del_text_title')}\n"
                    f"{sender_hdr}\n\n"
                    f"💬 <b>{t(lang, 'content_label')}</b>\n{text_content if text_content else t(lang, 'empty')}"
                )
                await send_to_owner(owner_id, event.chat, bot.send_message, text=body)
                return
            caption = text_content if text_content else None
            sent = await dispatch_media_message(owner_id, event.chat, content_type, file_id, caption)
            info = f"{t(lang, 'del_media_title')}\n{sender_hdr}"
            if sent:
                await sent.reply(info)
            else:
                await send_to_owner(owner_id, event.chat, bot.send_message, text=info)
        except Exception as e:
            logging.error(f"Error sending delete notification: {e}")

    await asyncio.gather(*[_one(mid) for mid in event.message_ids])


async def main():
    global BOT_USERNAME
    if not config.ADMIN_ID:
        logging.error("MY_USER_ID is 0 — set your Telegram id in .env so the allowlist works")
    await db.init_db()
    me = await bot.get_me()
    BOT_USERNAME = me.username or ""
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "callback_query",
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
        ],
    )


if __name__ == "__main__":
    asyncio.run(main())
