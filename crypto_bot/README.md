# 🤖 Крипто-бот для Telegram

Бот автоматически отправляет:
- **Ежедневно в 09:00** — обзор рынка, топ монеты, гейнеры/луузеры, новые листинги, Fear & Greed
- **Каждое воскресенье в 10:00** — недельный отчёт + AI-прогноз на следующую неделю

---

## 🚀 УСТАНОВКА (5 минут)

### Шаг 1 — Установи Python
Скачай Python 3.11+ с https://python.org/downloads
При установке поставь галочку "Add to PATH"

### Шаг 2 — Создай бота в Telegram
1. Открой Telegram, найди **@BotFather**
2. Напиши `/newbot`
3. Придумай имя и username боту
4. Скопируй токен (выглядит как `7123456789:AAF...`)

### Шаг 3 — Узнай свой Chat ID
1. Напиши боту **@userinfobot** в Telegram
2. Он пришлёт твой ID (число, например `123456789`)

### Шаг 4 — Заполни config.py
Открой файл `config.py` и вставь:
```python
TELEGRAM_TOKEN = "7123456789:AAF..."   # токен от BotFather
CHAT_ID = "123456789"                   # твой ID
ANTHROPIC_API_KEY = "sk-ant-..."        # ключ Claude (опционально)
```

**Где взять Claude API ключ (для AI-прогнозов):**
- Зайди на https://console.anthropic.com
- Settings → API Keys → Create Key
- Вставь в config.py

### Шаг 5 — Установи зависимости
Открой папку с ботом в терминале/командной строке:
```bash
pip install -r requirements.txt
```

### Шаг 6 — Запусти бота
```bash
python bot.py
```

При первом запуске бот сразу пришлёт тебе отчёт ✅

---

## 📁 Структура файлов

```
crypto_bot/
├── bot.py              # Главный файл, запускать его
├── config.py           # ⚠️ СЮДА вставляй все ключи
├── data_fetcher.py     # Загрузка данных с CoinGecko
├── report_generator.py # Генерация текста отчётов
├── requirements.txt    # Зависимости
└── README.md           # Это файл
```

---

## 💡 Настройка расписания

В `config.py` можно изменить:
- `TOP_COINS_COUNT` — сколько монет в топе (по умолчанию 10)
- `NEW_LISTINGS_COUNT` — сколько новых листингов (по умолчанию 5)
- `TIMEZONE` — часовой пояс (по умолчанию Europe/Moscow)

В `bot.py` можно изменить время отправки:
```python
scheduler.add_job(send_daily_report, "cron", hour=9, minute=0)  # 09:00
```

---

## 🔧 Чтобы бот работал постоянно

**На Windows:** Запусти через планировщик задач или оставь окно терминала открытым.

**Автозапуск на Windows:**
1. Нажми Win+R, введи `shell:startup`
2. Создай файл `start_bot.bat`:
```bat
cd C:\путь\до\crypto_bot
python bot.py
```
3. Перетащи файл в папку автозапуска

---

## ❓ Частые проблемы

**"Module not found"** → запусти `pip install -r requirements.txt`

**"Unauthorized"** → проверь токен в config.py

**"Chat not found"** → проверь Chat ID, напиши боту что-нибудь первым

**AI не работает** → проверь API ключ или поставь `AI_PROVIDER = "none"`

---

## 📊 Используемые API (бесплатные)

- **CoinGecko** — цены, капитализация, листинги (бесплатно, лимит 30 запросов/мин)
- **Alternative.me** — Fear & Greed индекс (бесплатно, без лимитов)
- **Anthropic Claude** — AI-анализ (платный, ~$0.001 за отчёт)
