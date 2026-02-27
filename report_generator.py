import logging
import aiohttp
from datetime import datetime
from config import (
    AI_PROVIDER, ANTHROPIC_API_KEY, OPENAI_API_KEY,
    TOP_COINS_COUNT, NEW_LISTINGS_COUNT,
    WHALE_MIN_USD
)

logger = logging.getLogger(__name__)


def fmt_price(n):
    if n is None: return "N/A"
    if n >= 1000: return f"{n:,.2f} $"
    elif n >= 1: return f"{n:.4f} $"
    else: return f"{n:.6f} $"

def fmt_large(n):
    if not n: return "N/A"
    if n >= 1_000_000_000_000: return f"{n/1_000_000_000_000:.2f} трлн $"
    elif n >= 1_000_000_000: return f"{n/1_000_000_000:.1f} млрд $"
    elif n >= 1_000_000: return f"{n/1_000_000:.1f} млн $"
    return f"{n:,.0f} $"

def pct_fmt(pct):
    if pct is None: return "`0.00%`"
    sign = "+" if pct >= 0 else ""
    emoji = "🟢" if pct >= 0 else "🔴"
    return f"`{sign}{pct:.2f}%` {emoji}"

def fear_label(v):
    if v >= 75: return "Жадность"
    elif v >= 55: return "Умеренная жадность"
    elif v >= 45: return "Нейтрально"
    elif v >= 25: return "Страх"
    else: return "Крайний страх"

def fear_emoji(v):
    if v >= 75: return "🤑"
    elif v >= 55: return "😊"
    elif v >= 45: return "😐"
    elif v >= 25: return "😰"
    else: return "😱"


