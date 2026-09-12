import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from html import escape
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
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    TelegramObject,
    KeyboardButtonRequestUsers,
    FSInputFile,
)

import config
import database as db
import isolation
from locales import t

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

SAVE_TRIGGERS = {"!", ".", "+", "save", "сохранить", "сейв", "/save", "s", "с"}
BOT_USERNAME = ""

# Button colors: https://core.telegram.org/bots/api#keyboardbutton
# https://docs.aiogram.dev/en/v3.28.2/api/enums/button_style.html
try:
    from aiogram.enums import ButtonStyle
    STYLE_SUCCESS = ButtonStyle.SUCCESS
    STYLE_PRIMARY = ButtonStyle.PRIMARY
    STYLE_DANGER = ButtonStyle.DANGER
except Exception:
    STYLE_SUCCESS = "success"
    STYLE_PRIMARY = "primary"
    STYLE_DANGER = "danger"

# Custom emoji (HTML <tg-emoji> + button icon_custom_emoji_id).
# https://core.telegram.org/bots/api#html-style
# ╔════════════════════════════════════════════════════════════════╗
# ║        ⚙️  CUSTOMIZATION — EDIT YOUR BOT'S LOOK HERE            ║
# ╚════════════════════════════════════════════════════════════════╝

# --- [1] WELCOME PHOTO -------------------------------------------------
# Path to a local image file, or a direct https:// URL, or "" for no photo.
WELCOME_PHOTO = "mooodypic.jpg"

# --- [2] BUTTON COLORS ---------------------------------------------------
# Allowed values: "primary" (blue), "success" (green), "danger" (red).
# Docs: https://core.telegram.org/bots/api#keyboardbutton
COLOR_CONNECT   = "success"   # green "Connect" button under /start
COLOR_SECONDARY = "primary"   # blue "Chatbots" + "How it works" buttons
COLOR_MENU      = "primary"   # reply-keyboard menu buttons

# --- [3] PREMIUM FEATURES (work only if the bot OWNER has Telegram Premium)
# True → premium emoji inside message texts (<tg-emoji>).
_USE_TEXT_CUSTOM_EMOJI = False
# True → premium emoji icons ON buttons (icon_custom_emoji_id).
_USE_BUTTON_ICONS = False
# Premium emoji IDs used when the flags above are True:
E_WAVE = "5312241539987038474"
E_SPY = "5924490652745212033"
E_SHIELD = "5924649605189869607"
E_FIRE = "5931801052155222589"
E_CHECK = "5368324170671202286"
E_GEAR = "5276246852666758580"
E_CHART = "5377312262123803976"
E_LANG = "5413704112220949842"
E_SAVE = "5271600761883117622"

# --- [4] MONETIZATION — prices in Telegram Stars (XTR) -------------------
PRICE_WEEK  = 59    # 1 hafta
PRICE_MONTH = 149   # 1 oy
PRICE_YEAR  = 700   # 1 yil
# Plan lengths (days) live in database.PREMIUM_PLANS

# --- [5] PREMIUM GATE -----------------------------------------------------
# True → the spy feed works ONLY for users with an active premium
# subscription (the admin is always exempt). Payment activates instantly.
# FREE LAUNCH: keep False while onboarding users. To go PAID later:
#   1) set REQUIRE_PREMIUM = True   (locks the feed until payment)
#   2) set SHOW_PREMIUM_BUTTON = True (shows the 💎 button in the menu)
REQUIRE_PREMIUM = False
# True → show a 💎 Premium button in the reply menu (opens /buy).
SHOW_PREMIUM_BUTTON = False
# ╚═════════════════════════ END OF CUSTOMIZATION ═════════════════════════╝


def ae(emoji_id: str, fallback: str) -> str:
    if not _USE_TEXT_CUSTOM_EMOJI:
        return fallback
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
        if await db.is_banned(user.id):
            if isinstance(event, CallbackQuery):
                await event.answer("🚫", show_alert=True)
            return None
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
    if icon and _USE_BUTTON_ICONS:
        kwargs["icon_custom_emoji_id"] = icon
    return KeyboardButton(**kwargs)


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
    if icon and _USE_BUTTON_ICONS:
        kwargs["icon_custom_emoji_id"] = icon
    return InlineKeyboardButton(**kwargs)


def _menu_labels(lang: str) -> Dict[str, str]:
    if lang == "en":
        return {"stats": "📊 Statistics", "how": "🕵️ How does the bot work?", "connect": "🟢 Connect"}
    if lang == "uz":
        return {"stats": "📊 Statistika", "how": "🕵️ Bot qanday ishlaydi?", "connect": "🟢 Ulash"}
    return {"stats": "📊 Статистика", "how": "🕵️ Как работает бот?", "connect": "🟢 Подключить"}


_LABELS = [_menu_labels(l) for l in ("en", "uz", "ru")]


PREMIUM_TEXTS = {"💎 Premium"}


