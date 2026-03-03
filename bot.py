import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from data_fetcher import CryptoDataFetcher
from report_generator import ReportGenerator
from price_alerts import check_price_alerts
from bybit_trader import run_bybit_trading_cycle, format_bybit_trade, format_bybit_portfolio
from config import TELEGRAM_TOKEN, CHAT_ID, PRICE_ALERT_ENABLED

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

fetcher = CryptoDataFetcher()
generator = ReportGenerator(fetcher)
app = Application.builder().token(TELEGRAM_TOKEN).build()


async def send_msg(text):
    await app.bot.send_message(chat_id=CHAT_ID, text=text,
        parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def send_daily_report():
    logger.info("Генерирую ежедневный отчёт...")
    try:
        report = await generator.build_daily_report()
        await send_msg(report)
    except Exception as e:
        logger.error(f"Ошибка отчёта: {e}")


async def send_weekly_report():
    try:
        report = await generator.build_weekly_report()
        await send_msg(report)
    except Exception as e:
        logger.error(f"Ошибка недельного: {e}")


async def run_auto_trader():
    logger.info("Запускаю Bybit трейдер...")
    try:
        trades = await run_bybit_trading_cycle()
        for trade in trades:
            msg = format_bybit_trade(trade)
            await send_msg(msg)
            await asyncio.sleep(1)
        if not trades:
            logger.info("Сигналов нет")
    except Exception as e:
        logger.error(f"Ошибка трейдера: {e}")


async def send_daily_portfolio():
    try:
        msg = await format_bybit_portfolio()
        await send_msg(msg)
    except Exception as e:
        logger.error(f"Ошибка портфолио: {e}")


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(CHAT_ID):
        return
    msg = await format_bybit_portfolio()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(CHAT_ID):
        return
    await update.message.reply_text("Генерирую отчёт, подожди ~30 секунд...")
    report = await generator.build_daily_report()
    await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(CHAT_ID):
        return
    text = "Команды: /report - отчёт рынка, /portfolio - портфолио Bybit Testnet"
    await update.message.reply_text(text)


async def main():
    logger.info("Запуск бота...")
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("report", cmd_report))
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    hello = ("*Крипто-бот запущен!*\n\n"
             "Отчёт рынка: каждый день в 09:00\n"
             "Bybit трейдер: каждые 2 часа\n"
             "Итоги торговли: каждый день в 20:00\n"
             "Алерты: каждые 30 минут\n\n"
             "Команды: /report /portfolio")
    await app.bot.send_message(chat_id=CHAT_ID, text=hello, parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(5)
    await send_daily_report()
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_daily_report, "cron", hour=9, minute=0)
    scheduler.add_job(send_weekly_report, "cron", day_of_week="sun", hour=10, minute=0)
    scheduler.add_job(send_daily_portfolio, "cron", hour=20, minute=0)
    scheduler.add_job(run_auto_trader, "interval", hours=2)
    if PRICE_ALERT_ENABLED:
        scheduler.add_job(check_price_alerts, "interval", minutes=30)
    scheduler.start()
    logger.info("Бот работает!")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())