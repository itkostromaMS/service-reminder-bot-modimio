from datetime import date

from dateutil.relativedelta import relativedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

import storage
from notifier import format_days_left, parse_date, service_status_icon, today_local

MAIN_MENU_TEXT = (
    "🤖 Service Reminder Bot\n\n"
    "Я помогу не пропустить окончание оплаченных услуг.\n"
    "Управление через кнопки — никаких команд запоминать не нужно."
)

SELECTION_PAGE_SIZE = 10

HELP_TEXT = (
    "🤖 Service Reminder Bot\n\n"
    "Управление полностью через кнопки — никаких команд запоминать не нужно.\n\n"
    "📌 Как пользоваться:\n"
    "1. Нажмите ➕ Добавить услугу\n"
    "2. Введите название и дату окончания\n"
    "3. Бот сам напомнит за 7, 3 и 1 день\n"
    "4. Выберите продление через меню 🔄\n\n"
    "🔔 Уведомления: за 7, 3 и 1 день до окончания\n"
    "📅 Формат даты: YYYY-MM-DD"
)


def main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Добавить услугу", callback_data="act:add"),
            InlineKeyboardButton("📋 Мои услуги", callback_data="act:list"),
        ]
    ])


def services_markup(services: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if services:
        rows.append([
            InlineKeyboardButton("🔄 Продлить услугу", callback_data="act:renew_menu:0"),
            InlineKeyboardButton("🗑 Удалить услугу", callback_data="act:del_menu:0"),
        ])

    footer = [InlineKeyboardButton("➕ Добавить услугу", callback_data="act:add")]
    rows.append(footer)

    if services:
        rows.append([InlineKeyboardButton("🗑 Удалить все", callback_data="act:clear")])

    return InlineKeyboardMarkup(rows)


def renew_markup(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 1 месяц", callback_data=f"act:renew_period:{service_id}:1m"),
            InlineKeyboardButton("📅 3 месяца", callback_data=f"act:renew_period:{service_id}:3m"),
        ],
        [
            InlineKeyboardButton("📅 6 месяцев", callback_data=f"act:renew_period:{service_id}:6m"),
            InlineKeyboardButton("📅 1 год", callback_data=f"act:renew_period:{service_id}:1y"),
        ],
        [
            InlineKeyboardButton("✏️ Другая дата", callback_data=f"act:renew_custom:{service_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"act:renew_cancel:{service_id}"),
        ],
    ])


def delete_confirm_markup(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"act:del_confirm:{service_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"act:del_cancel:{service_id}"),
        ]
    ])


def clear_confirm_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, удалить все", callback_data="act:clear_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="act:clear_cancel"),
        ]
    ])


def list_button_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("📋 Мои услуги", callback_data="act:list")]])


def add_button_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("➕ Добавить услугу", callback_data="act:add")]])


