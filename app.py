from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update

from config import CRON_SECRET, WEBHOOK_SECRET, validate_config
from notifier import mark_cron_executed, send_due_notifications, should_execute_cron
from telegram_app import get_webhook_application

app = FastAPI(title="Service Reminder Bot")


@app.get("/")
async def root() -> dict:
    return {"ok": True, "service": "service-reminder-bot"}


@app.get("/api/health")
async def health() -> dict:
    validate_config()
    return {"ok": True}


@app.post("/api/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    validate_config()

    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    payload = await request.json()
    application = await get_webhook_application()
    update = Update.de_json(payload, application.bot)
    await application.process_update(update)
    return {"ok": True}


@app.get("/api/cron")
async def cron(request: Request, token: str | None = None, force: int = 0) -> dict:
    validate_config()

    user_agent = request.headers.get("user-agent", "")
    authorized = user_agent.startswith("vercel-cron/") or (CRON_SECRET and token == CRON_SECRET)
    if not authorized:
        raise HTTPException(status_code=401, detail="Unauthorized cron request")

    if not force:
        should_run, reason = await should_execute_cron(window_minutes=5)
        if not should_run:
            return {"ok": True, "skipped": True, "reason": reason}

    application = await get_webhook_application()
    sent = await send_due_notifications(application.bot)

    if not force:
        await mark_cron_executed()

    return {"ok": True, "sent": sent}