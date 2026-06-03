"""
Telegram Bot для скринера пампов/дампов.
Реальная отправка алертов + команды.
"""

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from datetime import datetime
from app.config import settings
from app.models import Signal
import structlog

logger = structlog.get_logger()

bot = Bot(token=settings.telegram_bot_token, parse_mode=ParseMode.HTML)
dp = Dispatcher()


# ====================== КОМАНДЫ ======================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = (
        "🚀 <b>Pump & Dump Screener Bot</b>\n\n"
        "Я мониторю микроструктуру Binance и Bybit в реальном времени.\n\n"
        "<b>Команды:</b>\n"
        "/screen &lt;SYMBOL&gt; — текущий сигнал по паре\n"
        "/status — статус всех отслеживаемых пар\n"
        "/symbols — список мониторимых символов"
    )
    await message.answer(text)


@dp.message(Command("screen"))
async def cmd_screen(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: <code>/screen BTCUSDT</code>")
        return

    symbol = args[1].upper()
    # В будущем здесь будет запрос к Redis / БД за актуальными фичами
    await message.answer(
        f"📊 <b>{symbol}</b>\n\n"
        "Актуальные данные пока в разработке.\n"
        "Скоро здесь будет live-скоринг из Redis."
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    text = "📈 <b>Статус мониторинга</b>\n\n"
    for sym in settings.symbols:
        text += f"• <b>{sym}</b> — в работе\n"
    text += f"\nВсего пар: <b>{len(settings.symbols)}</b>"
    await message.answer(text)


@dp.message(Command("symbols"))
async def cmd_symbols(message: Message):
    symbols_text = "\n".join(f"• <code>{s}</code>" for s in settings.symbols)
    await message.answer(f"📋 <b>Мониторимые пары:</b>\n{symbols_text}")


# ====================== ОТПРАВКА АЛЕРТОВ ======================

def _format_signal_alert(signal: Signal, features: FeatureVector | None = None) -> str:
    """Красивое форматирование алерта с реальными значениями метрик из документа."""

    emoji = "🟢" if signal.direction == "LONG" else "🔴" if signal.direction == "SHORT" else "⚪"
    direction_text = {
        "LONG": "PRE-PUMP (лонг)",
        "SHORT": "PRE-DUMP (шорт)",
        "NEUTRAL": "Нейтрально"
    }.get(signal.direction, signal.direction)

    text = (
        f"{emoji} <b>{signal.direction} — {direction_text}</b>\n"
        f"<b>{signal.symbol}</b> @ <code>{signal.current_price:.2f}</code>\n\n"
        f"Score: <b>{signal.score:.3f}</b>   |   Уверенность: <b>{signal.confidence:.0%}</b>\n"
        f"Время: <code>{signal.timestamp.strftime('%H:%M:%S')}</code>\n\n"
    )

    # === Реальные значения ключевых метрик ===
    if features:
        text += "<b>Микроструктура (текущие значения):</b>\n"
        text += f"• WOBI: <code>{features.wobi:+.3f}</code>\n"
        text += f"• CVD: <code>{features.cvd:+.2f}</code>\n"
        text += f"• Taker Aggression: <code>{features.taker_aggression:+.3f}</code>\n"
        text += f"• Leverage Velocity (θ_LV): <code>{features.leverage_velocity:.2f}</code>\n"
        if features.spread:
            text += f"• Spread: <code>{features.spread:.4f}</code>\n"
        text += "\n"

    if signal.triggered_metrics:
        text += "<b>Активированные триггеры / гейты:</b>\n"
        for metric in signal.triggered_metrics:
            text += f"• <code>{metric}</code>\n"
        text += "\n"

    if signal.explanation:
        text += f"<b>Объяснение:</b>\n{signal.explanation}\n\n"

    text += (
        "<i>Методология: Weighted OBI + Multi-Level OFI + CVD + Leverage Velocity + гейты</i>"
    )

    return text


async def send_pump_dump_alert(signal: Signal, features: FeatureVector | None = None):
    """
    Реальная отправка алерта в Telegram с метриками.
    """
    if not settings.telegram_alert_chat_id:
        logger.warning("TELEGRAM_ALERT_CHAT_ID не задан — алерт не отправлен", symbol=signal.symbol)
        return

    try:
        alert_text = _format_signal_alert(signal, features)
        await bot.send_message(
            chat_id=settings.telegram_alert_chat_id,
            text=alert_text,
            disable_web_page_preview=True
        )
        logger.info("Alert sent to Telegram", symbol=signal.symbol, direction=signal.direction)
    except Exception as e:
        logger.error("Failed to send Telegram alert", error=str(e), symbol=signal.symbol)


# ====================== ЗАПУСК БОТА ======================

async def start_bot():
    """Запуск polling бота (вызывается из main.py)"""
    logger.info("Starting Telegram bot polling...")
    await dp.start_polling(bot)