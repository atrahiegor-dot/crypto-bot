import asyncio
import json
import logging
import aiohttp
import hashlib
import hmac
import time
import os
from datetime import datetime
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

BINANCE_API_KEY    = os.getenv('BINANCE_API_KEY', 'm1j7K2A1nMwIcURTQypLBr3wE0rzC5YQ3qqYux57eLAnuiV0dohwvAYwHdX6ohq0')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', 'arcrLVOeNxFxNQprAkTBZj8MxYCj8ETcCypAf1qkF8eL6eFyLzViwq64sh8uwcSO')
BINANCE_BASE       = 'https://testnet.binance.vision'

TRADE_SYMBOL   = 'BTCUSDT'
TRADE_QTY      = '0.001'
RSI_OVERSOLD   = 35
RSI_OVERBOUGHT = 65


def _sign(secret: str, params: dict) -> str:
    query = urlencode(params)
    return hmac.new(secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()


def _auth_headers() -> dict:
    return {'X-MBX-APIKEY': BINANCE_API_KEY}


async def binance_get_signed(endpoint: str, params: dict = None):
    params = params or {}
    params['timestamp'] = int(time.time() * 1000)
    params['recvWindow'] = 5000
    query = urlencode(params)
    signature = hmac.new(BINANCE_API_SECRET.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
    url = BINANCE_BASE + endpoint + '?' + query + '&signature=' + signature
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=_auth_headers(),
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                text = await r.text()
                logger.info(f'[{endpoint}] status={r.status} body={text[:300]}')
                return json.loads(text)
    except Exception as e:
        logger.error(f'GET signed error: {e}')
        return {}


async def binance_post_signed(endpoint: str, params: dict = None):
    params = params or {}
    params['timestamp'] = int(time.time() * 1000)
    params['recvWindow'] = 5000
    query = urlencode(params)
    signature = hmac.new(BINANCE_API_SECRET.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
    url = BINANCE_BASE + endpoint + '?' + query + '&signature=' + signature
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=_auth_headers(),
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                text = await r.text()
                logger.info(f'[{endpoint}] status={r.status} body={text[:300]}')
                return json.loads(text)
    except Exception as e:
        logger.error(f'POST signed error: {e}')
        return {}


async def binance_get_public(endpoint: str, params: dict = None):
    url = BINANCE_BASE + endpoint
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                return json.loads(await r.text())
    except Exception as e:
        logger.error(f'GET public error: {e}')
        return {}


async def get_klines(symbol: str, interval: str = '1h', limit: int = 50) -> list:
    data = await binance_get_public('/api/v3/klines', {
        'symbol': symbol, 'interval': interval, 'limit': limit
    })
    try:
        return [float(k[4]) for k in data]
    except Exception:
        return []


async def get_price(symbol: str) -> float:
    data = await binance_get_public('/api/v3/ticker/price', {'symbol': symbol})
    try:
        return float(data['price'])
    except Exception:
        return 0.0


async def get_balance() -> dict:
    logger.info(f'KEY задан: {bool(BINANCE_API_KEY)} | SECRET задан: {bool(BINANCE_API_SECRET)}')
    data = await binance_get_signed('/api/v3/account')
    try:
        result = {}
        for asset in data.get('balances', []):
            free   = float(asset['free'])
            locked = float(asset['locked'])
            total  = free + locked
            if total > 0:
                result[asset['asset']] = {
                    'balance': total,
                    'free': free,
                    'usd': 0.0
                }
        if 'BTC' in result:
            price = await get_price(TRADE_SYMBOL)
            result['BTC']['usd'] = result['BTC']['balance'] * price
        return result
    except Exception as e:
        logger.error(f'Balance parse error: {e}')
        return {}


def calc_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    recent = deltas[-period:]
    avg_gain = sum(d for d in recent if d > 0) / period
    avg_loss = sum(-d for d in recent if d < 0) / period
    if avg_gain == 0: return 0.0
    if avg_loss == 0: return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


async def place_order(side: str, symbol: str, qty: str) -> dict:
    return await binance_post_signed('/api/v3/order', {
        'symbol':   symbol,
        'side':     side,
        'type':     'MARKET',
        'quantity': qty,
    })


async def run_bybit_trading_cycle() -> list:
    trades = []
    prices = await get_klines(TRADE_SYMBOL)
    if not prices:
        logger.warning('Не удалось получить свечи Binance')
        return []
    rsi     = calc_rsi(prices)
    price   = await get_price(TRADE_SYMBOL)
    balance = await get_balance()
    btc_balance = balance.get('BTC', {}).get('balance', 0.0)
    logger.info(f'BTC: ${price:,.2f} | RSI: {rsi:.1f} | BTC баланс: {btc_balance:.6f}')
    if rsi < RSI_OVERSOLD and btc_balance < 0.0001:
        result = await place_order('BUY', TRADE_SYMBOL, TRADE_QTY)
        if 'orderId' in result:
            trades.append({'type': 'BUY', 'price': price, 'qty': TRADE_QTY,
                'rsi': rsi, 'order_id': str(result['orderId']),
                'time': datetime.now().strftime('%d.%m %H:%M')})
        else:
            logger.error(f'Ошибка покупки: {result}')
    elif rsi > RSI_OVERBOUGHT and btc_balance >= 0.001:
        qty = str(round(btc_balance, 3))
        result = await place_order('SELL', TRADE_SYMBOL, qty)
        if 'orderId' in result:
            trades.append({'type': 'SELL', 'price': price, 'qty': qty,
                'rsi': rsi, 'order_id': str(result['orderId']),
                'time': datetime.now().strftime('%d.%m %H:%M')})
        else:
            logger.error(f'Ошибка продажи: {result}')
    return trades


def format_bybit_trade(trade: dict) -> str:
    if trade['type'] == 'BUY':
        return (
            '*BINANCE TESTNET*\n'
            '*🟢 ПОКУПКА BTC*\n'
            f"Цена: `${trade['price']:,.2f}`\n"
            f"Куплено: `{trade['qty']} BTC`\n"
            f"RSI: `{trade['rsi']:.1f}` — перепродан\n"
            f"Order ID: `{trade['order_id']}`\n"
            f"Время: {trade['time']}"
        )
    return (
        '*BINANCE TESTNET*\n'
        '*🔴 ПРОДАЖА BTC*\n'
        f"Цена: `${trade['price']:,.2f}`\n"
        f"Продано: `{trade['qty']} BTC`\n"
        f"RSI: `{trade['rsi']:.1f}` — перекуплен\n"
        f"Order ID: `{trade['order_id']}`\n"
        f"Время: {trade['time']}"
    )


async def format_bybit_portfolio() -> str:
    balance = await get_balance()
    price   = await get_price(TRADE_SYMBOL)
    lines   = ['*BINANCE TESTNET — ДЕМО ПОРТФОЛИО*', '━━━━━━━━━━━━━━━━━━━━━━']
    if not balance:
        lines.append('❌ Баланс недоступен')
        lines.append(f'KEY задан: {"да" if BINANCE_API_KEY else "НЕТ"} | SECRET задан: {"да" if BINANCE_API_SECRET else "НЕТ"}')
        lines.append('Проверь Railway Variables: BINANCE\\_API\\_KEY и BINANCE\\_API\\_SECRET')
        return '\n'.join(lines)
    total = 0.0
    stablecoins = ('USDT', 'USDC', 'BUSD', 'DAI')
    for coin, d in balance.items():
        if d['usd'] > 0:
            usd = d['usd']
        elif coin in stablecoins:
            usd = d['balance']
        else:
            usd = 0.0
        total += usd
        lines.append(f"*{coin}*: `{d['balance']:.6f}` ≈ `${usd:,.2f}`")
    lines.append('━━━━━━━━━━━━━━━━━━━━━━')
    lines.append(f'Итого: `${total:,.2f}`')
    lines.append(f'BTC цена: `${price:,.2f}`')
    lines.append(f'Стратегия RSI: покупка <{RSI_OVERSOLD} / продажа >{RSI_OVERBOUGHT}')
    return '\n'.join(lines)
