"""
SQLAlchemy models для хранения сигналов и фич
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text, Index
from sqlalchemy.sql import func
from app.db.database import Base


class SignalRecord(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)          # LONG / SHORT / NEUTRAL
    score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    current_price = Column(Float)
    triggered_metrics = Column(JSON)                        # list of strings
    explanation = Column(Text)

    # Дополнительные метрики из FeatureVector (для аналитики)
    wobi = Column(Float)
    cvd = Column(Float)
    taker_aggression = Column(Float)
    leverage_velocity = Column(Float)
    iceberg_estimate = Column(Float)
    spoof_score = Column(Float)
    mid_price = Column(Float)
    spread = Column(Float)

    # Индексы для быстрых запросов
    __table_args__ = (
        Index("ix_signals_symbol_timestamp", "symbol", "timestamp"),
        Index("ix_signals_direction", "direction"),
    )

    def __repr__(self):
        return f"<SignalRecord {self.symbol} {self.direction} {self.score:.3f}>"