"""
Main entrypoint для Railway.
Полноценная интеграция WebSocket collectors (Binance + Bybit) + Feature Engine + Scorer + Telegram Bot.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn
import structlog
from app.config import settings
from app.bot.telegram_bot import start_bot, send_pump_dump_alert
from app.features.orderbook import OrderBook
from app.features.engine import FeatureEngine
from app.scorer.scorer import DynamicScorer
from app.collector.binance_collector import BinanceCollector
from app.collector.bybit_collector import BybitCollector
from app.models import FeatureVector, Signal
from app.db.database import init_db, close_db
from app.db.signals import save_signal

logger = structlog.get_logger()

app = FastAPI(title="Pump & Dump Screener", version="0.4.0")

# Глобальное состояние
orderbooks: dict[str, OrderBook] = {}
engines: dict[str, FeatureEngine] = {}
scorer = DynamicScorer()

binance_collector: BinanceCollector | None = None
bybit_collector: BybitCollector | None = None


# Простой cooldown чтобы не спамить один и тот же сигнал
_last_alert_time: dict[str, float] = {}
ALERT_COOLDOWN_SECONDS = 180  # 3 минуты между алертами по одной паре


async def on_new_feature(symbol: str, features: FeatureVector):
    """Callback: FeatureEngine → Scorer → Save to DB → Telegram Alert"""
    signal: Signal = scorer.score(features)

    if signal.direction == "NEUTRAL":
        return

    now = asyncio.get_event_loop().time()
    last_time = _last_alert_time.get(symbol, 0)

    if now - last_time < ALERT_COOLDOWN_SECONDS:
        return

    _last_alert_time[symbol] = now

    logger.info(
        "🚨 Signal generated",
        symbol=symbol,
        direction=signal.direction,
        score=signal.score
    )

    # 1. Сохраняем в PostgreSQL
    await save_signal(signal, features)

    # 2. Отправляем алерт в Telegram
    await send_pump_dump_alert(signal, features)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global binance_collector, bybit_collector

    logger.info("🚀 Starting Pump & Dump Screener v0.2")

    # Инициализация
    for symbol in settings.symbols:
        orderbooks[symbol] = OrderBook(symbol)
        engines[symbol] = FeatureEngine(symbol)

    # Telegram бот
    asyncio.create_task(start_bot())

    # Инициализация базы данных
    await init_db()

    # === ЗАПУСК COLLECTORS ===
    binance_collector = BinanceCollector(
        symbols=settings.symbols,
        orderbooks=orderbooks,
        engines=engines,
        on_feature=on_new_feature
    )

    bybit_collector = BybitCollector(
        symbols=settings.symbols,
        orderbooks=orderbooks,
        engines=engines,
        on_feature=on_new_feature
    )

    asyncio.create_task(binance_collector.start())
    asyncio.create_task(bybit_collector.start())

    logger.info("All collectors started", symbols=settings.symbols)

    yield

    # Shutdown
    logger.info("Shutting down...")
    if binance_collector:
        await binance_collector.stop()
    if bybit_collector:
        await bybit_collector.stop()
    await close_db()


app.router.lifespan_context = lifespan


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "symbols": len(settings.symbols),
        "binance_connected": binance_collector.running if binance_collector else False,
        "bybit_connected": bybit_collector.running if bybit_collector else False,
    }


@app.get("/features/{symbol}")
async def get_features(symbol: str):
    engine = engines.get(symbol.upper())
    if not engine:
        return {"error": "Symbol not monitored"}
    return {"message": "Live features available via WebSocket collectors"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)