"""
Telegram Bot для скринера пампов/дампов.
Реальная отправка алертов + команды.
"""
from app.config import settings
from app.models import Signal, FeatureVector
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
import structlog

logger = structlog.get_logger()

bot = Bot(
    token=settings.telegram_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

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
    await message.answer(
        f"📊 <b>{symbol}</b>\n\n"
        "Live-данные пока в разработке."
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    text = "📈 <b>Статус мониторинга</b>\n\n"
    for sym in settings.symbols:
        text += f"• <b>{sym}</b> — в работе\n"
    await message.answer(text)


@dp.message(Command("symbols"))
async def cmd_symbols(message: Message):
    symbols_text = "\n".join(f"• <code>{s}</code>" for s in settings.symbols)
    await message.answer(f"📋 <b>Мониторимые пары:</b>\n{symbols_text}")


# ====================== ОТПРАВКА АЛЕРТОВ ======================

def _format_signal_alert(signal: Signal, features: FeatureVector | None = None) -> str:
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

    if features:
        text += "<b>Микроструктура:</b>\n"
        text += f"• WOBI: <code>{features.wobi:+.3f}</code>\n"
        text += f"• MLOFI: <code>{features.mlofi:+.2f}</code>\n"
        text += f"• CVD: <code>{features.cvd:+.2f}</code>\n"
        text += f"• Taker Aggression: <code>{features.taker_aggression:+.3f}</code>\n"
        text += f"• Leverage Velocity: <code>{features.leverage_velocity:.2f}</code>\n"
        if features.iceberg_estimate > 10:
            text += f"• Iceberg: <code>{features.iceberg_estimate:.1f}</code>\n"
        if features.spoof_score > 5:
            text += f"• Spoof Score: <code>{features.spoof_score:.1f}</code>\n"
        text += "\n"

    if signal.triggered_metrics:
        text += "<b>Триггеры:</b>\n" + "\n".join(f"• <code>{m}</code>" for m in signal.triggered_metrics) + "\n\n"

    if signal.explanation:
        text += f"<b>Объяснение:</b>\n{signal.explanation}\n\n"

    text += "<i>Методология: WOBI + MLOFI + CVD + Leverage Velocity + гейты</i>"
    return text


async def send_pump_dump_alert(signal: Signal, features: FeatureVector | None = None):
    if not settings.telegram_alert_chat_id:
        logger.warning("TELEGRAM_ALERT_CHAT_ID не задан", symbol=signal.symbol)
        return

    try:
        await bot.send_message(
            chat_id=settings.telegram_alert_chat_id,
            text=_format_signal_alert(signal, features),
            disable_web_page_preview=True
        )
        logger.info("Alert sent", symbol=signal.symbol, direction=signal.direction)
    except Exception as e:
        logger.error("Failed to send alert", error=str(e), symbol=signal.symbol)


async def start_bot():
    logger.info("Starting Telegram bot...")
    await dp.start_polling(bot)
