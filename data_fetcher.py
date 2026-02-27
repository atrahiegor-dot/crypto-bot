import aiohttp
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FEAR_GREED_API = "https://api.alternative.me/fng/"
CRYPTOPANIC_BASE = "https://cryptopanic.com/api/v1/posts/"
WHALE_ALERT_BASE = "https://api.whale-alert.io/v1/transactions"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


class CryptoDataFetcher:
    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=HEADERS)
        return self.session

    async def fetch(self, url: str, params: dict = None, retries: int = 3) -> dict:
        session = await self._get_session()
        for attempt in range(retries):
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        wait = 15 * (attempt + 1)
                        logger.warning(f"Rate limit (429), жду {wait}с...")
                        await asyncio.sleep(wait)
                    elif resp.status == 403:
                        logger.warning("Доступ запрещён (403), жду 20с...")
                        await asyncio.sleep(20)
                    else:
                        logger.warning(f"Статус {resp.status} для {url}")
                        await asyncio.sleep(5)
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут попытка {attempt+1}/{retries}")
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Ошибка попытка {attempt+1}/{retries}: {e}")
                await asyncio.sleep(5)
        return {}

    async def get_market_overview(self) -> dict:
        data = await self.fetch(f"{COINGECKO_BASE}/global")
        if not data:
            return {}
        gdata = data.get("data", {})
        return {
            "total_market_cap": gdata.get("total_market_cap", {}).get("usd", 0),
            "total_volume_24h": gdata.get("total_volume", {}).get("usd", 0),
            "btc_dominance": gdata.get("market_cap_percentage", {}).get("btc", 0),
            "eth_dominance": gdata.get("market_cap_percentage", {}).get("eth", 0),
            "market_cap_change_24h": gdata.get("market_cap_change_percentage_24h_usd", 0),
        }

    async def get_top_coins(self, limit: int = 10) -> list:
        await asyncio.sleep(3)
        data = await self.fetch(
            f"{COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h,7d",
                "locale": "en"
            }
        )
        if isinstance(data, list) and len(data) > 0:
            logger.info(f"Загружено {len(data)} монет")
            return data
        logger.warning("Монеты не загрузились, пробую запасной метод...")
        return await self._get_top_coins_fallback()

    async def _get_top_coins_fallback(self) -> list:
        await asyncio.sleep(5)
        symbols = ["bitcoin", "ethereum", "tether", "binancecoin", "solana",
                   "ripple", "usd-coin", "cardano", "avalanche-2", "dogecoin"]
        results = []
        for sym in symbols[:5]:
            await asyncio.sleep(2)
            data = await self.fetch(
                f"{COINGECKO_BASE}/coins/{sym}",
                params={"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "false"}
            )
            if data and "market_data" in data:
                md = data["market_data"]
                results.append({
                    "id": sym,
                    "symbol": data.get("symbol", ""),
                    "name": data.get("name", ""),
                    "current_price": md.get("current_price", {}).get("usd", 0),
                    "market_cap": md.get("market_cap", {}).get("usd", 0),
                    "total_volume": md.get("total_volume", {}).get("usd", 0),
                    "price_change_percentage_24h": md.get("price_change_percentage_24h", 0),
                })
        return results

    async def get_top_gainers_losers(self, limit: int = 5) -> dict:
        await asyncio.sleep(5)
        data = await self.fetch(
            f"{COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "sparkline": "false",
                "locale": "en"
            }
        )
        if not isinstance(data, list) or len(data) == 0:
            return {"gainers": [], "losers": []}
        filtered = [c for c in data if c.get("total_volume", 0) > 1_000_000 and c.get("price_change_percentage_24h") is not None]
        sorted_by_change = sorted(filtered, key=lambda x: x.get("price_change_percentage_24h") or 0, reverse=True)
        return {
            "gainers": sorted_by_change[:limit],
            "losers": sorted_by_change[-limit:][::-1]
        }

    async def get_new_listings(self, limit: int = 5) -> list:
        await asyncio.sleep(5)
        data = await self.fetch(f"{COINGECKO_BASE}/coins/list/new")
        if not isinstance(data, list):
            return []
        return data[:limit]

    async def get_fear_greed_index(self) -> dict:
        await asyncio.sleep(2)
        data = await self.fetch(FEAR_GREED_API, params={"limit": 8})
        if not data or "data" not in data:
            return {}
        latest = data["data"][0]
        week_ago = data["data"][-1] if len(data["data"]) >= 7 else None
        return {
            "value": int(latest.get("value", 0)),
            "classification": latest.get("value_classification", ""),
            "week_ago_value": int(week_ago.get("value", 0)) if week_ago else None,
            "week_ago_class": week_ago.get("value_classification", "") if week_ago else None,
            "history": [{"value": int(d["value"]), "class": d["value_classification"]} for d in data["data"]]
        }

    async def get_weekly_top_coins(self) -> list:
        await asyncio.sleep(2)
        data = await self.fetch(
            f"{COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 20,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "7d",
                "locale": "en"
            }
        )
        return data if isinstance(data, list) else []

    # ──────────────────────────────────────────
    #  НОВОСТИ (CryptoPanic — бесплатно без ключа)
    # ──────────────────────────────────────────
    async def get_crypto_news(self, limit: int = 5) -> list:
        """Топ крипто-новостей дня"""
        await asyncio.sleep(2)
        data = await self.fetch(
            CRYPTOPANIC_BASE,
            params={
                "public": "true",
                "kind": "news",
                "filter": "important",
                "regions": "en",
            }
        )
        results = data.get("results", [])
        news = []
        for item in results[:limit]:
            news.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": item.get("source", {}).get("title", ""),
                "currencies": [c.get("code", "") for c in item.get("currencies", [])[:3]],
            })
        return news

    # ──────────────────────────────────────────
    #  КИТЫ (Whale Alert API — бесплатный ключ)
    # ──────────────────────────────────────────
    async def get_whale_transactions(self, api_key: str, min_usd: int = 1_000_000, limit: int = 5) -> list:
        """Крупные переводы за последние 3 часа"""
        if not api_key or api_key == "ВАШ_WHALE_ALERT_KEY":
            return await self._get_whale_fallback(min_usd, limit)

        import time
        since = int(time.time()) - 10800  # 3 часа назад
        data = await self.fetch(
            WHALE_ALERT_BASE,
            params={
                "api_key": api_key,
                "min_value": min_usd,
                "start": since,
                "limit": limit,
                "cursor": 0
            }
        )
        transactions = data.get("transactions", [])
        result = []
        for tx in transactions[:limit]:
            amount = tx.get("amount", 0)
            amount_usd = tx.get("amount_usd", 0)
            symbol = tx.get("symbol", "").upper()
            from_owner = tx.get("from", {}).get("owner_type", "unknown")
            to_owner = tx.get("to", {}).get("owner_type", "unknown")
            from_name = tx.get("from", {}).get("owner", from_owner)
            to_name = tx.get("to", {}).get("owner", to_owner)
            result.append({
                "symbol": symbol,
                "amount": amount,
                "amount_usd": amount_usd,
                "from": from_name,
                "to": to_name,
            })
        return result

    async def _get_whale_fallback(self, min_usd: int, limit: int) -> list:
        """Резервный источник китов через Etherscan крупные транзакции"""
        # Без ключа возвращаем заглушку с подсказкой
        return []

    async def get_whale_transactions_free(self, min_usd: float = 1_000_000, limit: int = 5) -> list:
        """Крупные переводы BTC и ETH без API ключа"""
        from whale_tracker import get_all_whales
        return await get_all_whales(min_usd, limit)
