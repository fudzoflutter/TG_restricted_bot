"""
database.py — Supabase (PostgreSQL) backend
"""
import logging
from typing import Any, Dict, List, Optional

from supabase import create_client, Client
from aiogram.types import Message

import config
import isolation

log = logging.getLogger(__name__)

_supabase: Optional[Client] = None


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _supabase


def _one(res) -> Optional[Dict[str, Any]]:
    """res.data dan birinchi elementni xavfsiz olish."""
    if res is None:
        return None
    data = getattr(res, "data", None)
    if not data:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data


# ---------------------------------------------------------------------------
# Initialise DB — Supabase ulanishini tekshirish
# ---------------------------------------------------------------------------
async def init_db():
    sb = get_supabase()
    try:
        sb.table("user_settings").select("user_id").limit(1).execute()
        log.info("✅ Supabase connection OK")
    except Exception as e:
        log.error(f"❌ Supabase connection failed: {e}")
        raise
    if config.ADMIN_ID:
        await allow_user(config.ADMIN_ID, config.ADMIN_ID)


# ---------------------------------------------------------------------------
# USER SETTINGS
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "language": "ru",
    "show_first_name": True,
    "show_last_name": True,
    "show_username": True,
    "show_user_id": True,
    "threaded_mode": False,
    "save_media_mode": "all",
}


async def get_user_settings(user_id: int) -> Dict[str, Any]:
    sb = get_supabase()
    try:
        res = sb.table("user_settings").select("*").eq("user_id", user_id).limit(1).execute()
        row = _one(res)
        if row:
            return row
    except Exception as e:
        log.warning(f"get_user_settings error: {e}")

    # Yo'q bo'lsa — default qaytaramiz va saqlaymiz
    row = {"user_id": user_id, **DEFAULT_SETTINGS}
    try:
        sb.table("user_settings").upsert(row).execute()
    except Exception as e:
        log.warning(f"insert default settings error: {e}")
    return row


async def update_user_setting(user_id: int, field: str, value: Any):
    sb = get_supabase()
    try:
        sb.table("user_settings").update({field: value}).eq("user_id", user_id).execute()
    except Exception as e:
        log.warning(f"update_user_setting error: {e}")


# ---------------------------------------------------------------------------
# BUSINESS CONNECTIONS
# ---------------------------------------------------------------------------
async def save_connection(connection_id: str, user_id: int):
    sb = get_supabase()
    try:
        sb.table("connections").upsert(
            {"connection_id": connection_id, "user_id": user_id}
        ).execute()
    except Exception as e:
        log.warning(f"save_connection error: {e}")


def is_admin(user_id: int) -> bool:
    return bool(config.ADMIN_ID) and user_id == config.ADMIN_ID


async def is_allowed(user_id: int) -> bool:
    if is_admin(user_id):
        return True
    sb = get_supabase()
    try:
        res = sb.table("allowed_users").select("user_id").eq("user_id", user_id).limit(1).execute()
        return bool(_one(res))
    except Exception as e:
        log.warning(f"is_allowed error: {e}")
        return False


async def allow_user(user_id: int, added_by: int) -> None:
    sb = get_supabase()
    try:
        sb.table("allowed_users").upsert(
            {"user_id": user_id, "added_by": added_by}
        ).execute()
    except Exception as e:
        log.warning(f"allow_user error: {e}")


async def deny_user(user_id: int) -> None:
    if is_admin(user_id):
        return
    sb = get_supabase()
    try:
        sb.table("allowed_users").delete().eq("user_id", user_id).execute()
    except Exception as e:
        log.warning(f"deny_user error: {e}")
    await purge_owner_runtime(user_id)


async def list_allowed() -> List[int]:
    sb = get_supabase()
    ids: List[int] = []
    if config.ADMIN_ID:
        ids.append(config.ADMIN_ID)
    try:
        res = sb.table("allowed_users").select("user_id").execute()
        data = getattr(res, "data", None) or []
        for row in data:
            uid = row.get("user_id")
            if uid and uid not in ids:
                ids.append(uid)
    except Exception as e:
        log.warning(f"list_allowed error: {e}")
    return ids


async def get_owner_by_connection(connection_id: Optional[str]) -> Optional[int]:
    if not connection_id:
        return None
    sb = get_supabase()
    try:
        res = sb.table("connections").select("user_id").eq("connection_id", connection_id).limit(1).execute()
        row = _one(res)
        return row["user_id"] if row else None
    except Exception as e:
        log.warning(f"get_owner_by_connection error: {e}")
        return None


