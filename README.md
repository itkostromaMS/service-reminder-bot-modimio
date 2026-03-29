# Service Reminder Bot

Telegram-бот для отслеживания сроков оплаченных услуг с напоминаниями за 7, 3 и 1 день, а также в день истечения.

## Что реализовано

- Добавление услуги через кнопки и текстовый ввод
- Просмотр списка услуг
- Продление на 1 месяц, 3 месяца, 6 месяцев, 1 год или произвольной датой
- Удаление одной услуги и очистка всего списка
- Автоматические уведомления за 7, 3, 1 день и после истечения
- Локальный запуск через polling
- Деплой в Vercel через webhook + cron
- Переключаемое хранилище:
  - `file` для локальной разработки
  - `redis` для Vercel и других stateless-окружений

## Структура проекта

```text
service-reminder-bot-modimio/
├── app.py
├── bot.py
├── config.py
├── handlers.py
├── notifier.py
├── storage.py
├── telegram_app.py
├── requirements.txt
├── vercel.json
└── .env.example
```

## Переменные окружения

Обязательные:

```env
BOT_TOKEN=<telegram bot token>
APP_TZ=Europe/Moscow
CHECK_TIME=09:00
STORAGE_BACKEND=file
```

Дополнительно для Vercel и Redis:

```env
REDIS_URL=redis://default:password@host:port
WEBHOOK_SECRET=<secret passed to Telegram webhook>
CRON_SECRET=<secret for manual cron запусков>
```

## Локальный запуск

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

После этого заполните `.env` и запустите:

```powershell
python bot.py
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

## Как работает хранение данных

### Локально

При `STORAGE_BACKEND=file` бот хранит всё в `data.json` в корне проекта.

### В Vercel

Локальный файл в Vercel использовать нельзя: файловая система serverless-функций не подходит для постоянного хранения. Поэтому для Vercel нужно переключить backend на Redis:

```env
STORAGE_BACKEND=redis
REDIS_URL=<your redis url>
```

В Redis сохраняются:

- список услуг пользователя
- флаги отправленных уведомлений
- текущее состояние многошагового ввода
- служебная метка последнего cron-запуска

Это нужно, потому что webhook-вызовы в Vercel stateless, и состояние нельзя держать только в памяти процесса.

## Деплой в Vercel

### 1. Создайте бота в Telegram

1. Откройте `@BotFather`
2. Выполните `/newbot`
3. Получите токен
4. Подготовьте секрет для webhook, например случайную длинную строку

### 2. Подготовьте постоянное хранилище

В Vercel KV больше не доступен как отдельный новый продукт, поэтому используйте Redis-интеграцию из Vercel Marketplace, например Upstash Redis.

После подключения Redis получите строку подключения и задайте её в `REDIS_URL`.

### 3. Импортируйте проект в Vercel

1. Загрузите репозиторий в GitHub
2. В Vercel выберите `Add New Project`
3. Импортируйте этот репозиторий
4. Убедитесь, что Vercel определил Python-проект по `requirements.txt`

### 4. Добавьте переменные окружения в Vercel

Минимальный набор для продакшена:

```env
BOT_TOKEN=<telegram token>
APP_TZ=Europe/Moscow
CHECK_TIME=09:00
STORAGE_BACKEND=redis
REDIS_URL=<redis connection url>
WEBHOOK_SECRET=<random secret>
CRON_SECRET=<random secret>
```

### 5. Задеплойте проект

После первого деплоя получите адрес вида:

```text
https://your-project.vercel.app
```

Проверьте health endpoint:

```text
https://your-project.vercel.app/api/health
```

### 6. Зарегистрируйте webhook в Telegram

Откройте в браузере или вызовите через `curl`:

```text
https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://your-project.vercel.app/api/webhook&secret_token=<WEBHOOK_SECRET>
```

Проверить webhook можно так:

```text
https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
```

### 7. Как работают напоминания в Vercel

В проект уже добавлен `vercel.json` с cron-задачей:

```json
{
  "crons": [
    {
      "path": "/api/cron",
      "schedule": "0 6 * * *"
    }
  ]
}
```

Почему именно так:

- Vercel Cron работает только в UTC
- на Hobby доступен только один запуск в сутки

Итог: подберите UTC-время в cron под ваш `APP_TZ` и `CHECK_TIME`. Для `APP_TZ=Europe/Moscow` и `CHECK_TIME=09:00` подходит `0 6 * * *`.

Если нужно больше одного запуска в день, потребуется Vercel Pro.

### 8. Ручной запуск cron для проверки

Если нужно вручную проверить уведомления, можно открыть:

```text
https://your-project.vercel.app/api/cron?token=<CRON_SECRET>&force=1
```

`force=1` отключает временное окно и принудительно запускает проверку.

## Поведение бота

### Команды

- `/start` — главное меню
- `/help` — инструкция
- `/list` — текстовый способ открыть список услуг

### Напоминания

- за 7 дней — `🟡`
- за 3 дня — `🟠`
- за 1 день — `🔴`
- в день истечения и позже, если финальное уведомление ещё не отправлялось — `⛔`

### Продление

Продление по шаблонам считается от текущей даты окончания услуги, а не от сегодняшней даты. Это соответствует задаче из спецификации.

## Ограничения

- Для локального режима JSON-файл подходит нормально
- Для Vercel JSON-хранилище не подходит из-за stateless serverless runtime
- Если Redis временно недоступен, bot webhook и cron не смогут надёжно читать и сохранять данные

## Основные файлы

- `bot.py` — локальный запуск через polling
- `app.py` — FastAPI entrypoint для Vercel
- `handlers.py` — вся логика Telegram-интерфейса
- `storage.py` — работа с JSON или Redis
- `notifier.py` — логика ежедневных уведомлений
- `telegram_app.py` — сборка и инициализация `python-telegram-bot`