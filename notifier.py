from datetime import date, datetime

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

import storage
from config import CHECK_TIME, get_check_time_parts, get_timezone


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def today_local() -> date:
    return datetime.now(get_timezone()).date()


def now_local() -> datetime:
    return datetime.now(get_timezone())


def days_left_for(end_date: str, today: date | None = None) -> int:
    current_day = today or today_local()
    return (parse_date(end_date) - current_day).days


def format_days_left(end_date: str, today: date | None = None) -> str:
    diff = days_left_for(end_date, today)

    if diff < 0:
        return f"истекла {abs(diff)} дн. назад"
    if diff == 0:
        return "сегодня!"
    if diff == 1:
        return "завтра"
    return f"через {diff} дней"


def service_status_icon(service: dict, today: date | None = None) -> str:
    diff = days_left_for(service["end_date"], today)

    if diff < 0:
        return "⛔"
    if diff <= 1:
        return "🔴"
    if diff <= 7:
        return "🟡"
    return "🟢"


def notification_markup(service_id: int, expired: bool = False) -> InlineKeyboardMarkup:
    if expired:
        rows = [[
            InlineKeyboardButton("🔄 Продлить", callback_data=f"act:renew:{service_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"act:del:{service_id}"),
        ]]
    else:
        rows = [[
            InlineKeyboardButton("🔄 Продлить", callback_data=f"act:renew:{service_id}"),
            InlineKeyboardButton("📋 Мои услуги", callback_data="act:list"),
        ]]

    return InlineKeyboardMarkup(rows)


def build_notification_message(service: dict, diff: int) -> tuple[str, InlineKeyboardMarkup]:
    name = service["name"]
    end_date = service["end_date"]
    service_id = service["id"]

    if diff == 7:
        text = (
            f"🟡 Напоминание: «{name}» истекает через 7 дней\n"
            f"📅 Дата окончания: {end_date}"
        )
        return text, notification_markup(service_id)

    if diff == 3:
        text = (
            f"🟠 Внимание: «{name}» истекает через 3 дня\n"
            f"📅 Дата окончания: {end_date}"
        )
        return text, notification_markup(service_id)

    if diff == 1:
        text = (
            f"🔴 Срочно: «{name}» истекает завтра!\n"
            f"📅 Дата окончания: {end_date}"
        )
        return text, notification_markup(service_id)

    text = (
        f"⛔ Услуга «{name}» истекла!\n"
        f"📅 Дата окончания: {end_date}\n\n"
        "Продлите или удалите:"
    )
    return text, notification_markup(service_id, expired=True)


async def send_due_notifications(bot: Bot) -> int:
    data = await storage.snapshot_data()
    today = today_local()
    sent_count = 0

    for user_id, bucket in data.items():
        if user_id.startswith("__"):
            continue

        services = bucket.get("services", [])
        for service in services:
            diff = days_left_for(service["end_date"], today)
            reminder_step = None

            if diff == 7 and not service.get("notified_7", False):
                reminder_step = 7
            elif diff == 3 and not service.get("notified_3", False):
                reminder_step = 3
            elif diff == 1 and not service.get("notified_1", False):
                reminder_step = 1
            elif diff <= 0 and not service.get("notified_0", False):
                reminder_step = 0

            if reminder_step is None:
                continue

            text, markup = build_notification_message(service, reminder_step)

            try:
                await bot.send_message(chat_id=int(user_id), text=text, reply_markup=markup)
            except Exception:
                continue

            await storage.mark_notified(user_id, service["id"], reminder_step)
            sent_count += 1

    return sent_count


def should_run_now(window_minutes: int = 5) -> bool:
    current_time = now_local()
    hour, minute = get_check_time_parts()
    target_minutes = hour * 60 + minute
    current_minutes = current_time.hour * 60 + current_time.minute
    return target_minutes <= current_minutes < target_minutes + window_minutes


async def should_execute_cron(window_minutes: int = 5) -> tuple[bool, str]:
    if not should_run_now(window_minutes=window_minutes):
        return False, "outside configured time window"

    marker = f"{today_local().isoformat()}::{CHECK_TIME}"
    last_marker = await storage.get_meta_value("last_cron_marker")

    if last_marker == marker:
        return False, "already executed for current day"

    return True, "ready"


async def mark_cron_executed() -> None:
    marker = f"{today_local().isoformat()}::{CHECK_TIME}"
    await storage.set_meta_value("last_cron_marker", marker)