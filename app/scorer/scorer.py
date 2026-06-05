"""
Multi-factor Scoring Engine with stricter multi-confirmation logic.
Signals now require alignment of multiple factors for higher quality and fewer false positives.
"""

import numpy as np
from collections import deque
from datetime import datetime
from typing import Dict, List
from app.models import FeatureVector, Signal
from app.config import settings


class DynamicScorer:
    def __init__(self):
        self.feature_history: Dict[str, deque] = {}

    def _get_or_create_buffer(self, symbol: str) -> deque:
        if symbol not in self.feature_history:
            self.feature_history[symbol] = deque(maxlen=2000)
        return self.feature_history[symbol]

    def _calculate_zscore(self, values: list[float], current: float) -> float:
        if len(values) < 30:
            return 0.0
        arr = np.array(values)
        mean = np.mean(arr)
        std = np.std(arr) or 1.0
        return (current - mean) / std

    def _get_regime_weights(self, regime: int) -> dict:
        if regime == 0:
            return {"wobi": 0.45, "taker": 0.25, "cvd": 0.15, "lev": 0.15}
        elif regime == 1:
            return {"wobi": 0.30, "taker": 0.25, "cvd": 0.25, "lev": 0.20}
        else:
            return {"wobi": 0.20, "taker": 0.30, "cvd": 0.25, "lev": 0.25}

    def score(self, features: FeatureVector) -> Signal:
        buf = self._get_or_create_buffer(features.symbol)
        buf.append(features)

        wobi_history = [f.wobi for f in buf]
        cvd_history = [f.cvd for f in buf]
        taker_history = [f.taker_aggression for f in buf]
        lev_history = [f.leverage_velocity for f in buf]

        z_wobi = self._calculate_zscore(wobi_history, features.wobi)
        z_cvd = self._calculate_zscore(cvd_history, features.cvd)
        z_taker = self._calculate_zscore(taker_history, features.taker_aggression)
        z_lev = self._calculate_zscore(lev_history, features.leverage_velocity)

        regime_weights = self._get_regime_weights(features.regime)

        raw_score = (
            regime_weights["wobi"] * z_wobi +
            regime_weights["taker"] * z_taker +
            regime_weights["cvd"] * z_cvd +
            regime_weights["lev"] * z_lev
        )

        score = np.tanh(raw_score * 1.5)

        triggered = []
        blocked = False

        if z_wobi > 1.5 and z_cvd < -0.8:
            blocked = True
            triggered.append("CVD_OBI_DIVERGENCE")

        if features.spoof_score > settings.spoof_threshold:
            blocked = True
            triggered.append("SPOOFING_DETECTED")

        if features.leverage_velocity > 2.5 and abs(features.taker_aggression) < 0.3:
            blocked = True
            triggered.append("LEVERAGE_WITHOUT_SPOT_SUPPORT")

        if features.regime_name == "HIGH_VOL" and features.leverage_velocity > 1.8:
            blocked = True
            triggered.append("HIGH_VOL_REGIME")

        direction = "NEUTRAL"

        if not blocked:
            # СТРОГИЙ ТРИГГЕР: требуем подтверждения минимум от одного сильного фактора в правильном направлении
            strong_positive = (z_wobi > 0.9) or (z_taker > 0.9) or (z_cvd > 0.8)
            strong_negative = (z_wobi < -0.9) or (z_taker < -0.9) or (z_cvd < -0.8)

            if score > settings.pump_threshold and strong_positive:
                direction = "LONG"
                triggered.append("PRE_PUMP")
            elif score < settings.dump_threshold and strong_negative:
                direction = "SHORT"
                triggered.append("PRE_DUMP")

        explanation = self._generate_explanation(features, z_wobi, z_taker, z_cvd, z_lev, triggered, features.regime_name)

        return Signal(
            symbol=features.symbol,
            timestamp=features.timestamp,
            direction=direction,
            score=round(float(score), 4),
            confidence=min(abs(float(score)), 1.0),
            triggered_metrics=triggered,
            explanation=explanation,
            current_price=features.mid_price
        )

    def _generate_explanation(self, f: FeatureVector, z_wobi, z_taker, z_cvd, z_lev, triggered, regime_name: str) -> str:
        parts = []

        if abs(z_wobi) > 0.8:
            direction = "покупателей" if z_wobi > 0 else "продавцов"
            parts.append(f"Сильный дисбаланс в стакане в пользу {direction} (WOBI z={z_wobi:.2f})")

        if abs(z_taker) > 0.8:
            direction = "агрессивных покупок" if z_taker > 0 else "агрессивных продаж"
            parts.append(f"Доминирование {direction} (Taker z={z_taker:.2f})")

        if abs(z_cvd) > 0.7:
            direction = "накопления" if z_cvd > 0 else "распределения"
            parts.append(f"Значительный CVD ({direction}, z={z_cvd:.2f})")

        if z_lev > 1.2:
            parts.append(f"Активный набор плеча (θ_LV z={z_lev:.2f})")

        if regime_name == "HIGH_VOL":
            parts.append("⚠️ HIGH_VOL режим — сигналы фильтруются")

        for t in triggered:
            if t == "CVD_OBI_DIVERGENCE":
                parts.append("⚠️ Дивергенция CVD/OBI — возможен ложный сигнал")
            elif t == "SPOOFING_DETECTED":
                parts.append("🚫 Обнаружен спуфинг")
            elif t == "HIGH_VOL_REGIME":
                parts.append("🚨 Блокировка в HIGH_VOL режиме")

        if not parts:
            return "Нейтральная микроструктура (недостаточно подтверждений для сигнала)"

        return " | ".join(parts)
