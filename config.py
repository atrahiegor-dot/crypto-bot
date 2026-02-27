# ==========================================
#   НАСТРОЙКИ БОТА
# ==========================================

TELEGRAM_TOKEN = "8285082648:AAHhQzNdOjH-zBcnxbpwzAZcaA4yDXNGgJU"
CHAT_ID = "1248347380"

# AI для прогнозов: "claude", "openai" или "none"
AI_PROVIDER = "none"
ANTHROPIC_API_KEY = "ВАШ_ANTHROPIC_KEY"
OPENAI_API_KEY = ""

# ==========================================
#   WHALE ALERT (крупные переводы китов)
#   Бесплатный ключ: https://whale-alert.io
#   Регистрация занимает 1 минуту
# ==========================================
WHALE_ALERT_KEY = "ВАШ_WHALE_ALERT_KEY"
WHALE_MIN_USD = 1_000_000   # Минимальная сумма перевода ($1 млн)

# ==========================================
#   АЛЕРТЫ НА РЕЗКИЕ ДВИЖЕНИЯ ЦЕНЫ
# ==========================================
PRICE_ALERT_ENABLED = True
PRICE_ALERT_THRESHOLD = 5.0   # % изменения за час чтобы получить алерт
PRICE_ALERT_COINS = ["bitcoin", "ethereum", "solana", "binancecoin"]  # За какими следить

# ==========================================
#   НАСТРОЙКИ ОТЧЁТА
# ==========================================
TOP_COINS_COUNT = 10
NEW_LISTINGS_COUNT = 5
TIMEZONE = "Europe/Moscow"
