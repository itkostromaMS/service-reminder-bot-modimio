from telegram import Update

from telegram_app import build_application, schedule_local_notifications


def main() -> None:
    application = build_application(webhook_mode=False)
    schedule_local_notifications(application)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()