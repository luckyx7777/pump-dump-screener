"""
Multi-factor Scoring Engine with Z-score normalization, logical gating and regime-aware weighting.
Fully aligned with the pump-dump methodology document.
"""

import numpy as np
from collections import deque
from datetime import datetime
from typing import Dict, List
from app.models import FeatureVector, Signal
from app.config import settings


class DynamicScorer:
    def __init__(self):
        self.feature_history: Dict[str, deque] = {}  # symbol -> deque of recent features

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
        """Dynamic weights based on regime (LOW_VOL=0, TRENDING=1, HIGH_VOL=2)"""
        if regime == 0:  # LOW_VOL
            return {"wobi": 0.45, "taker": 0.25, "cvd": 0.15, "lev": 0.15}
        elif regime == 1:  # TRENDING
            return {"wobi": 0.30, "taker": 0.25, "cvd": 0.25, "lev": 0.20}
        else:  # HIGH_VOL - more conservative on wobi, higher on filters
            return {"wobi": 0.20, "taker": 0.30, "cvd": 0.25, "lev": 0.25}

    def score(self, features: FeatureVector) -> Signal:
        """
        Итоговый скоринг S(t) ∈ [-1, 1]
        + динамические веса по режиму + гейты из документа
        """
        buf = self._get_or_create_buffer(features.symbol)
        buf.append(features)

        # Z-score на основе истории
        wobi_history = [f.wobi for f in buf]
        cvd_history = [f.cvd for f in buf]
        taker_history = [f.taker_aggression for f in buf]
        lev_history = [f.leverage_velocity for f in buf]

        z_wobi = self._calculate_zscore(wobi_history, features.wobi)
        z_cvd = self._calculate_zscore(cvd_history, features.cvd)
        z_taker = self._calculate_zscore(taker_history, features.taker_aggression)
        z_lev = self._calculate_zscore(lev_history, features.leverage_velocity)

        # === ДИНАМИЧЕСКИЕ ВЕСА ПО РЕЖИМУ (Priority 2) ===
        regime_weights = self._get_regime_weights(features.regime)
        raw_score = (
            regime_weights["wobi"] * z_wobi +
            regime_weights["taker"] * z_taker +
            regime_weights["cvd"] * z_cvd +
            regime_weights["lev"] * z_lev
        )

        # Нелинейная активация
        score = np.tanh(raw_score * 1.5)

        # === ЛОГИЧЕСКИЕ ГЕЙТЫ (enhanced) ===
        triggered = []
        blocked = False

        # 1. Дивергенция CVD и OBI
        if z_wobi > 1.5 and z_cvd < -0.8:
            blocked = True
            triggered.append("CVD_OBI_DIVERGENCE")

        # 2. Спуфинг
        if features.spoof_score > settings.spoof_threshold:
            blocked = True
            triggered.append("SPOOFING_DETECTED")

        # 3. Перегрев плеча без спотового подтверждения
        if features.leverage_velocity > 2.5 and abs(features.taker_aggression) < 0.3:
            blocked = True
            triggered.append("LEVERAGE_WITHOUT_SPOT_SUPPORT")

        # 4. HIGH_VOL regime gate (new from Priority 2) - блокируем агрессивные сигналы в хаосе
        if features.regime_name == "HIGH_VOL" and features.leverage_velocity > 1.8:
            blocked = True
            triggered.append("HIGH_VOL_REGIME")

        direction = "NEUTRAL"
        if not blocked:
            if score > settings.pump_threshold:
                direction = "LONG"
                triggered.append("PRE_PUMP")
            elif score < settings.dump_threshold:
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
        if z_wobi > 1.2:
            parts.append(f"Сильный дисбаланс в стакане (WOBI z={z_wobi:.2f})")
        if z_taker > 1.0:
            parts.append(f"Доминирование агрессивных покупок (Taker z={z_taker:.2f})")
        if z_lev > 1.5:
            parts.append(f"Быстрый набор плеча (θ_LV z={z_lev:.2f})")

        if regime_name == "HIGH_VOL":
            parts.append("⚠️ HIGH_VOL режим - сигналы фильтруются")
        if "CVD_OBI_DIVERGENCE" in triggered:
            parts.append("⚠️ Дивергенция - возможен ложный пробой")
        if "SPOOFING_DETECTED" in triggered:
            parts.append("🚫 Обнаружен спуфинг - сигнал заблокирован")
        if "HIGH_VOL_REGIME" in triggered:
            parts.append("🚨 HIGH_VOL режим + высокое плечо - сигнал блокирован")

        return " | ".join(parts) if parts else "Нейтральная микроструктура"
