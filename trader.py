import json
import logging
import os
import asyncio
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
#  НАСТРОЙКИ АВТО-ТРЕЙДЕРА
# ──────────────────────────────────────────
STARTING_BALANCE = 10_000        # Стартовый баланс в $
RSI_OVERSOLD     = 35            # Покупаем когда RSI ниже этого
RSI_OVERBOUGHT   = 65            # Продаём когда RSI выше этого
TRADE_AMOUNT_PCT = 0.20          # Тратим 20% баланса на каждую сделку
COINS_TO_TRADE   = ["bitcoin", "ethereum", "solana"]  # Монеты для торговли
STATE_FILE       = "trader_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


# ──────────────────────────────────────────
#  СОХРАНЕНИЕ / ЗАГРУЗКА СОСТОЯНИЯ
# ──────────────────────────────────────────
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "balance_usd": STARTING_BALANCE,
        "holdings": {},       # {"bitcoin": {"amount": 0.5, "avg_price": 60000}}
        "trades": [],         # история сделок
        "total_trades": 0,
        "winning_trades": 0,
        "started_at": datetime.now().isoformat(),
    }


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────
#  RSI РАСЧЁТ
# ──────────────────────────────────────────
def calculate_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]

    if not gains:
        return 0.0
    if not losses:
        return 100.0

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


async def get_rsi_and_price(coin_id: str) -> dict:
    """Получаем цену и RSI для монеты"""
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": 3, "interval": "hourly"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()

            prices = [p[1] for p in data.get("prices", [])]
            if not prices:
                return {}

            rsi = calculate_rsi(prices)
            current_price = prices[-1]

            return {
                "coin_id": coin_id,
                "price": current_price,
                "rsi": rsi,
            }
    except Exception as e:
        logger.error(f"Ошибка RSI для {coin_id}: {e}")
        return {}


# ──────────────────────────────────────────
#  ЛОГИКА ТОРГОВЛИ
# ──────────────────────────────────────────
COIN_SYMBOLS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binancecoin": "BNB",
    "cardano": "ADA",
}


def execute_buy(state: dict, coin_id: str, price: float, rsi: float):
    """Покупаем монету"""
    symbol = COIN_SYMBOLS.get(coin_id, coin_id.upper())
    spend_usd = state["balance_usd"] * TRADE_AMOUNT_PCT

    if spend_usd < 10:
        return None  # Слишком мало денег

    # Уже держим эту монету — не покупаем ещё
    if coin_id in state["holdings"] and state["holdings"][coin_id]["amount"] > 0:
        return None

    amount = spend_usd / price
    state["balance_usd"] -= spend_usd

    state["holdings"][coin_id] = {
        "amount": amount,
        "avg_price": price,
        "invested_usd": spend_usd,
    }

    trade = {
        "type": "BUY",
        "coin": symbol,
        "coin_id": coin_id,
        "amount": amount,
        "price": price,
        "usd": spend_usd,
        "rsi": rsi,
        "time": datetime.now().strftime("%d.%m %H:%M"),
    }
    state["trades"].append(trade)
    state["total_trades"] += 1
    save_state(state)
    return trade


def execute_sell(state: dict, coin_id: str, price: float, rsi: float):
    """Продаём монету"""
    symbol = COIN_SYMBOLS.get(coin_id, coin_id.upper())

    if coin_id not in state["holdings"] or state["holdings"][coin_id]["amount"] <= 0:
        return None  # Нечего продавать

    holding = state["holdings"][coin_id]
    amount = holding["amount"]
    invested = holding["invested_usd"]
    received_usd = amount * price
    profit = received_usd - invested
    profit_pct = (profit / invested) * 100

    state["balance_usd"] += received_usd
    del state["holdings"][coin_id]

    if profit > 0:
        state["winning_trades"] = state.get("winning_trades", 0) + 1

    trade = {
        "type": "SELL",
        "coin": symbol,
        "coin_id": coin_id,
        "amount": amount,
        "price": price,
        "usd": received_usd,
        "profit": profit,
        "profit_pct": profit_pct,
        "rsi": rsi,
        "time": datetime.now().strftime("%d.%m %H:%M"),
    }
    state["trades"].append(trade)
    state["total_trades"] += 1
    save_state(state)
    return trade