def get_main_menu_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Zenly-style menu (Statistics / How it works [+ Premium])."""
    lb = _menu_labels(lang)
    rows = [
        [kb(lb["stats"], COLOR_MENU, E_CHART)],
        [kb(lb["how"], COLOR_MENU, E_SPY)],
    ]
    if SHOW_PREMIUM_BUTTON:
        rows.append([kb("💎 Premium", COLOR_MENU, E_FIRE)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def stats_contact_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Keyboard with a button that opens Telegram's native USER picker (like Zenly)."""
    rows = [
        [KeyboardButton(
            text=t(lang, "stats_pick"),
            request_users=KeyboardButtonRequestUsers(request_id=1, max_quantity=1),
        )],
        [kb(t(lang, "btn_back_menu"), COLOR_MENU)],
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
        if "not a forum" in str(e).lower():
            # Owner's PM has no topics enabled — disable once instead of retrying per message.
            try:
                await db.update_user_setting(owner_id, "threaded_mode", False)
            except Exception:
                pass
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


async def dispatch_media_message(
    owner_id: int,
    chat: Any,
    content_type: str,
    file_id: Optional[str],
    caption: Optional[str] = None,
    local_path: Optional[str] = None,
):
    media: Any = None
    path = isolation.resolve_owner_file(owner_id, local_path)
    if path:
        media = FSInputFile(path)
    elif file_id:
        media = file_id
    else:
        return None
    if content_type in ("photo", ContentType.PHOTO):
        return await send_to_owner(owner_id, chat, bot.send_photo, photo=media, caption=caption)
    if content_type in ("video", ContentType.VIDEO):
        return await send_to_owner(owner_id, chat, bot.send_video, video=media, caption=caption)
    if content_type in ("voice", ContentType.VOICE):
        return await send_to_owner(owner_id, chat, bot.send_voice, voice=media, caption=caption)
    if content_type in ("video_note", ContentType.VIDEO_NOTE):
        return await send_to_owner(owner_id, chat, bot.send_video_note, video_note=media)
    if content_type in ("audio", ContentType.AUDIO):
        return await send_to_owner(owner_id, chat, bot.send_audio, audio=media, caption=caption)
    if content_type in ("document", ContentType.DOCUMENT):
        return await send_to_owner(owner_id, chat, bot.send_document, document=media, caption=caption)
    if content_type in ("animation", ContentType.ANIMATION):
        return await send_to_owner(owner_id, chat, bot.send_animation, animation=media, caption=caption)
    if content_type in ("sticker", ContentType.STICKER):
        return await send_to_owner(owner_id, chat, bot.send_sticker, sticker=media)
    return None


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
        [ib(t(lang, "btn_lang"), callback_data="menu_lang", style=STYLE_PRIMARY, icon=E_LANG)],
    ])


def get_header_keyboard(st: Dict[str, Any]) -> InlineKeyboardMarkup:
    lang = st["language"]

    def btn_txt(name, val):
        return f"{name}: {t(lang, 'status_on') if val else t(lang, 'status_off')}"

    def styled(name, val, data):
        return ib(
            btn_txt(name, val),
            callback_data=data,
            style=STYLE_SUCCESS if val else STYLE_DANGER,
        )

    return InlineKeyboardMarkup(inline_keyboard=[
        [styled(t(lang, "btn_show_fname"), st["show_first_name"], "toggle_hdr_first_name")],
        [styled(t(lang, "btn_show_lname"), st["show_last_name"], "toggle_hdr_last_name")],
        [styled(t(lang, "btn_show_uname"), st["show_username"], "toggle_hdr_username")],
        [styled(t(lang, "btn_show_id"), st["show_user_id"], "toggle_hdr_user_id")],
        [ib(t(lang, "btn_back"), callback_data="menu_main", style=STYLE_PRIMARY)],
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
        [ib(t(lang, "btn_back"), callback_data="menu_main", style=STYLE_PRIMARY)],
    ])


def get_lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib("🇷🇺 Русский", callback_data="set_lang_ru", style=STYLE_PRIMARY)],
        [ib("🇬🇧 English", callback_data="set_lang_en", style=STYLE_PRIMARY)],
        [ib("🇺🇿 O'zbekcha", callback_data="set_lang_uz", style=STYLE_PRIMARY)],
        [ib("⬅️ Back / Назад", callback_data="menu_main", style=STYLE_DANGER)],
    ])


def connect_keyboard(
    prefer_https: bool = False,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """Single green Connect button (shown under /start)."""
    profile = isolation.connect_profile_url() if not prefer_https else "https://t.me/settings"
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(_menu_labels(lang)["connect"], url=profile, style=COLOR_CONNECT, icon=E_CHECK)],
    ])


def how_it_works_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "uz":
        back = "⬅️ Orqaga"
    elif lang == "en":
        back = "⬅️ Back"
    else:
        back = "⬅️ Назад"
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(back, callback_data="back_start", style=STYLE_PRIMARY)],
    ])


