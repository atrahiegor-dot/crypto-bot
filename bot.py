import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.constants import ParseMode
from data_fetcher import CryptoDataFetcher
from report_generator import ReportGenerator
from price_alerts import check_price_alerts
from config import TELEGRAM_TOKEN, CHAT_ID, PRICE_ALERT_ENABLED

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
fetcher = CryptoDataFetcher()
generator = ReportGenerator(fetcher)


async def send_daily_report():
    logger.info("Генерирую ежедневный отчёт...")
    try:
        report = await generator.build_daily_report()
        await bot.send_message(chat_id=CHAT_ID, text=report, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        logger.info("Ежедневный отчёт отправлен")
    except Exception as e:
        logger.error(f"Ошибка отчёта: {e}")


async def send_weekly_report():
    logger.info("Генерирую еженедельный отчёт...")
    try:
        report = await generator.build_weekly_report()
        await bot.send_message(chat_id=CHAT_ID, text=report, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        logger.info("Еженедельный отчёт отправлен")
    except Exception as e:
        logger.error(f"Ошибка недельного отчёта: {e}")


async def main():
    logger.info("Крипто-бот запускается...")

    await bot.send_message(
        chat_id=CHAT_ID,
        text="🤖 *Крипто-бот запущен!*\n\n"
             "📅 Ежедневный отчёт: каждый день в 09:00\n"
             "📊 Еженедельный отчёт: каждое воскресенье в 10:00\n"
             "⚡ Алерты на движения цены: каждые 30 минут\n\n"
             "⏳ Первый отчёт придёт через ~40 секунд...",
        parse_mode=ParseMode.MARKDOWN
    )

    await asyncio.sleep(5)
    await send_daily_report()

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Ежедневный отчёт в 09:00
    scheduler.add_job(send_daily_report, "cron", hour=9, minute=0)

    # Еженедельный отчёт в воскресенье в 10:00
    scheduler.add_job(send_weekly_report, "cron", day_of_week="sun", hour=10, minute=0)

    # Алерты каждые 30 минут
    if PRICE_ALERT_ENABLED:
        scheduler.add_job(check_price_alerts, "interval", minutes=30)
        logger.info(f"Алерты включены — проверка каждые 30 минут")

    scheduler.start()
    logger.info("Бот работает!")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
        scheduler.shutdown()
        if fetcher.session and not fetcher.session.closed:
            await fetcher.session.close()


if __name__ == "__main__":
    asyncio.run(main())