def build_services_text(services: list[dict]) -> str:
    if not services:
        return "📭 У вас нет отслеживаемых услуг."

    lines = ["📋 Ваши услуги:", ""]

    for index, service in enumerate(services, start=1):
        lines.append("━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(f"№{index} {service_status_icon(service)} {service['name']}")
        lines.append(f"   📅 {service['end_date']} ({format_days_left(service['end_date'])})")
        lines.append("")

    return "\n".join(lines).rstrip()


def build_selection_text(services: list[dict], page: int, title: str) -> str:
    if not services:
        return "📭 У вас нет отслеживаемых услуг."

    total_pages = (len(services) - 1) // SELECTION_PAGE_SIZE + 1
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * SELECTION_PAGE_SIZE
    end = min(start + SELECTION_PAGE_SIZE, len(services))

    lines = [f"{title}", f"Страница {safe_page + 1}/{total_pages}", ""]
    for number, service in enumerate(services[start:end], start=start + 1):
        lines.append(f"{number}. {service_status_icon(service)} {service['name']} — {service['end_date']}")

    lines.append("")
    lines.append("Выберите услугу кнопкой ниже:")
    return "\n".join(lines)


def selection_markup(services: list[dict], page: int, mode: str) -> InlineKeyboardMarkup:
    if not services:
        return add_button_markup()

    total_pages = (len(services) - 1) // SELECTION_PAGE_SIZE + 1
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * SELECTION_PAGE_SIZE
    end = min(start + SELECTION_PAGE_SIZE, len(services))

    rows: list[list[InlineKeyboardButton]] = []
    for number, service in enumerate(services[start:end], start=start + 1):
        rows.append([
            InlineKeyboardButton(
                f"№{number} {service['name']}",
                callback_data=f"act:{mode}_pick:{service['id']}:{safe_page}",
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if safe_page > 0:
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"act:{mode}_menu:{safe_page - 1}"))
    if safe_page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️ Далее", callback_data=f"act:{mode}_menu:{safe_page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("↩️ К списку", callback_data="act:list")])
    return InlineKeyboardMarkup(rows)


def build_add_date_prompt(name: str) -> str:
    return (
        f"📅 Введите дату окончания для «{name}»\n\n"
        "Формат: YYYY-MM-DD\n"
        "Например: 2026-12-31"
    )


def build_service_added_text(service: dict) -> str:
    return (
        f"✅ Услуга «{service['name']}» добавлена!\n\n"
        f"📅 Окончание: {service['end_date']} ({format_days_left(service['end_date'])})\n"
        f"🆔 ID: {service['id']}"
    )


def build_service_updated_text(service: dict, old_date: str, period_label: str | None = None) -> str:
    action = f" продлена на {period_label}" if period_label else " продлена"
    return (
        f"✅ Услуга «{service['name']}»{action}!\n\n"
        f"📅 Было: {old_date}\n"
        f"📅 Стало: {service['end_date']} ({format_days_left(service['end_date'])})\n"
        f"🆔 ID: {service['id']}"
    )


def build_renew_text(service: dict) -> str:
    return (
        f"🔄 Продление: «{service['name']}»\n\n"
        f"Текущая дата окончания: {service['end_date']}\n\n"
        "Выберите период продления:"
    )


def build_custom_date_text(service: dict) -> str:
    return (
        f"✏️ Произвольная дата для «{service['name']}»\n\n"
        f"Текущая дата окончания: {service['end_date']}\n\n"
        "Введите новую дату окончания:\n"
        "Формат: YYYY-MM-DD"
    )


def parse_user_date(value: str) -> date | None:
    try:
        return parse_date(value)
    except ValueError:
        return None


def get_period_delta(period_key: str) -> tuple[relativedelta, str] | tuple[None, None]:
    mapping = {
        "1m": (relativedelta(months=1), "1 месяц"),
        "3m": (relativedelta(months=3), "3 месяца"),
        "6m": (relativedelta(months=6), "6 месяцев"),
        "1y": (relativedelta(years=1), "1 год"),
    }
    return mapping.get(period_key, (None, None))


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    await storage.clear_user_state(str(update.effective_user.id))
    await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=main_menu_markup())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    await storage.clear_user_state(str(update.effective_user.id))
    await update.message.reply_text(HELP_TEXT, reply_markup=main_menu_markup())