# ──────────────────────────────────────────
#  ГЛАВНАЯ ФУНКЦИЯ — вызывается по расписанию
# ──────────────────────────────────────────
async def run_trading_cycle() -> list:
    """Один цикл торговли — проверяем все монеты и торгуем"""
    state = load_state()
    executed_trades = []

    for coin_id in COINS_TO_TRADE:
        await asyncio.sleep(3)  # Пауза между запросами
        data = await get_rsi_and_price(coin_id)
        if not data:
            continue

        price = data["price"]
        rsi = data["rsi"]
        logger.info(f"{coin_id}: цена=${price:,.2f}, RSI={rsi:.1f}")

        if rsi < RSI_OVERSOLD:
            trade = execute_buy(state, coin_id, price, rsi)
            if trade:
                executed_trades.append(trade)
                logger.info(f"🟢 ПОКУПКА {trade['coin']} по ${price:,.2f}")

        elif rsi > RSI_OVERBOUGHT:
            trade = execute_sell(state, coin_id, price, rsi)
            if trade:
                executed_trades.append(trade)
                logger.info(f"🔴 ПРОДАЖА {trade['coin']} по ${price:,.2f}")

    return executed_trades


# ──────────────────────────────────────────
#  ФОРМАТИРОВАНИЕ СООБЩЕНИЙ
# ──────────────────────────────────────────
def format_trade_message(trade: dict) -> str:
    """Сообщение о конкретной сделке"""
    if trade["type"] == "BUY":
        return (
            f"🟢 *ПОКУПКА — {trade['coin']}*\n"
            f"├ Цена: `${trade['price']:,.2f}`\n"
            f"├ Куплено: `{trade['amount']:.6f} {trade['coin']}`\n"
            f"├ Потрачено: `${trade['usd']:,.2f}`\n"
            f"└ RSI сигнал: `{trade['rsi']:.1f}` 📉 _перепродан_\n"
            f"_⏰ {trade['time']}_"
        )
    else:
        profit = trade.get("profit", 0)
        pct = trade.get("profit_pct", 0)
        emoji = "✅" if profit >= 0 else "❌"
        sign = "+" if profit >= 0 else ""
        return (
            f"🔴 *ПРОДАЖА — {trade['coin']}*\n"
            f"├ Цена: `${trade['price']:,.2f}`\n"
            f"├ Продано: `{trade['amount']:.6f} {trade['coin']}`\n"
            f"├ Получено: `${trade['usd']:,.2f}`\n"
            f"├ Прибыль: `{sign}${profit:,.2f}` ({sign}{pct:.2f}%) {emoji}\n"
            f"└ RSI сигнал: `{trade['rsi']:.1f}` 📈 _перекуплен_\n"
            f"_⏰ {trade['time']}_"
        )


def format_portfolio_message() -> str:
    """Сводка по портфолио"""
    state = load_state()
    balance = state["balance_usd"]
    holdings = state["holdings"]
    trades = state["trades"]
    total = state["total_trades"]
    wins = state.get("winning_trades", 0)

    # Считаем стоимость холдингов (по цене покупки — без реального запроса)
    holdings_value = sum(
        h["amount"] * h["avg_price"] for h in holdings.values()
    )
    total_value = balance + holdings_value
    pnl = total_value - STARTING_BALANCE
    pnl_pct = (pnl / STARTING_BALANCE) * 100
    pnl_sign = "+" if pnl >= 0 else ""
    pnl_emoji = "📈" if pnl >= 0 else "📉"

    winrate = (wins / total * 100) if total > 0 else 0

    lines = []
    lines.append("💼 *ДЕМО ПОРТФОЛИО*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💵 Свободные $: `${balance:,.2f}`")
    lines.append(f"📦 В позициях: `${holdings_value:,.2f}`")
    lines.append(f"💰 Итого: `${total_value:,.2f}`")
    lines.append(f"{pnl_emoji} P&L: `{pnl_sign}${pnl:,.2f}` ({pnl_sign}{pnl_pct:.2f}%)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    if holdings:
        lines.append("📊 *ОТКРЫТЫЕ ПОЗИЦИИ*")
        for coin_id, h in holdings.items():
            sym = COIN_SYMBOLS.get(coin_id, coin_id.upper())
            lines.append(f"├ *{sym}*: `{h['amount']:.6f}` по `${h['avg_price']:,.2f}`")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📈 Сделок всего: `{total}`")
    lines.append(f"✅ Прибыльных: `{wins}` ({winrate:.0f}%)")

    # Последние 3 сделки
    if trades:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🕐 *ПОСЛЕДНИЕ СДЕЛКИ*")
        for t in trades[-3:][::-1]:
            tp = "🟢" if t["type"] == "BUY" else "🔴"
            profit_str = ""
            if t["type"] == "SELL":
                p = t.get("profit", 0)
                profit_str = f" `{'+' if p>=0 else ''}{p:,.0f}$`"
            lines.append(f"{tp} *{t['coin']}* ${t['price']:,.0f}{profit_str} — {t['time']}")

    lines.append(f"\n_Старт: ${STARTING_BALANCE:,} | Стратегия: RSI {RSI_OVERSOLD}/{RSI_OVERBOUGHT}_")
    return "\n".join(lines)
