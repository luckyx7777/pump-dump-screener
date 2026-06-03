"""
Сервис для сохранения сигналов в БД
"""

from sqlalchemy import insert
from app.db.database import AsyncSessionLocal
from app.db.models import SignalRecord
from app.models import Signal, FeatureVector
import structlog

logger = structlog.get_logger()


async def save_signal(signal: Signal, features: FeatureVector | None = None):
    """
    Сохраняет сигнал в PostgreSQL.
    Если передан features — сохраняет также ключевые метрики.
    """
    async with AsyncSessionLocal() as session:
        try:
            record = SignalRecord(
                symbol=signal.symbol,
                direction=signal.direction,
                score=signal.score,
                confidence=signal.confidence,
                current_price=signal.current_price,
                triggered_metrics=signal.triggered_metrics,
                explanation=signal.explanation,
            )

            # Добавляем метрики из features, если есть
            if features:
                record.wobi = features.wobi
                record.cvd = features.cvd
                record.taker_aggression = features.taker_aggression
                record.leverage_velocity = features.leverage_velocity
                record.iceberg_estimate = features.iceberg_estimate
                record.spoof_score = features.spoof_score
                record.mid_price = features.mid_price
                record.spread = features.spread

            session.add(record)
            await session.commit()
            logger.info("Signal saved to database", symbol=signal.symbol, direction=signal.direction, id=record.id)

        except Exception as e:
            await session.rollback()
            logger.error("Failed to save signal to DB", error=str(e), symbol=signal.symbol)