async def purge_owner_runtime(user_id: int) -> None:
    """Drop connection + cached rows for one owner so leftover data cannot leak."""
    sb = get_supabase()
    for table, col in (
        ("connections", "user_id"),
        ("messages", "owner_id"),
        ("user_topics", "owner_id"),
    ):
        try:
            sb.table(table).delete().eq(col, user_id).execute()
        except Exception as e:
            log.warning(f"purge {table} error: {e}")
    isolation.purge_owner_files(user_id)


async def has_connection(user_id: int) -> bool:
    sb = get_supabase()
    try:
        res = sb.table("connections").select("connection_id").eq("user_id", user_id).limit(1).execute()
        return bool(_one(res))
    except Exception as e:
        log.warning(f"has_connection error: {e}")
        return False


# ---------------------------------------------------------------------------
# MESSAGE CACHE
# ---------------------------------------------------------------------------
def extract_media(msg: Message) -> tuple:
    if msg.photo:
        return "photo", msg.photo[-1].file_id
    if msg.video:
        return "video", msg.video.file_id
    if msg.voice:
        return "voice", msg.voice.file_id
    if msg.video_note:
        return "video_note", msg.video_note.file_id
    if msg.audio:
        return "audio", msg.audio.file_id
    if msg.document:
        return "document", msg.document.file_id
    if msg.animation:
        return "animation", msg.animation.file_id
    if msg.sticker:
        return "sticker", msg.sticker.file_id
    return str(msg.content_type), None


async def cache_message(msg: Message, owner_id: int):
    sender = msg.from_user
    sender_id = sender.id if sender else 0
    s_uname = (sender.username or "") if sender else ""
    s_fname = (sender.first_name or "") if sender else ""
    s_lname = (sender.last_name or "") if sender else ""
    content_type, file_id = extract_media(msg)
    text_content = msg.text or msg.caption or ""

    sb = get_supabase()
    try:
        sb.table("messages").upsert(
            {
                "owner_id": owner_id,
                "connection_id": msg.business_connection_id,
                "chat_id": msg.chat.id,
                "message_id": msg.message_id,
                "sender_id": sender_id,
                "sender_username": s_uname,
                "sender_first_name": s_fname,
                "sender_last_name": s_lname,
                "content_type": content_type,
                "text_content": text_content,
                "file_id": file_id,
            },
            on_conflict="owner_id,chat_id,message_id",
        ).execute()
    except Exception as e:
        log.warning(f"cache_message error: {e}")


async def set_message_local_path(owner_id: int, chat_id: int, message_id: int, local_path: str) -> None:
    sb = get_supabase()
    try:
        sb.table("messages").update({"local_path": local_path}).eq("owner_id", owner_id).eq(
            "chat_id", chat_id
        ).eq("message_id", message_id).execute()
    except Exception as e:
        log.warning(f"set_message_local_path error: {e}")


async def get_cached_message(owner_id: int, chat_id: int, message_id: int) -> Optional[Dict[str, Any]]:
    sb = get_supabase()
    try:
        res = (
            sb.table("messages")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("chat_id", chat_id)
            .eq("message_id", message_id)
            .limit(1)
            .execute()
        )
        return _one(res)
    except Exception as e:
        log.warning(f"get_cached_message error: {e}")
        return None


# ---------------------------------------------------------------------------
# FORUM TOPICS
# ---------------------------------------------------------------------------
async def get_user_topic(owner_id: int, business_chat_id: int) -> Optional[int]:
    sb = get_supabase()
    try:
        res = (
            sb.table("user_topics")
            .select("thread_id")
            .eq("owner_id", owner_id)
            .eq("business_chat_id", business_chat_id)
            .limit(1)
            .execute()
        )
        row = _one(res)
        return row["thread_id"] if row else None
    except Exception as e:
        log.warning(f"get_user_topic error: {e}")
        return None


async def save_user_topic(owner_id: int, business_chat_id: int, thread_id: int, topic_name: str):
    sb = get_supabase()
    try:
        sb.table("user_topics").upsert({
            "owner_id": owner_id,
            "business_chat_id": business_chat_id,
            "thread_id": thread_id,
            "topic_name": topic_name,
        }).execute()
    except Exception as e:
        log.warning(f"save_user_topic error: {e}")


async def update_user_topic_name(owner_id: int, thread_id: int, topic_name: str):
    sb = get_supabase()
    try:
        sb.table("user_topics").update({"topic_name": topic_name}).eq(
            "owner_id", owner_id
        ).eq("thread_id", thread_id).execute()
    except Exception as e:
        log.warning(f"update_user_topic_name error: {e}")