def welcome_caption(lang: str) -> str:
    bot_mention = f"@{BOT_USERNAME}" if BOT_USERNAME else "bot"
    if lang == "en":
        return (
            f"{ae(E_WAVE, '👋')} <b>Welcome!</b>\n\n"
            f"{ae(E_SPY, '🕵️')} I catch your contacts' <b>deleted</b> and <b>edited</b> messages "
            "and save <b>one-time</b> photos, videos, voice and video notes — even when you're offline.\n\n"
            f"{ae(E_SHIELD, '🔒')} I work only with <b>your permission</b> and never touch your data without consent.\n\n"
            f"<b>{ae(E_FIRE, '🛠')} Connect in 20 seconds:</b>\n"
            "<blockquote>1️⃣ Tap <b>Connect</b> below ❞\n"
            "2️⃣ Open <b>Chatbots</b> and type "
            f"{bot_mention}\n"
            "3️⃣ Tap <b>Add</b> — done ✅</blockquote>"
        )
    if lang == "uz":
        return (
            f"{ae(E_WAVE, '👋')} <b>Xush kelibsiz!</b>\n\n"
            f"{ae(E_SPY, '🕵️')} Kontaktlaringizning <b>o'chirilgan</b> va <b>tahrirlangan</b> xabarlarini ushlayman, "
            "<b>bir martalik</b> rasm, video, ovoz va video-xabarlarni saqlayman — oflayn bo'lsangiz ham.\n\n"
            f"{ae(E_SHIELD, '🔒')} Faqat <b>sizning ruxsatingiz bilan</b> ishlayman, ma'lumotlaringizga tegmayman.\n\n"
            f"<b>{ae(E_FIRE, '🛠')} 20 sekundda ulash:</b>\n"
            "<blockquote>1️⃣ Pastdagi <b>Ulash</b> tugmasini bosing ❞\n"
            f"2️⃣ <b>Chatbots</b> bo'limida {bot_mention} yozing\n"
            "3️⃣ <b>Qo'shish</b> — tayyor ✅</blockquote>"
        )
    return (
        f"{ae(E_WAVE, '👋')} <b>Добро пожаловать!</b>\n\n"
        f"{ae(E_SPY, '🕵️')} Ловлю <b>удалённые</b> и <b>отредактированные</b> сообщения ваших контактов "
        "и сохраняю <b>одноразовые</b> фото, видео, голосовые и кружки — даже когда вы офлайн.\n\n"
        f"{ae(E_SHIELD, '🔒')} Работаю только с <b>вашего разрешения</b> и не трогаю данные без согласия.\n\n"
        f"<b>{ae(E_FIRE, '🛠')} Подключение за 20 секунд:</b>\n"
        "<blockquote>1️⃣ Нажмите <b>Подключить</b> ниже ❞\n"
        f"2️⃣ Откройте <b>Chatbots</b> и введите {bot_mention}\n"
        "3️⃣ Нажмите <b>Добавить</b> — готово ✅</blockquote>"
    )


def _strip_markup_icons(markup: Any) -> Any:
    if isinstance(markup, ReplyKeyboardMarkup):
        rows = []
        for row in markup.keyboard:
            rows.append([
                KeyboardButton(text=btn.text)
                for btn in row
            ])
        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=markup.resize_keyboard,
            is_persistent=markup.is_persistent,
        )
    if isinstance(markup, InlineKeyboardMarkup):
        rows = []
        for row in markup.inline_keyboard:
            new_row = []
            for btn in row:
                kwargs: Dict[str, Any] = {"text": btn.text}
                if btn.callback_data:
                    kwargs["callback_data"] = btn.callback_data
                if btn.url:
                    kwargs["url"] = btn.url
                new_row.append(InlineKeyboardButton(**kwargs))
            rows.append(new_row)
        return InlineKeyboardMarkup(inline_keyboard=rows)
    return markup


async def send_with_markup_fallback(send_func, **kwargs):
    try:
        return await send_func(**kwargs)
    except TelegramBadRequest as e:
        err = str(e).lower()
        if any(tok in err for tok in ("url", "button_url")):
            kwargs["reply_markup"] = connect_keyboard(prefer_https=True)
            try:
                return await send_func(**kwargs)
            except TelegramBadRequest:
                pass
        if "style" in err:
            if kwargs.get("reply_markup") is not None:
                kwargs["reply_markup"] = _strip_markup_icons(kwargs["reply_markup"])
            try:
                return await send_func(**kwargs)
            except TelegramBadRequest:
                kwargs.pop("reply_markup", None)
                return await send_func(**kwargs)
        if "document_invalid" in err:
            # Telegram reports <tg-emoji> parse failures as DOCUMENT_INVALID;
            # strip them from caption/text and retry with plain emoji.
            stripped = False
            for key in ("caption", "text"):
                val = kwargs.get(key)
                if val and "<tg-emoji" in val:
                    kwargs[key] = isolation.strip_tg_emoji(val)
                    stripped = True
            if stripped:
                try:
                    return await send_func(**kwargs)
                except TelegramBadRequest:
                    pass
            raise
        if any(tok in err for tok in ("emoji", "icon", "custom_emoji")):
            if kwargs.get("reply_markup") is not None:
                kwargs["reply_markup"] = _strip_markup_icons(kwargs["reply_markup"])
            if kwargs.get("caption"):
                kwargs["caption"] = isolation.strip_tg_emoji(kwargs["caption"])
            if kwargs.get("text"):
                kwargs["text"] = isolation.strip_tg_emoji(kwargs["text"])
            try:
                return await send_func(**kwargs)
            except TelegramBadRequest:
                kwargs.pop("reply_markup", None)
                return await send_func(**kwargs)
        raise


async def send_welcome(bot_instance, chat_id: int, lang: str):
    markup = connect_keyboard(lang=lang)
    caption = welcome_caption(lang)
    photo: Any = None
    if WELCOME_PHOTO:
        if WELCOME_PHOTO.startswith("http"):
            photo = WELCOME_PHOTO
        elif os.path.isfile(WELCOME_PHOTO):
            photo = FSInputFile(WELCOME_PHOTO)
    if photo is not None:
        try:
            return await send_with_markup_fallback(
                bot_instance.send_photo,
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=markup,
            )
        except (TelegramBadRequest, FileNotFoundError, OSError):
            pass
    return await send_with_markup_fallback(
        bot_instance.send_message,
        chat_id=chat_id,
        text=caption,
        reply_markup=connect_keyboard(lang=lang),
    )


