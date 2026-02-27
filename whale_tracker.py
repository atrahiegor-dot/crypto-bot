import aiohttp
import asyncio
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def fmt_large(n: float) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} млрд $"
    elif n >= 1_000_000:
        return f"{n / 1_000_000:.1f} млн $"
    elif n >= 1_000:
        return f"{n / 1_000:.1f} тыс $"
    return f"{n:,.0f} $"


def fmt_btc(satoshi: int) -> str:
    btc = satoshi / 1e8
    return f"{btc:,.2f} BTC"


async def get_btc_whales(min_usd: float = 1_000_000, limit: int = 4) -> list:
    """Крупные BTC транзакции через Blockchain.info"""
    results = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # Получаем последние неподтверждённые транзакции
            async with session.get(
                "https://blockchain.info/unconfirmed-transactions?format=json&limit=100",
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            # Текущая цена BTC
            async with session.get(
                "https://blockchain.info/ticker",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp2:
                ticker = await resp2.json() if resp2.status == 200 else {}

            btc_price = ticker.get("USD", {}).get("last", 65000)

            txs = data.get("txs", [])
            for tx in txs:
                # Считаем общую сумму выходов
                total_out = sum(o.get("value", 0) for o in tx.get("out", []))
                total_btc = total_out / 1e8
                total_usd = total_btc * btc_price

                if total_usd >= min_usd:
                    # Определяем тип транзакции
                    inputs_count = len(tx.get("inputs", []))
                    outputs_count = len(tx.get("out", []))

                    if outputs_count == 1:
                        tx_type = "консолидация"
                    elif inputs_count == 1 and outputs_count == 2:
                        tx_type = "перевод"
                    else:
                        tx_type = "перевод"

                    results.append({
                        "symbol": "BTC",
                        "amount": total_btc,
                        "amount_usd": total_usd,
                        "type": tx_type,
                        "hash": tx.get("hash", "")[:12] + "..."
                    })

                    if len(results) >= limit:
                        break

    except Exception as e:
        logger.error(f"Ошибка получения BTC китов: {e}")

    return results


async def get_eth_whales(min_usd: float = 1_000_000, limit: int = 4) -> list:
    """Крупные ETH транзакции через Etherscan (без ключа — публичный эндпоинт)"""
    results = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # Получаем последние блоки
            async with session.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "proxy",
                    "action": "eth_blockNumber",
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                block_data = await resp.json() if resp.status == 200 else {}

            latest_block_hex = block_data.get("result", "0x0")
            latest_block = int(latest_block_hex, 16)

            # Текущая цена ETH
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "ethereum", "vs_currencies": "usd"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp3:
                price_data = await resp3.json() if resp3.status == 200 else {}
            eth_price = price_data.get("ethereum", {}).get("usd", 3000)

            # Берём транзакции из последних блоков
            for block_offset in range(3):
                block_num = latest_block - block_offset
                async with session.get(
                    "https://api.etherscan.io/api",
                    params={
                        "module": "proxy",
                        "action": "eth_getBlockByNumber",
                        "tag": hex(block_num),
                        "boolean": "true",
                    },
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp4:
                    if resp4.status != 200:
                        continue
                    block_info = await resp4.json()

                txs = block_info.get("result", {}).get("transactions", [])
                for tx in txs:
                    value_wei = int(tx.get("value", "0x0"), 16)
                    value_eth = value_wei / 1e18
                    value_usd = value_eth * eth_price

                    if value_usd >= min_usd:
                        results.append({
                            "symbol": "ETH",
                            "amount": value_eth,
                            "amount_usd": value_usd,
                            "type": "перевод",
                            "hash": tx.get("hash", "")[:12] + "..."
                        })
                        if len(results) >= limit:
                            break

                if len(results) >= limit:
                    break

                await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Ошибка получения ETH китов: {e}")

    return results


async def get_all_whales(min_usd: float = 1_000_000, limit: int = 5) -> list:
    """Объединяет BTC и ETH крупные транзакции"""
    btc_whales, eth_whales = await asyncio.gather(
        get_btc_whales(min_usd, limit=3),
        get_eth_whales(min_usd, limit=3),
    )

    all_whales = btc_whales + eth_whales
    # Сортируем по сумме
    all_whales.sort(key=lambda x: x.get("amount_usd", 0), reverse=True)
    return all_whales[:limit]