class ReportGenerator:
    def __init__(self, fetcher):
        self.fetcher = fetcher

    async def get_eth_gas(self):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://api.etherscan.io/api",
                    params={"module": "gastracker", "action": "gasoracle"},
                    timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if data.get("status") == "1":
                        return data["result"]["SafeGasPrice"] + " Gwei"
        except Exception:
            pass
        return "N/A"

    async def get_ai_analysis(self, prompt):
        if AI_PROVIDER == "claude" and ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != "ВАШ_ANTHROPIC_KEY":
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=500,
                    messages=[{"role": "user", "content": prompt}]
                )
                return msg.content[0].text
            except Exception as e:
                logger.error(f"Claude ошибка: {e}")
        elif AI_PROVIDER == "openai" and OPENAI_API_KEY:
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=OPENAI_API_KEY)
                resp = await client.chat.completions.create(
                    model="gpt-4o-mini", max_tokens=500,
                    messages=[{"role": "user", "content": prompt}]
                )
                return resp.choices[0].message.content
            except Exception as e:
                logger.error(f"OpenAI ошибка: {e}")
        return ""

    # ──────────────────────────────────────────
    #  ЕЖЕДНЕВНЫЙ ОТЧЁТ
    # ──────────────────────────────────────────
    async def build_daily_report(self) -> str:
        logger.info("Загружаю данные...")

        market = await self.fetcher.get_market_overview()
        top_coins = await self.fetcher.get_top_coins(limit=TOP_COINS_COUNT)
        gainers_losers = await self.fetcher.get_top_gainers_losers(limit=5)
        fear_greed = await self.fetcher.get_fear_greed_index()
        new_listings = await self.fetcher.get_new_listings(limit=NEW_LISTINGS_COUNT)
        gas = await self.get_eth_gas()
        news = await self.fetcher.get_crypto_news(limit=5)
        whales = await self.fetcher.get_whale_transactions_free(WHALE_MIN_USD, limit=5)

        logger.info(f"Данные: монет={len(top_coins)}, новостей={len(news)}, китов={len(whales)}")

        now = datetime.now()
        date_str = now.strftime("%d %b %Y | %H:%M")

        btc = next((c for c in top_coins if c.get("symbol") == "btc"), {})
        eth = next((c for c in top_coins if c.get("symbol") == "eth"), {})

        lines = []
        lines.append("💎 *ОБЗОР КРИПТОРЫНКА* 💎")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        # BTC
        if btc:
            lines.append("📈 *БИТКОИН (BTC/USDT)*")
            lines.append(f"├ Цена: `{fmt_price(btc.get('current_price', 0))}`")
            lines.append(f"├ Изменение 24ч: {pct_fmt(btc.get('price_change_percentage_24h'))}")
            lines.append(f"└ Объем 24ч: `{fmt_large(btc.get('total_volume', 0))}`")
        else:
            lines.append("📈 *БИТКОИН* — данные недоступны")

        # ETH
        if eth:
            lines.append("🔹 *ЭФИРИУМ (ETH/USDT)*")
            lines.append(f"├ Цена: `{fmt_price(eth.get('current_price', 0))}`")
            lines.append(f"├ Изменение 24ч: {pct_fmt(eth.get('price_change_percentage_24h'))}")
            lines.append(f"└ Объем 24ч: `{fmt_large(eth.get('total_volume', 0))}`")
        else:
            lines.append("🔹 *ЭФИРИУМ* — данные недоступны")

        # Другие монеты
        others = [c for c in top_coins if c.get("symbol") not in ("btc", "eth")][:5]
        if others:
            lines.append("🔸 *ДРУГИЕ МОНЕТЫ*")
            for i, coin in enumerate(others):
                sym = coin.get("symbol", "").upper()
                price = coin.get("current_price", 0)
                pct = coin.get("price_change_percentage_24h") or 0
                prefix = "└" if i == len(others) - 1 else "├"
                lines.append(f"{prefix} *{sym}*: `{fmt_price(price)}` {pct_fmt(pct)}")

        # Рынок
        fv = fear_greed.get("value", 0) if fear_greed else 0
        lines.append("📊 *СОСТОЯНИЕ РЫНКА*")
        if market:
            lines.append(f"├ Капитализация: `{fmt_large(market.get('total_market_cap', 0))}`")
            lines.append(f"├ Доминация BTC: `{market.get('btc_dominance', 0):.1f}%`")
        if fear_greed:
            lines.append(f"├ Индекс страха: `{fv} ({fear_label(fv)})` {fear_emoji(fv)}")
        lines.append(f"└ Газ в сети: `{gas}`")

        # Гейнеры
        if gainers_losers.get("gainers"):
            lines.append("🚀 *ТОП РОСТА (24ч)*")
            for i, coin in enumerate(gainers_losers["gainers"][:5]):
                sym = coin.get("symbol", "").upper()
                pct = coin.get("price_change_percentage_24h") or 0
                prefix = "└" if i == 4 else "├"
                lines.append(f"{prefix} *{sym}*: `+{pct:.2f}%` 📈")

        # Луузеры
        if gainers_losers.get("losers"):
            lines.append("💥 *ТОП ПАДЕНИЯ (24ч)*")
            for i, coin in enumerate(gainers_losers["losers"][:5]):
                sym = coin.get("symbol", "").upper()
                pct = coin.get("price_change_percentage_24h") or 0
                prefix = "└" if i == 4 else "├"
                lines.append(f"{prefix} *{sym}*: `{pct:.2f}%` 📉")

        # Новые листинги
        if new_listings:
            lines.append("🆕 *НОВЫЕ ЛИСТИНГИ*")
            for i, coin in enumerate(new_listings):
                sym = coin.get("symbol", "").upper()
                name = coin.get("name", "")
                prefix = "└" if i == len(new_listings) - 1 else "├"
                lines.append(f"{prefix} *{sym}* — {name}")

        # 🐳 КИТЫ
        if whales:
            lines.append("🐳 *КРУПНЫЕ ПЕРЕВОДЫ КИТОВ*")
            for i, tx in enumerate(whales):
                sym = tx.get("symbol", "")
                usd = tx.get("amount_usd", 0)
                amount = tx.get("amount", 0)
                tx_type = tx.get("type", "перевод")
                prefix = "└" if i == len(whales) - 1 else "├"
                lines.append(f"{prefix} *{sym}* `{amount:,.1f} {sym}` ≈ `{fmt_large(usd)}` — {tx_type}")

        # 🗞 НОВОСТИ
        if news:
            lines.append("🗞 *НОВОСТИ ДНЯ*")
            for i, item in enumerate(news):
                title = item.get("title", "")
                url = item.get("url", "")
                source = item.get("source", "")
                coins = " ".join([f"#{c}" for c in item.get("currencies", []) if c])
                prefix = "└" if i == len(news) - 1 else "├"
                # Экранируем спецсимволы для Markdown
                title_safe = title.replace("*", "").replace("_", "").replace("`", "").replace("[", "").replace("]", "")[:60]
                if url:
                    lines.append(f"{prefix} [{title_safe}...]({url}) _{source}_ {coins}")
                else:
                    lines.append(f"{prefix} {title_safe}... _{source}_ {coins}")

        # AI прогноз
        ai_text = await self.get_ai_analysis(self._build_daily_ai_prompt(market, fear_greed, btc, eth, gainers_losers))
        if ai_text:
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("🤖 *ПРОГНОЗ И ЧТО ПОКУПАТЬ*")
            lines.append(ai_text)

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📅 _Обновлено: {date_str}_")
        lines.append("[🔗 Открыть на бирже](https://mexc.com)")
        return "\n".join(lines)

    def _build_daily_ai_prompt(self, market, fear_greed, btc, eth, gainers_losers):
        fv = fear_greed.get("value", 50) if fear_greed else 50
        btc_pct = btc.get("price_change_percentage_24h", 0) or 0
        eth_pct = eth.get("price_change_percentage_24h", 0) or 0
        btc_price = btc.get("current_price", 0)
        mkt_change = market.get("market_cap_change_24h", 0) if market else 0
        top_gainer = gainers_losers.get("gainers", [{}])[0].get("symbol", "").upper() if gainers_losers.get("gainers") else "N/A"
        return f"""Ты крипто-аналитик. 3-4 предложения на русском, без вводных фраз.
BTC: ${btc_price:,.0f} ({btc_pct:+.2f}%), ETH: {eth_pct:+.2f}%, рынок: {mkt_change:.2f}%, F&G: {fv}/100, топ гейнер: {top_gainer}
Формат: куда движется рынок + 1-2 монеты интересные для покупки и почему."""

    # ──────────────────────────────────────────
    #  ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ
    # ──────────────────────────────────────────
    async def build_weekly_report(self) -> str:
        import datetime as dt
        week_start = (datetime.now() - dt.timedelta(days=6)).strftime("%d.%m")
        week_end = datetime.now().strftime("%d.%m.%Y")
        now = datetime.now()

        market = await self.fetcher.get_market_overview()
        weekly_coins = await self.fetcher.get_weekly_top_coins()
        fear_greed = await self.fetcher.get_fear_greed_index()

        btc = next((c for c in weekly_coins if c.get("symbol") == "btc"), {})
        eth = next((c for c in weekly_coins if c.get("symbol") == "eth"), {})

        lines = []
        lines.append(f"📊 *НЕДЕЛЬНЫЙ ОТЧЁТ* 📊")
        lines.append(f"_Период: {week_start} — {week_end}_")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        if btc:
            lines.append("📈 *БИТКОИН (BTC) за неделю*")
            lines.append(f"├ Цена: `{fmt_price(btc.get('current_price', 0))}`")
            lines.append(f"└ Изменение 7д: {pct_fmt(btc.get('price_change_percentage_7d_in_currency'))}")

        if eth:
            lines.append("🔹 *ЭФИРИУМ (ETH) за неделю*")
            lines.append(f"├ Цена: `{fmt_price(eth.get('current_price', 0))}`")
            lines.append(f"└ Изменение 7д: {pct_fmt(eth.get('price_change_percentage_7d_in_currency'))}")

        fv = fear_greed.get("value", 0) if fear_greed else 0
        lines.append("📊 *СОСТОЯНИЕ РЫНКА*")
        if market:
            lines.append(f"├ Капитализация: `{fmt_large(market.get('total_market_cap', 0))}`")
            lines.append(f"├ Доминация BTC: `{market.get('btc_dominance', 0):.1f}%`")
        if fear_greed:
            lines.append(f"└ Индекс страха: `{fv} ({fear_label(fv)})` {fear_emoji(fv)}")

        sorted_coins = sorted(weekly_coins, key=lambda x: x.get("price_change_percentage_7d_in_currency") or 0, reverse=True)

        lines.append("🏆 *ЛУЧШИЕ ЗА НЕДЕЛЮ*")
        for i, coin in enumerate(sorted_coins[:5]):
            sym = coin.get("symbol", "").upper()
            pct = coin.get("price_change_percentage_7d_in_currency") or 0
            prefix = "└" if i == 4 else "├"
            lines.append(f"{prefix} *{sym}*: `+{pct:.2f}%` 🚀")

        lines.append("💔 *ХУДШИЕ ЗА НЕДЕЛЮ*")
        for i, coin in enumerate(sorted_coins[-5:][::-1]):
            sym = coin.get("symbol", "").upper()
            pct = coin.get("price_change_percentage_7d_in_currency") or 0
            prefix = "└" if i == 4 else "├"
            lines.append(f"{prefix} *{sym}*: `{pct:.2f}%` 💥")

        ai_text = await self.get_ai_analysis(self._build_weekly_ai_prompt(market, fear_greed, btc, eth, sorted_coins))
        if ai_text:
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("🤖 *ПРОГНОЗ НА СЛЕДУЮЩУЮ НЕДЕЛЮ*")
            lines.append(ai_text)

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📅 _Сформирован: {now.strftime('%d %b %Y | %H:%M')}_")
        lines.append("[🔗 Открыть на бирже](https://mexc.com)")
        return "\n".join(lines)

    def _build_weekly_ai_prompt(self, market, fear_greed, btc, eth, sorted_coins):
        btc_7d = btc.get("price_change_percentage_7d_in_currency", 0) or 0
        eth_7d = eth.get("price_change_percentage_7d_in_currency", 0) or 0
        fv = fear_greed.get("value", 50) if fear_greed else 50
        top3 = [c.get("symbol", "").upper() for c in sorted_coins[:3]]
        return f"""Ты крипто-аналитик. Прогноз на следующую неделю, 5-6 предложений на русском.
BTC: ${btc.get('current_price',0):,.0f} ({btc_7d:+.2f}% за 7д), ETH: {eth_7d:+.2f}%, BTC dom: {market.get('btc_dominance',0):.1f}%, F&G: {fv}/100, топ недели: {', '.join(top3)}
Укажи уровни BTC, тренд и 2-3 монеты для покупки. Без вводных слов."""