def how_it_works_text(lang: str) -> str:
    if lang == "en":
        return (
            f"{ae(E_SPY, '😎')} <b>How does the bot work?</b>\n\n"
            "1. Open <b>Settings → Edit profile</b> (Connect → tg://settings/edit)\n"
            "2. Chatbots / Chat Automation — add this bot (works without Premium)\n"
            "3. Deleted/edited messages and media are sent only to you\n"
            "4. View-once photos/videos are cached immediately\n\n"
            "⚡️ Real-time, even offline\n"
            "🔐 Isolated per user"
        )
    if lang == "uz":
        return (
            f"{ae(E_SPY, '😎')} <b>Bot qanday ishlaydi?</b>\n\n"
            "1. <b>Sozlamalar → Profilni tahrirlash</b> (Connect)\n"
            "2. Chatbots / Chat Automation — botni qo'shing (Premium shart emas)\n"
            "3. O'chirilgan/tahrirlangan xabarlar faqat sizga ketadi\n"
            "4. Bir martalik media darhol keshga tushadi\n\n"
            "⚡️ Real vaqt, oflayn ham\n"
            "🔐 Ma'lumot aralashmaydi"
        )
    return (
        f"{ae(E_SPY, '😎')} <b>Как работает бот?</b>\n\n"
        "1. <b>Настройки → Редактировать профиль</b> (Connect)\n"
        "2. Chatbots / Chat Automation — добавьте бота (Premium не требуется)\n"
        "3. Удалённые/изменённые сообщения приходят только вам\n"            "4. Одноразовые медиа сразу кэшируются\n\n"
        "⚡️ В реальном времени, даже офлайн\n"
        "🔐 Данные не смешиваются"
    )


