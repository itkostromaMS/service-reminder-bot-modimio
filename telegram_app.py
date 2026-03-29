import asyncio
from datetime import time as dt_time

from telegram.ext import Application, CallbackContext

from config import BOT_TOKEN, get_check_time_parts, get_timezone, validate_config
from handlers import register_handlers
from notifier import send_due_notifications

_webhook_application: Application | None = None
_webhook_lock = asyncio.Lock()


def build_application(*, webhook_mode: bool) -> Application:
    validate_config()
    builder = Application.builder().token(BOT_TOKEN)

    if webhook_mode:
        builder = builder.updater(None)

    application = builder.build()
    register_handlers(application)
    return application


async def get_webhook_application() -> Application:
    global _webhook_application

    if _webhook_application is None:
        async with _webhook_lock:
            if _webhook_application is None:
                application = build_application(webhook_mode=True)
                await application.initialize()
                _webhook_application = application

    return _webhook_application


async def notification_job(context: CallbackContext) -> None:
    await send_due_notifications(context.bot)


def schedule_local_notifications(application: Application) -> None:
    if application.job_queue is None:
        raise RuntimeError("python-telegram-bot job queue is not available")

    hour, minute = get_check_time_parts()
    application.job_queue.run_daily(
        notification_job,
        time=dt_time(hour=hour, minute=minute, tzinfo=get_timezone()),
        name="service-reminder-daily-check",
    )