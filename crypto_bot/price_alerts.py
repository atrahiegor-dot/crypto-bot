import asyncio
import logging
from datetime import datetime
from telegram import Bot
from telegram.constants import ParseMode
from data_fetcher import CryptoDataFetcher
from config import TELEGRAM_TOKEN, CHAT_ID, PRICE_ALERT_THRESHOLD, PRICE_ALERT_COINS

logger = logging.getLogger(__name__)

# Хранит последние цены для сравнения
_last_prices = {}


async def check_price_alerts():
    """Проверяет резкие движения каждые 30 минут"""
    global _last_prices
    bot = Bot(token=TELEGRAM_TOKEN)
    fetcher = CryptoDataFetcher()

    try:
        coins_str = ",".join(PRICE_ALERT_COINS)
        data = await fetcher.fetch(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": coins_str,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_1hr_change": "true",
            }
        )

        if not data:
            return

        alerts = []
        for coin_id, prices in data.items():
            current_price = prices.get("usd", 0)
            change_1h = prices.get("usd_1h_change", 0) or 0
            change_24h = prices.get("usd_24h_change", 0) or 0

            # Собственное отслеживание между проверками (каждые 30 мин)
            if coin_id in _last_prices and _last_prices[coin_id] > 0:
                own_change = ((current_price - _last_prices[coin_id]) / _last_prices[coin_id]) * 100
                if abs(own_change) >= PRICE_ALERT_THRESHOLD:
                    change_1h = own_change  # используем собственное изменение
            _last_prices[coin_id] = current_price

            # Проверяем резкое движение
            if abs(change_1h) >= PRICE_ALERT_THRESHOLD:
                direction = "🚀 ВЫРОС" if change_1h > 0 else "💥 УПАЛ"
                symbol = coin_id.upper().replace("-2", "").replace("COIN", "")
                alerts.append({
                    "coin": symbol,
                    "price": current_price,
                    "change_1h": change_1h,
                    "change_24h": change_24h,
                    "direction": direction
                })

        if alerts:
            msg = "⚡ *АЛЕРТ: РЕЗКОЕ ДВИЖЕНИЕ ЦЕНЫ*\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
            for a in alerts:
                sign = "+" if a["change_1h"] > 0 else ""
                sign24 = "+" if a["change_24h"] > 0 else ""
                msg += f"{'🚀' if a['change_1h'] > 0 else '💥'} *{a['coin']}* {a['direction']}\n"
                msg += f"├ Цена: `${a['price']:,.4f}`\n"
                msg += f"├ За 1ч: `{sign}{a['change_1h']:.2f}%`\n"
                msg += f"└ За 24ч: `{sign24}{a['change_24h']:.2f}%`\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"_⏰ {datetime.now().strftime('%H:%M')}_"

            await bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            logger.info(f"Отправлено {len(alerts)} алертов")

    except Exception as e:
        logger.error(f"Ошибка проверки алертов: {e}")
    finally:
        if fetcher.session and not fetcher.session.closed:
            await fetcher.session.close()
