import asyncio
import logging
import aiohttp
import hashlib
import hmac
import time
from datetime import datetime

logger = logging.getLogger(__name__)

BYBIT_API_KEY = '8odB5cpZg76UHvoAnO'
BYBIT_API_SECRET = '8ggHi0uUDkehdPNKsyPoO9ZINppEm1RF4BxD'
BYBIT_BASE = 'https://api-testnet.bybit.com'
TRADE_SYMBOL = 'BTCUSDT'
TRADE_QTY = '0.001'
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65


def make_sign_v5(api_secret, timestamp, api_key, recv_window, body):
    param_str = str(timestamp) + api_key + str(recv_window) + body
    return hmac.new(api_secret.encode('utf-8'), param_str.encode('utf-8'), hashlib.sha256).hexdigest()


async def bybit_get_signed(endpoint, params=None):
    if params is None:
        params = {}
    timestamp = str(int(time.time() * 1000))
    recv_window = '5000'
    query_string = '&'.join([f'{k}={v}' for k, v in params.items()])
    sign = make_sign_v5(BYBIT_API_SECRET, timestamp, BYBIT_API_KEY, recv_window, query_string)
    headers = {
        'X-BAPI-API-KEY': BYBIT_API_KEY,
        'X-BAPI-TIMESTAMP': timestamp,
        'X-BAPI-SIGN': sign,
        'X-BAPI-RECV-WINDOW': recv_window,
    }
    url = BYBIT_BASE + endpoint
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        logger.error(f'GET signed error: {e}')
        return {}


async def bybit_post_signed(endpoint, body_dict):
    import json
    timestamp = str(int(time.time() * 1000))
    recv_window = '5000'
    body_str = json.dumps(body_dict)
    sign = make_sign_v5(BYBIT_API_SECRET, timestamp, BYBIT_API_KEY, recv_window, body_str)
    headers = {
        'X-BAPI-API-KEY': BYBIT_API_KEY,
        'X-BAPI-TIMESTAMP': timestamp,
        'X-BAPI-SIGN': sign,
        'X-BAPI-RECV-WINDOW': recv_window,
        'Content-Type': 'application/json',
    }
    url = BYBIT_BASE + endpoint
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=body_str, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        logger.error(f'POST signed error: {e}')
        return {}


async def bybit_get_public(endpoint, params=None):
    url = BYBIT_BASE + endpoint
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        logger.error(f'GET public error: {e}')
        return {}


async def get_balance():
    data = await bybit_get_signed('/v5/account/wallet-balance', {'accountType': 'UNIFIED'})
    logger.info(f'Balance response: {data}')
    try:
        coins = data['result']['list'][0]['coin']
        result = {}
        for c in coins:
            if float(c.get('walletBalance', 0)) > 0:
                result[c['coin']] = {
                    'balance': float(c['walletBalance']),
                    'usd': float(c.get('usdValue', 0))
                }
        return result
    except Exception as e:
        logger.error(f'Balance parse error: {e}')
        return {}


async def get_klines(symbol, interval='60', limit=50):
    data = await bybit_get_public('/v5/market/kline', {
        'category': 'spot', 'symbol': symbol,
        'interval': interval, 'limit': limit
    })
    try:
        return [float(k[4]) for k in reversed(data['result']['list'])]
    except Exception:
        return []


async def get_price(symbol):
    data = await bybit_get_public('/v5/market/tickers', {'category': 'spot', 'symbol': symbol})
    try:
        return float(data['result']['list'][0]['lastPrice'])
    except Exception:
        return 0.0


def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    if not gains: return 0.0
    if not losses: return 100.0
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


async def place_order(side, symbol, qty):
    body = {
        'category': 'spot',
        'symbol': symbol,
        'side': side,
        'orderType': 'Market',
        'qty': qty
    }
    return await bybit_post_signed('/v5/order/create', body)


async def run_bybit_trading_cycle():
    trades = []
    prices = await get_klines(TRADE_SYMBOL)
    if not prices:
        logger.warning('Не удалось получить свечи')
        return []
    rsi = calc_rsi(prices)
    price = await get_price(TRADE_SYMBOL)
    balance = await get_balance()
    btc_balance = balance.get('BTC', {}).get('balance', 0.0)
    logger.info(f'BTC: ${price:,.2f} | RSI: {rsi:.1f} | BTC: {btc_balance:.6f}')
    if rsi < RSI_OVERSOLD and btc_balance < 0.0001:
        result = await place_order('Buy', TRADE_SYMBOL, TRADE_QTY)
        if result.get('retCode') == 0:
            trades.append({'type': 'BUY', 'price': price, 'qty': TRADE_QTY, 'rsi': rsi,
                'order_id': result.get('result', {}).get('orderId', ''),
                'time': datetime.now().strftime('%d.%m %H:%M')})
        else:
            logger.error(f'Ошибка покупки: {result}')
    elif rsi > RSI_OVERBOUGHT and btc_balance >= 0.001:
        qty = str(round(btc_balance, 3))
        result = await place_order('Sell', TRADE_SYMBOL, qty)
        if result.get('retCode') == 0:
            trades.append({'type': 'SELL', 'price': price, 'qty': qty, 'rsi': rsi,
                'order_id': result.get('result', {}).get('orderId', ''),
                'time': datetime.now().strftime('%d.%m %H:%M')})
        else:
            logger.error(f'Ошибка продажи: {result}')
    return trades


def format_bybit_trade(trade):
    if trade['type'] == 'BUY':
        return (
            '*BYBIT TESTNET*\n'
            '*ПОКУПКА BTC*\n'
            f"Цена: `${trade['price']:,.2f}`\n"
            f"Куплено: `{trade['qty']} BTC`\n"
            f"RSI: `{trade['rsi']:.1f}` перепродан\n"
            f"Order: `{trade['order_id']}`\n"
            f"Время: {trade['time']}"
        )
    return (
        '*BYBIT TESTNET*\n'
        '*ПРОДАЖА BTC*\n'
        f"Цена: `${trade['price']:,.2f}`\n"
        f"Продано: `{trade['qty']} BTC`\n"
        f"RSI: `{trade['rsi']:.1f}` перекуплен\n"
        f"Order: `{trade['order_id']}`\n"
        f"Время: {trade['time']}"
    )


async def format_bybit_portfolio():
    balance = await get_balance()
    price = await get_price(TRADE_SYMBOL)
    lines = ['*BYBIT TESTNET — ДЕМО ПОРТФОЛИО*', '━━━━━━━━━━━━━━━━━━━━━━']
    if not balance:
        lines.append('Баланс недоступен — проверь API ключи')
        return '\n'.join(lines)
    total = 0
    for coin, d in balance.items():
        usd = d['usd'] if d['usd'] > 0 else d['balance'] * (price if coin == 'BTC' else 1)
        total += usd
        lines.append(f"*{coin}*: `{d['balance']:.4f}` = `${usd:,.2f}`")
    lines.append('━━━━━━━━━━━━━━━━━━━━━━')
    lines.append(f'Итого: `${total:,.2f}`')
    lines.append(f'BTC цена: `${price:,.2f}`')
    lines.append(f'Стратегия RSI: покупка <{RSI_OVERSOLD} / продажа >{RSI_OVERBOUGHT}')
    return '\n'.join(lines)
