# environment variables
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "8839105396:AAEb0_Y3nekW8rMR-jFq8dzCEA93rAGI1Og")
MY_USER_ID: int = int(os.getenv("MY_USER_ID", "5794972204"))
ADMIN_ID: int = MY_USER_ID

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://hnshcrtuksiluuquvntj.supabase.co")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "Jurat_$1303")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

# Force ONE language for every user: "uz", "ru", "en" — or "" to let each
# user pick their own via the menu.
FORCE_LANGUAGE: str = os.getenv("FORCE_LANGUAGE", "uz")