"""
Multi-factor Scoring Engine with Z-score normalization and logical gating.
Based on the methodology from the document.
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

    def score(self, features: FeatureVector) -> Signal:
        """
        Итоговый скоринг S(t) ∈ [-1, 1]
        + применение гейтов из документа (дивергенция CVD/OBI, спуфинг, θ_LV и т.д.)
        """
        buf = self._get_or_create_buffer(features.symbol)
        buf.append(features)

        # Собираем историю для Z-score
        wobi_history = [f.wobi for f in buf]
        cvd_history = [f.cvd for f in buf]
        taker_history = [f.taker_aggression for f in buf]
        lev_history = [f.leverage_velocity for f in buf]

        z_wobi = self._calculate_zscore(wobi_history, features.wobi)
        z_cvd = self._calculate_zscore(cvd_history, features.cvd)
        z_taker = self._calculate_zscore(taker_history, features.taker_aggression)
        z_lev = self._calculate_zscore(lev_history, features.leverage_velocity)

        # Базовый линейный скоринг (можно улучшить через tanh + веса)
        raw_score = (
            0.35 * z_wobi +
            0.25 * z_taker +
            0.20 * z_cvd +
            0.20 * z_lev
        )

        # Нелинейная активация
        score = np.tanh(raw_score * 1.5)

        # === ЛОГИЧЕСКИЕ ГЕЙТЫ (из документа) ===
        triggered = []
        blocked = False

        # 1. Дивергенция CVD и OBI (самый важный гейт)
        if z_wobi > 1.5 and z_cvd < -0.8:
            blocked = True
            triggered.append("CVD_OBI_DIVERGENCE")

        # 2. Высокий спуфинг
        if features.spoof_score > settings.spoof_threshold:
            blocked = True
            triggered.append("SPOOFING_DETECTED")

        # 3. Перегрев плеча без спотового подтверждения
        if features.leverage_velocity > 2.5 and abs(features.taker_aggression) < 0.3:
            blocked = True
            triggered.append("LEVERAGE_WITHOUT_SPOT_SUPPORT")

        direction = "NEUTRAL"
        if not blocked:
            if score > settings.pump_threshold:
                direction = "LONG"
                triggered.append("PRE_PUMP")
            elif score < settings.dump_threshold:
                direction = "SHORT"
                triggered.append("PRE_DUMP")

        explanation = self._generate_explanation(features, z_wobi, z_taker, z_cvd, z_lev, triggered)

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

    def _generate_explanation(self, f: FeatureVector, z_wobi, z_taker, z_cvd, z_lev, triggered) -> str:
        parts = []
        if z_wobi > 1.2:
            parts.append(f"Сильный дисбаланс в стакане (WOBI z={z_wobi:.2f})")
        if z_taker > 1.0:
            parts.append(f"Доминирование агрессивных покупок (Taker z={z_taker:.2f})")
        if z_lev > 1.5:
            parts.append(f"Быстрый набор плеча (θ_LV z={z_lev:.2f})")

        if "CVD_OBI_DIVERGENCE" in triggered:
            parts.append("⚠️ Дивергенция — возможен ложный пробой")
        if "SPOOFING_DETECTED" in triggered:
            parts.append("🚫 Обнаружен спуфинг — сигнал заблокирован")

        return " | ".join(parts) if parts else "Нейтральная микроструктура"