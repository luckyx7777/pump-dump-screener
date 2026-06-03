from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal, Dict, Any


class OrderBookLevel(BaseModel):
    price: float
    qty: float


class OrderBookSnapshot(BaseModel):
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: datetime
    last_update_id: int | None = None


class FeatureVector(BaseModel):
    symbol: str
    timestamp: datetime

    # Core microstructure features from the paper
    wobi: float = Field(..., description="Weighted Order Book Imbalance [-1, 1]")
    cvd: float = Field(..., description="Cumulative Volume Delta (aggressive)")
    taker_aggression: float = Field(..., description="AR_H - Taker Aggression Ratio")
    leverage_velocity: float = Field(..., description="θ_LV - Leverage accumulation speed")
    iceberg_estimate: float = Field(0.0, description="Estimated hidden iceberg volume")
    spoof_score: float = Field(0.0, description="Ψ_spoof - Fake liquidity ratio")

    # Derived
    mid_price: float
    spread: float
    imbalance_5: float  # simple top-5 imbalance for quick view

    # MLOFI + Market Regime (из документа)
    mlofi: float = 0.0
    regime: int = 0
    regime_name: str = "LOW_VOL"

    metadata: Dict[str, Any] = Field(default_factory=dict)


class Signal(BaseModel):
    symbol: str
    timestamp: datetime
    direction: Literal["LONG", "SHORT", "NEUTRAL"]
    score: float = Field(..., ge=-1.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    triggered_metrics: list[str]
    explanation: str
    current_price: float


class AlertMessage(BaseModel):
    chat_id: int
    text: str
    parse_mode: str = "HTML"