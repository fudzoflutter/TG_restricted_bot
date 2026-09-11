"""Per-user isolation helpers for cached media and lookups."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional, Tuple

MEDIA_ROOT = Path("media_cache")

_TG_EMOJI = re.compile(r'<tg-emoji emoji-id="[^"]*">([^<]*)</tg-emoji>')


def owner_media_dir(owner_id: int) -> Path:
    return MEDIA_ROOT / str(int(owner_id))


def purge_owner_files(owner_id: int) -> None:
    folder = owner_media_dir(owner_id)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


def owner_media_path(owner_id: int, chat_id: int, message_id: int) -> Path:
    return owner_media_dir(owner_id) / f"{int(chat_id)}_{int(message_id)}"


def resolve_owner_file(owner_id: int, stored: Optional[str]) -> Optional[Path]:
    """Return a path only if it belongs to this owner under MEDIA_ROOT."""
    if not stored:
        return None
    root = owner_media_dir(owner_id).resolve()
    path = Path(stored)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path if path.is_file() else None


def cache_identity(owner_id: int, chat_id: int, message_id: int) -> Tuple[int, int, int]:
    return (int(owner_id), int(chat_id), int(message_id))


def is_protected_media(msg) -> bool:
    return bool(getattr(msg, "has_protected_content", False))


def strip_tg_emoji(html: str) -> str:
    return _TG_EMOJI.sub(r"\1", html or "")


def connect_profile_url() -> str:
    # Opens Settings → Edit profile (Chatbots live here for all accounts).
    return "tg://settings/edit"


def connect_business_url(bot_username: str) -> Optional[str]:
    if not bot_username:
        return None
    name = bot_username.lstrip("@")
    return f"https://t.me/{name}?startbusiness"
