import os

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
CHAT_ID = os.getenv('CHAT_ID', '')

AI_PROVIDER = os.getenv('AI_PROVIDER', 'none')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

WHALE_MIN_USD = 1_000_000
PRICE_ALERT_ENABLED = True
PRICE_ALERT_THRESHOLD = 5.0
PRICE_ALERT_COINS = ['bitcoin', 'ethereum', 'solana', 'binancecoin']
TOP_COINS_COUNT = 10
NEW_LISTINGS_COUNT = 5
TIMEZONE = 'Europe/Moscow'