async def list_services_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    user_id = str(update.effective_user.id)
    await storage.clear_user_state(user_id)
    services = await storage.get_services(user_id)
    await update.message.reply_text(build_services_text(services), reply_markup=services_markup(services))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    user_id = str(update.effective_user.id)
    state = await storage.get_user_state(user_id)
    step = state.get("step")
    text = update.message.text.strip()

    if step == "waiting_name":
        if not text:
            await update.message.reply_text("❌ Название не может быть пустым. Попробуйте ещё раз:")
            return

        await storage.set_user_state(user_id, {"step": "waiting_date", "name": text})
        await update.message.reply_text(build_add_date_prompt(text))
        return

    if step == "waiting_date":
        name = state.get("name", "")
        end_date = parse_user_date(text)
        if end_date is None:
            await update.message.reply_text("❌ Неверный формат даты. Используйте: YYYY-MM-DD\nПопробуйте ещё раз:")
            return

        service = await storage.add_service(user_id, name=name, end_date=end_date)
        await storage.clear_user_state(user_id)
        await update.message.reply_text(build_service_added_text(service), reply_markup=list_button_markup())
        return

    if step == "waiting_custom_date":
        service_id = state.get("service_id")
        if not service_id:
            await storage.clear_user_state(user_id)
            await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=main_menu_markup())
            return

        service = await storage.get_service(user_id, int(service_id))
        if not service:
            await storage.clear_user_state(user_id)
            await update.message.reply_text("❌ Услуга не найдена.", reply_markup=list_button_markup())
            return

        new_end_date = parse_user_date(text)
        if new_end_date is None:
            await update.message.reply_text("❌ Неверный формат даты. Используйте: YYYY-MM-DD\nПопробуйте ещё раз:")
            return

        current_end_date = parse_date(service["end_date"])
        if new_end_date <= current_end_date:
            await update.message.reply_text(
                f"❌ Новая дата должна быть позже текущей даты окончания ({service['end_date']}).\n"
                "Введите корректную дату:"
            )
            return

        updated_service, old_date = await storage.update_service_end_date(user_id, int(service_id), new_end_date)
        await storage.clear_user_state(user_id)
        await update.message.reply_text(build_service_updated_text(updated_service, old_date), reply_markup=list_button_markup())
        return

    await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=main_menu_markup())


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query or not update.effective_user:
        return

    query = update.callback_query
    user_id = str(update.effective_user.id)
    data = query.data or ""
    await query.answer()

    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if data == "act:add":
        await storage.set_user_state(user_id, {"step": "waiting_name"})
        await query.edit_message_text(
            "📝 Введите название услуги:\n\nНапример: Timeweb VPS, Яндекс 360, Reg.ru домен"
        )
        return

    if data == "act:list":
        await storage.clear_user_state(user_id)
        services = await storage.get_services(user_id)
        await query.edit_message_text(build_services_text(services), reply_markup=services_markup(services))
        return

    if action == "renew_menu" and len(parts) == 3:
        await storage.clear_user_state(user_id)
        page = int(parts[2])
        services = await storage.get_services(user_id)
        await query.edit_message_text(
            build_selection_text(services, page, "🔄 Выберите услугу для продления"),
            reply_markup=selection_markup(services, page, "renew"),
        )
        return

    if action == "del_menu" and len(parts) == 3:
        await storage.clear_user_state(user_id)
        page = int(parts[2])
        services = await storage.get_services(user_id)
        await query.edit_message_text(
            build_selection_text(services, page, "🗑 Выберите услугу для удаления"),
            reply_markup=selection_markup(services, page, "del"),
        )
        return

    if data == "act:clear":
        await storage.clear_user_state(user_id)
        services = await storage.get_services(user_id)
        count = len(services)
        await query.edit_message_text(
            "⚠️ Вы уверены, что хотите удалить ВСЕ услуги?\n"
            f"Это действие нельзя отменить. (Всего: {count})",
            reply_markup=clear_confirm_markup(),
        )
        return

    if data == "act:clear_confirm":
        removed_count = await storage.clear_services(user_id)
        await storage.clear_user_state(user_id)
        if removed_count:
            await query.edit_message_text("🗑 Все услуги удалены.", reply_markup=add_button_markup())
        else:
            await query.edit_message_text("📭 У вас нет отслеживаемых услуг.", reply_markup=add_button_markup())
        return

    if data == "act:clear_cancel":
        services = await storage.get_services(user_id)
        await query.edit_message_text(build_services_text(services), reply_markup=services_markup(services))
        return

    if action in {"renew", "renew_pick"} and len(parts) in {3, 4}:
        await storage.clear_user_state(user_id)
        service = await storage.get_service(user_id, int(parts[2]))
        if not service:
            await query.edit_message_text("❌ Услуга не найдена.", reply_markup=list_button_markup())
            return
        await query.edit_message_text(build_renew_text(service), reply_markup=renew_markup(service["id"]))
        return

    if action == "renew_period" and len(parts) == 4:
        service_id = int(parts[2])
        period_delta, period_label = get_period_delta(parts[3])
        service = await storage.get_service(user_id, service_id)

        if not service or period_delta is None or period_label is None:
            await query.edit_message_text("❌ Не удалось продлить услугу.", reply_markup=list_button_markup())
            return

        current_end_date = parse_date(service["end_date"])
        new_end_date = current_end_date + period_delta
        updated_service, old_date = await storage.update_service_end_date(user_id, service_id, new_end_date)
        await storage.clear_user_state(user_id)
        await query.edit_message_text(
            build_service_updated_text(updated_service, old_date, period_label),
            reply_markup=list_button_markup(),
        )
        return

    if action == "renew_custom" and len(parts) == 3:
        service = await storage.get_service(user_id, int(parts[2]))
        if not service:
            await query.edit_message_text("❌ Услуга не найдена.", reply_markup=list_button_markup())
            return

        await storage.set_user_state(user_id, {"step": "waiting_custom_date", "service_id": service["id"]})
        await query.edit_message_text(build_custom_date_text(service))
        return

    if action == "renew_cancel" and len(parts) == 3:
        await storage.clear_user_state(user_id)
        services = await storage.get_services(user_id)
        await query.edit_message_text(build_services_text(services), reply_markup=services_markup(services))
        return

    if action in {"del", "del_pick"} and len(parts) in {3, 4}:
        await storage.clear_user_state(user_id)
        service = await storage.get_service(user_id, int(parts[2]))
        if not service:
            await query.edit_message_text("❌ Услуга не найдена.", reply_markup=list_button_markup())
            return

        await query.edit_message_text(
            f"⚠️ Удалить услугу «{service['name']}»?",
            reply_markup=delete_confirm_markup(service["id"]),
        )
        return

    if action == "del_confirm" and len(parts) == 3:
        removed = await storage.delete_service(user_id, int(parts[2]))
        await storage.clear_user_state(user_id)
        if not removed:
            await query.edit_message_text("❌ Услуга не найдена.", reply_markup=list_button_markup())
            return

        await query.edit_message_text(
            f"🗑 Услуга «{removed['name']}» удалена.",
            reply_markup=list_button_markup(),
        )
        return

    if action == "del_cancel" and len(parts) == 3:
        services = await storage.get_services(user_id)
        await query.edit_message_text(build_services_text(services), reply_markup=services_markup(services))
        return

    await query.edit_message_text(MAIN_MENU_TEXT, reply_markup=main_menu_markup())


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_services_message))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern=r"^act:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))