@dp.message(CommandStart())
async def cmd_start(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    lang = st["language"]

    if await db.has_connection(msg.from_user.id):
        if lang == "en":
            text = (
                f"{ae(E_CHECK, '✅')} <b>Bot is already connected and working!</b>\n"
                "I'm catching deleted/edited messages in your chats."
            )
        elif lang == "uz":
            text = (
                f"{ae(E_CHECK, '✅')} <b>Bot allaqachon ulangan va ishlayapti!</b>\n"
                "Men sizning chatlaringizdagi o'chirilgan/tahrirlangan xabarlarni ushlayapman."
            )
        else:
            text = (
                f"{ae(E_CHECK, '✅')} <b>Бот уже подключен и работает!</b>\n"
                "Я перехватываю удалённые/отредактированные сообщения в ваших чатах."
            )
        await send_with_markup_fallback(
            msg.answer, text=text, reply_markup=get_main_menu_keyboard(lang),
        )
        return

    await send_welcome(bot, msg.chat.id, lang)
    if lang == "en":
        tools_txt = f"{ae(E_GEAR, '👇')} The tools below are always available."
    elif lang == "uz":
        tools_txt = f"{ae(E_GEAR, '👇')} Quyidagi qurollar doim mavjud."
    else:
        tools_txt = f"{ae(E_GEAR, '👇')} Инструменты ниже всегда доступны."
    await send_with_markup_fallback(
        msg.answer, text=tools_txt, reply_markup=get_main_menu_keyboard(lang),
    )


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
    await send_with_markup_fallback(
        msg.answer, text=t(st["language"], "settings_title"), reply_markup=get_settings_keyboard(st),
    )


@dp.message(Command("menu"))
async def cmd_menu(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    await send_with_markup_fallback(
        msg.answer, text=t(st["language"], "menu_title"), reply_markup=get_main_menu_keyboard(st["language"]),
    )


CONNECT_TEXTS = {lb["connect"] for lb in _LABELS} | {"Connect", "Ulash", "Подключить"}
HOW_TEXTS = {lb["how"] for lb in _LABELS} | {"How does the bot work?", "Bot qanday ishlaydi?", "Как работает бот?"}
STATS_TEXTS = {lb["stats"] for lb in _LABELS} | {"Statistics", "Statistika", "Статистика"}
SETTINGS_TEXTS = {"Sozlamalar", "Settings", "Настройки"}
LANG_TEXTS = {"Til", "Language", "Язык"}
SAVE_MODE_TEXTS = {"Saqlash rejimi", "Save Mode", "Режим сохр."}


@dp.message(F.text.in_(CONNECT_TEXTS))
async def btn_connect(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    lang = st["language"]
    mention = f"@{BOT_USERNAME}" if BOT_USERNAME else "bot"
    if lang == "en":
        text = (
            f"{ae(E_CHECK, '🟢')} <b>To connect:</b>\n\n"
            "1️⃣ Tap <b>Connect</b> → Profile Edit (no Premium / no API hash)\n"
            f"2️⃣ Add <b>{mention}</b> in Chatbots ✅"
        )
    elif lang == "uz":
        text = (
            f"{ae(E_CHECK, '🟢')} <b>Ulash:</b>\n\n"
            "1️⃣ <b>Connect</b> — profil tahrirlash (Premium shart emas)\n"
            f"2️⃣ Chatbots da <b>{mention}</b> ni qo'shing ✅"
        )
    else:
        text = (
            f"{ae(E_CHECK, '🟢')} <b>Подключение:</b>\n\n"
            "1️⃣ <b>Connect</b> — редактирование профиля (Premium не нужен)\n"
            f"2️⃣ В Chatbots добавьте <b>{mention}</b> ✅"
        )
    await send_with_markup_fallback(msg.answer, text=text, reply_markup=connect_keyboard())


@dp.message(F.text.in_(HOW_TEXTS))
async def btn_how(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    lang = st["language"]
    await send_with_markup_fallback(
        msg.answer, text=how_it_works_text(lang), reply_markup=how_it_works_keyboard(lang),
    )


@dp.message(F.text.in_(STATS_TEXTS))
async def btn_stats(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    await send_with_markup_fallback(
        msg.answer,
        text=t(st["language"], "stats_choose"),
        reply_markup=stats_contact_keyboard(st["language"]),
    )


BACK_MENU_TEXTS = {"⬅️ Menu", "⬅️ Menyu", "⬅️ Меню"}


@dp.message(F.text.in_(BACK_MENU_TEXTS))
async def btn_back_menu(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    await send_with_markup_fallback(
        msg.answer, text=t(st["language"], "menu_title"), reply_markup=get_main_menu_keyboard(st["language"]),
    )


_STATS_ORDER = [
    ("text", "stats_text"),
    ("sticker", "stats_stickers"),
    ("voice", "stats_voice"),
    ("video_note", "stats_video_notes"),
    ("video", "stats_videos"),
    ("photo", "stats_photos"),
]
_STATS_EXTRA = [
    ("audio", "stats_audio"),
    ("document", "stats_documents"),
    ("animation", "stats_animations"),
]


def _utc_day_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


@dp.message(F.users_shared)
async def on_users_shared(msg: Message):
    """Zenly-style stats: native user picker → today's message counts from that user."""
    st = await db.get_user_settings(msg.from_user.id)
    lang = st["language"]
    shared = msg.users_shared.users
    if not shared:
        return
    u = shared[0]
    counts = await db.get_contact_stats(msg.from_user.id, u.user_id, _utc_day_start_iso())
    name = " ".join(p for p in [u.first_name, u.last_name] if p).strip()
    if not name:
        name = f"@{u.username}" if u.username else str(u.user_id)
    lines = [f"— {t(lang, loc)}: {counts.get(key, 0)}" for key, loc in _STATS_ORDER]
    lines += [f"— {t(lang, loc)}: {counts[key]}" for key, loc in _STATS_EXTRA if counts.get(key)]
    total = sum(counts.values())
    text = (
        f"📊 <b>{t(lang, 'stats_for')} {escape(name)} — {t(lang, 'stats_today')}</b>\n\n"
        f"<blockquote>📥 <b>{t(lang, 'stats_received')}:</b>\n"
        + "\n".join(lines)
        + f"\n📦 {t(lang, 'stats_total')}: {total}</blockquote>"
    )
    await send_with_markup_fallback(
        msg.answer, text=text, reply_markup=get_main_menu_keyboard(lang),
    )


@dp.message(F.contact)
async def on_contact_shared(msg: Message):
    """Fallback for old clients: same stats for a shared phone-book contact."""
    st = await db.get_user_settings(msg.from_user.id)
    lang = st["language"]
    contact = msg.contact
    if not contact:
        return
    counts = await db.get_contact_stats(msg.from_user.id, contact.user_id, _utc_day_start_iso())
    name = " ".join(p for p in [contact.first_name, contact.last_name] if p).strip()
    if not name:
        name = (
            f"@{contact.username}" if contact.username
            else f"+{contact.phone_number}" if contact.phone_number
            else str(contact.user_id)
        )
    lines = [f"— {t(lang, loc)}: {counts.get(key, 0)}" for key, loc in _STATS_ORDER]
    lines += [f"— {t(lang, loc)}: {counts[key]}" for key, loc in _STATS_EXTRA if counts.get(key)]
    total = sum(counts.values())
    text = (
        f"📊 <b>{t(lang, 'stats_for')} {escape(name)} — {t(lang, 'stats_today')}</b>\n\n"
        f"<blockquote>📥 <b>{t(lang, 'stats_received')}:</b>\n"
        + "\n".join(lines)
        + f"\n📦 {t(lang, 'stats_total')}: {total}</blockquote>"
    )
    await send_with_markup_fallback(
        msg.answer, text=text, reply_markup=get_main_menu_keyboard(lang),
    )


@dp.message(F.text.in_(SETTINGS_TEXTS))
async def btn_settings(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    await send_with_markup_fallback(
        msg.answer, text=t(st["language"], "settings_title"), reply_markup=get_settings_keyboard(st),
    )


@dp.message(F.text.in_(LANG_TEXTS))
async def btn_lang(msg: Message):
    await send_with_markup_fallback(msg.answer, text="🌐", reply_markup=get_lang_keyboard())


@dp.message(F.text.in_(SAVE_MODE_TEXTS))
async def btn_save_mode(msg: Message):
    st = await db.get_user_settings(msg.from_user.id)
    await send_with_markup_fallback(
        msg.answer, text=t(st["language"], "save_mode_title"), reply_markup=get_save_mode_keyboard(st),
    )


@dp.callback_query(F.data == "how_it_works")
async def cb_how_it_works(call: CallbackQuery):
    st = await db.get_user_settings(call.from_user.id)
    lang = st["language"]
    try:
        await call.message.edit_text(how_it_works_text(lang), reply_markup=how_it_works_keyboard(lang))
    except TelegramBadRequest:
        await call.message.answer(how_it_works_text(lang), reply_markup=how_it_works_keyboard(lang))
    await call.answer()


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


# ===========================================================================
# 💎 MONETIZATION (Telegram Stars)
# ===========================================================================
_STAR_PLANS = {
    "week": (PRICE_WEEK, "buy_week"),
    "month": (PRICE_MONTH, "buy_month"),
    "year": (PRICE_YEAR, "buy_year"),
}


def _premium_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(t(lang, "buy_week"), callback_data="buy:week", style=COLOR_SECONDARY)],
        [ib(t(lang, "buy_month"), callback_data="buy:month", style=COLOR_CONNECT)],
        [ib(t(lang, "buy_year"), callback_data="buy:year", style=COLOR_SECONDARY)],
    ])


@dp.message(Command("buy"))
async def cmd_buy(msg: Message):
    lang = (await db.get_user_settings(msg.from_user.id))["language"]
    await send_with_markup_fallback(
        msg.answer,
        text=t(lang, "buy_title"),
        reply_markup=_premium_keyboard(lang),
    )


@dp.message(F.text.in_(PREMIUM_TEXTS))
async def btn_premium(msg: Message):
    await cmd_buy(msg)


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery):
    lang = (await db.get_user_settings(call.from_user.id))["language"]
    plan = call.data.split(":")[1]
    if plan not in _STAR_PLANS:
        await call.answer()
        return
    price, label_key = _STAR_PLANS[plan]
    try:
        await call.message.answer_invoice(
            title=t(lang, label_key),
            description=t(lang, label_key),
            payload=f"premium:{plan}",
            currency="XTR",
            prices=[LabeledPrice(label=t(lang, label_key), amount=price)],
        )
    except TelegramBadRequest as e:
        logging.warning(f"invoice error: {e}")
        await call.message.answer(t(lang, "pay_failed"))
    await call.answer()


@dp.pre_checkout_query()
async def on_pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=q.invoice_payload.startswith("premium:"))


@dp.message(F.successful_payment)
async def on_successful_payment(msg: Message):
    sp = msg.successful_payment
    plan = (sp.invoice_payload or "").split(":")[-1]
    days = db.PREMIUM_PLANS.get(plan, 30)
    await db.premium_grant(msg.from_user.id, days)
    lang = (await db.get_user_settings(msg.from_user.id))["language"]
    try:
        await msg.answer(t(lang, "pay_sent").format(plan=t(lang, _STAR_PLANS.get(plan, (0, "buy_month"))[1])))
    except Exception:
        pass


# --- premium gate: the spy feed is locked until the user pays -------------
_PREM_NOTICE_TS: Dict[int, float] = {}
_PREM_NOTICE_COOLDOWN = 6 * 3600  # remind at most every 6 hours


def _premium_locked(owner_id: int) -> bool:
    return bool(REQUIRE_PREMIUM) and owner_id != config.ADMIN_ID


async def _premium_gate_notice(owner_id: int) -> None:
    """Rate-limited 'pay to activate' reminder with a one-tap invoice button."""
    now = time.monotonic()
    if now - _PREM_NOTICE_TS.get(owner_id, 0) < _PREM_NOTICE_COOLDOWN:
        return
    _PREM_NOTICE_TS[owner_id] = now
    lang = (await db.get_user_settings(owner_id))["language"]
    try:
        await bot.send_message(
            owner_id,
            t(lang, "premium_required"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [ib(t(lang, "buy_month"), callback_data="buy:month", style=COLOR_CONNECT)],
            ]),
        )
    except Exception:
        pass


# ===========================================================================
# 🛠 ADMIN PANEL — /admin (broadcast, users, premium, bans)
# ===========================================================================
def _adm_root_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(t(lang, "adm_broadcast"), callback_data="adm:bc", style=COLOR_CONNECT),
         ib(t(lang, "adm_users"), callback_data="adm:users", style=COLOR_SECONDARY)],
        [ib(t(lang, "adm_premium"), callback_data="adm:prem", style=COLOR_SECONDARY),
         ib(t(lang, "adm_ban"), callback_data="adm:ban", style="danger")],
    ])


