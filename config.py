import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TZ = os.getenv("TZ", "UTC").strip() or "UTC"
CHECK_TIME = os.getenv("CHECK_TIME", "09:00").strip() or "09:00"
DATA_FILE = BASE_DIR / os.getenv("DATA_FILE", "data.json")
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "file").strip().lower() or "file"
REDIS_URL = os.getenv("REDIS_URL", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
CRON_SECRET = os.getenv("CRON_SECRET", "").strip()


def get_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(TZ)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown timezone: {TZ}") from error


def get_check_time_parts() -> tuple[int, int]:
    try:
        hour_str, minute_str = CHECK_TIME.split(":", maxsplit=1)
        hour = int(hour_str)
        minute = int(minute_str)
    except ValueError as error:
        raise ValueError("CHECK_TIME must use HH:MM format") from error

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("CHECK_TIME must be a valid 24-hour time")

    return hour, minute


def validate_config() -> None:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set in environment variables")

    if STORAGE_BACKEND not in {"file", "redis"}:
        raise ValueError("STORAGE_BACKEND must be either 'file' or 'redis'")

    if STORAGE_BACKEND == "redis" and not REDIS_URL:
        raise ValueError("REDIS_URL is required when STORAGE_BACKEND=redis")

    get_timezone()
    get_check_time_parts()