@dp.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not db.is_admin(msg.from_user.id):
        await msg.answer(t("uz", "adm_denied"))
        return
    users = await db.count_rows("user_settings")
    conns = await db.count_rows("connections")
    prem = await db.count_rows("premium_users")
    banned = await db.count_rows("banned_users")
    await msg.answer(
        f"{t('uz', 'adm_title')}\n\n"
        + t('uz', "adm_stats").format(users=users, conns=conns, prem=prem, banned=banned),
        reply_markup=_adm_root_keyboard("uz"),
    )


@dp.callback_query(F.data == "adm:users")
async def cb_adm_users(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    rows = await db.list_known_users(20)
    banlist = set(await db.list_banned())
    premset = {r["user_id"] for r in await db.premium_list()}
    lines = []
    for r in rows:
        uid = r["user_id"]
        lines.append(
            t("uz", "adm_users_row").format(
                uid=uid, name="id" + str(uid),
                banned=" 🚫" if uid in banlist else "",
                prem=" 💎" if uid in premset else "",
            )
        )
    body = t("uz", "adm_users_hdr").format(n=len(rows)) + ("".join(lines) or t("uz", "adm_empty"))
    await call.message.answer(body)
    await call.answer()


@dp.callback_query(F.data == "adm:bc")
async def cb_adm_broadcast(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    await call.message.answer(t("uz", "adm_ask_text"))
    await call.answer()


@dp.callback_query(F.data == "adm:prem")
async def cb_adm_premium(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [ib(t("uz", "adm_prem_grant"), callback_data="adm:prem_grant")],
        [ib(t("uz", "adm_prem_revoke"), callback_data="adm:prem_revoke")],
        [ib(t("uz", "adm_prem_list"), callback_data="adm:prem_list")],
        [ib(t("uz", "adm_back"), callback_data="adm:root")],
    ])
    await call.message.answer(t("uz", "adm_prem_title"), reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "adm:ban")
async def cb_adm_ban(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [ib(t("uz", "adm_ban"), callback_data="adm:ban_set")],
        [ib(t("uz", "adm_unban"), callback_data="adm:ban_unset")],
        [ib(t("uz", "adm_banlist"), callback_data="adm:ban_list")],
        [ib(t("uz", "adm_back"), callback_data="adm:root")],
    ])
    await call.message.answer(t("uz", "adm_title"), reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "adm:root")
async def cb_adm_root(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    try:
        await call.message.edit_text(t("uz", "adm_title"), reply_markup=_adm_root_keyboard("uz"))
    except TelegramBadRequest:
        await call.message.answer(t("uz", "adm_title"), reply_markup=_adm_root_keyboard("uz"))
    await call.answer()


# --- admin input state machine (waiting for IDs / broadcast content) ------
_ADM_STATES: Dict[int, Optional[str]] = {}
_ADM_PENDING_BC: Dict[int, Message] = {}


async def _adm_set_state(user_id: int, value: Optional[str]) -> None:
    if value is None:
        _ADM_STATES.pop(user_id, None)
    else:
        _ADM_STATES[user_id] = value


async def _adm_pop_state(user_id: int) -> Optional[str]:
    return _ADM_STATES.pop(user_id, None)


def _adm_state_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(t("uz", "adm_back"), callback_data="adm:root")],
    ])


async def _ask_admin_id(call: CallbackQuery, state: str) -> None:
    await _adm_set_state(call.from_user.id, state)
    await call.message.answer(t("uz", "adm_waiting_id"), reply_markup=_adm_state_kb("uz"))
    await call.answer()


@dp.callback_query(F.data.in_({"adm:prem_grant", "adm:prem_revoke", "adm:ban_set", "adm:ban_unset"}))
async def cb_adm_wait_id(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    await _ask_admin_id(call, call.data.split(":")[1])


@dp.callback_query(F.data == "adm:prem_list")
async def cb_adm_prem_list(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    rows = await db.premium_list()
    lines = [f"• <code>{r['user_id']}</code> — {str(r.get('until', ''))[:10]}" for r in rows]
    await call.message.answer(
        t("uz", "adm_prem_list_hdr") + ("\n".join(lines) or t("uz", "adm_empty"))
    )
    await call.answer()


@dp.callback_query(F.data == "adm:ban_list")
async def cb_adm_ban_list(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    ids = await db.list_banned()
    lines = [f"• <code>{i}</code>" for i in ids]
    await call.message.answer(t("uz", "adm_banlist_hdr") + ("\n".join(lines) or t("uz", "adm_empty")))
    await call.answer()


@dp.message(Command("cancel"))
async def cmd_cancel(msg: Message):
    if await _adm_pop_state(msg.from_user.id):
        await msg.answer(t("uz", "adm_title"), reply_markup=_adm_root_keyboard("uz"))


@dp.callback_query(F.data == "adm:bc_yes")
async def cb_adm_bc_yes(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    src = _ADM_PENDING_BC.pop(call.from_user.id, None)
    if src is None:
        await call.answer()
        return
    await call.message.answer(t("uz", "adm_bc_start"))
    ids = [r["user_id"] for r in await db.list_known_users(1000)]
    ok = fail = 0
    for uid in ids:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=src.chat.id, message_id=src.message_id)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await call.message.answer(t("uz", "adm_bc_done").format(ok=ok, fail=fail))
    await call.answer()


@dp.callback_query(F.data == "adm:bc_no")
async def cb_adm_bc_no(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    _ADM_PENDING_BC.pop(call.from_user.id, None)
    await call.message.answer(t("uz", "adm_title"), reply_markup=_adm_root_keyboard("uz"))
    await call.answer()


@dp.message(F.from_user.func(lambda u: bool(config.ADMIN_ID) and u.id == config.ADMIN_ID))
async def on_admin_message(msg: Message):
    """Admin free-input: broadcast content (any type) or user IDs. Menu texts
    and commands are handled by earlier-registered handlers, so they never
    reach this catch-all."""
    state = await _adm_pop_state(msg.from_user.id)
    if not state:
        return
    if state == "bc":
        _ADM_PENDING_BC[msg.from_user.id] = msg
        n = await db.count_rows("user_settings")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [ib(t("uz", "adm_yes"), callback_data="adm:bc_yes", style=COLOR_CONNECT),
             ib(t("uz", "adm_no"), callback_data="adm:bc_no", style="danger")],
        ])
        await msg.answer(t("uz", "adm_bc_ask").format(n=n), reply_markup=kb)
        return
    raw = (msg.text or "").strip().split()[-1] if msg.text else ""
    try:
        uid = int(raw)
    except ValueError:
        await msg.answer(t("uz", "adm_bad_id"), reply_markup=_adm_state_kb("uz"))
        return
    if state == "prem_grant":
        await db.premium_grant(uid, db.PREMIUM_PLANS["month"])
        await msg.answer(t("uz", "adm_prem_ok").format(uid=uid, plan="1 oy"))
    elif state == "prem_revoke":
        await db.premium_revoke(uid)
        await msg.answer(t("uz", "adm_prem_gone").format(uid=uid))
    elif state == "ban_set":
        await db.ban_user(uid)
        await msg.answer(t("uz", "adm_ban_ok").format(uid=uid))
    elif state == "ban_unset":
        await db.unban_user(uid)
        await msg.answer(t("uz", "adm_unban_ok").format(uid=uid))


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


async def _deliver_protected_media(
    owner_id: int, msg: Message, file_id: str, content_type: str, local_path: Optional[str] = None
):
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
        sent = await dispatch_media_message(
            owner_id, msg.chat, content_type, file_id, caption, local_path=local_path
        )
        if sent and content_type == "video_note":
            await sent.reply(caption)
    except Exception as e:
        logging.error(f"protected media deliver error: {e}")


async def persist_business_media(owner_id: int, msg: Message):
    """Download media immediately so view-once / deletes can still be recovered."""
    content_type, file_id = db.extract_media(msg)
    if not file_id:
        return
    dest = isolation.owner_media_path(owner_id, msg.chat.id, msg.message_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    local_path = None
    downloadable = (
        (msg.photo[-1] if msg.photo else None)
        or msg.video
        or msg.voice
        or msg.video_note
        or msg.audio
        or msg.document
        or msg.animation
        or msg.sticker
        or file_id
    )
    try:
        await bot.download(downloadable, destination=dest)
        local_path = str(dest)
        await db.set_message_local_path(owner_id, msg.chat.id, msg.message_id, local_path)
    except Exception as e:
        logging.warning(f"media download failed owner={owner_id}: {e}")
    if isolation.is_protected_media(msg):
        await _deliver_protected_media(owner_id, msg, file_id, content_type, local_path=local_path)


@dp.business_message()
async def on_business_message(msg: Message):
    owner_id = await db.get_owner_by_connection(msg.business_connection_id)
    if not owner_id or await db.is_banned(owner_id) or not await db.is_allowed(owner_id):
        return
    if _premium_locked(owner_id) and not await db.premium_active(owner_id):
        await _premium_gate_notice(owner_id)
        return

    await db.cache_message(msg, owner_id)
    _, file_id = db.extract_media(msg)
    if file_id:
        asyncio.create_task(persist_business_media(owner_id, msg))

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
        sent = await dispatch_media_message(
            owner_id, msg.chat, replied.content_type, rfile, caption
        )
        if sent and replied.video_note:
            await sent.reply(caption)
    except Exception as e:
        logging.error(f"Error saving media reply: {e}")


@dp.edited_business_message()
async def on_edited_business_message(msg: Message):
    owner_id = await db.get_owner_by_connection(msg.business_connection_id)
    if not owner_id or await db.is_banned(owner_id) or not await db.is_allowed(owner_id):
        return
    if _premium_locked(owner_id) and not await db.premium_active(owner_id):
        return

    # The owner's own edits are mirrored to the cache but never reported —
    # each user only gets notified about OTHER people's edits.
    is_self_edit = bool(msg.from_user and msg.from_user.id == owner_id)

    cached = await db.get_cached_message(owner_id, msg.chat.id, msg.message_id)
    st = await db.get_user_settings(owner_id)
    lang = st["language"]

    new_text = msg.text or msg.caption or ""
    old_text = cached["text_content"] if cached else None

    if old_text != new_text and not is_self_edit:
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
    _, file_id = db.extract_media(msg)
    if file_id:
        asyncio.create_task(persist_business_media(owner_id, msg))


@dp.deleted_business_messages()
async def on_business_messages_deleted(event: BusinessMessagesDeleted):
    owner_id = await db.get_owner_by_connection(event.business_connection_id)
    if not owner_id or await db.is_banned(owner_id) or not await db.is_allowed(owner_id):
        return
    if _premium_locked(owner_id) and not await db.premium_active(owner_id):
        return
    st = await db.get_user_settings(owner_id)
    lang = st["language"]

    async def _one(msg_id: int):
        cached = await db.get_cached_message(owner_id, event.chat.id, msg_id)
        if not cached:
            return
        # The delete event carries no sender info, but the cached row does.
        # Owners never get notified about deleting their OWN messages.
        if cached.get("sender_id") == owner_id:
            return
        sender_hdr = format_sender_header(cached, st, lang)
        content_type = cached["content_type"]
        file_id = cached["file_id"]
        text_content = cached["text_content"]
        try:
            has_media = bool(file_id or cached.get("local_path"))
            if content_type == "text" or not has_media:
                body = (
                    f"{t(lang, 'del_text_title')}\n"
                    f"{sender_hdr}\n\n"
                    f"💬 <b>{t(lang, 'content_label')}</b>\n{text_content if text_content else t(lang, 'empty')}"
                )
                await send_to_owner(owner_id, event.chat, bot.send_message, text=body)
                return
            caption = text_content if text_content else None
            sent = await dispatch_media_message(
                owner_id,
                event.chat,
                content_type,
                file_id,
                caption,
                local_path=cached.get("local_path"),
            )
            info = f"{t(lang, 'del_media_title')}\n{sender_hdr}"
            if sent:
                await sent.reply(info)
            else:
                await send_to_owner(owner_id, event.chat, bot.send_message, text=info)
        except Exception as e:
            logging.error(f"Error sending delete notification: {e}")

    await asyncio.gather(*[_one(mid) for mid in event.message_ids])


_health_server = None


async def start_healthcheck() -> None:
    global _health_server
    port = os.getenv("PORT")
    if not port:
        return

    async def handle(reader, writer):
        try:
            await reader.read(1024)
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                b"Content-Length: 2\r\nConnection: close\r\n\r\nok"
            )
            await writer.drain()
        finally:
            writer.close()

    _health_server = await asyncio.start_server(handle, "0.0.0.0", int(port))
    logging.info("healthcheck listening on 0.0.0.0:%s", port)


async def premium_expiry_loop() -> None:
    """Notify users 24h before their premium expires."""
    while True:
        try:
            for uid in await db.premium_expiring_tomorrow():
                try:
                    await bot.send_message(uid, t("uz", "adm_trial_end"))
                except Exception:
                    pass
                await db.mark_premium_notified(uid)
        except Exception as e:
            logging.warning(f"premium_expiry_loop error: {e}")
        await asyncio.sleep(3600)


async def main():
    global BOT_USERNAME
    if not config.ADMIN_ID:
        logging.error("MY_USER_ID is 0 — set your Telegram id in .env so the allowlist works")
    isolation.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    await db.init_db()
    me = await bot.get_me()
    BOT_USERNAME = me.username or ""
    await start_healthcheck()
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(premium_expiry_loop())
    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "callback_query",
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
            "pre_checkout_query",
        ],
    )


if __name__ == "__main__":
    asyncio.run(main())
