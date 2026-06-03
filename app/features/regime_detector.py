"""
Market Regime Detection с помощью Hidden Markov Model (HMM).
Используется для динамического взвешивания метрик в скоринге
(как описано в разделе 5.2 документа).

Состояния:
0 - Low Volatility / Ranging
1 - High Volatility / Trending
2 - Transition / News-driven (опционально)
"""

import numpy as np
from hmmlearn.hmm import GaussianHMM
from collections import deque
from typing import Literal


class MarketRegimeDetector:
    def __init__(self, n_states: int = 2, window: int = 300):
        self.n_states = n_states
        self.window = window
        self.hmm = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=100,
            random_state=42
        )
        self.is_fitted = False
        self.feature_buffer: deque[float] = deque(maxlen=window)
        self.current_regime: int = 0
        self.regime_names = {0: "LOW_VOL", 1: "HIGH_VOL"}

    def update(self, feature_value: float) -> int:
        """
        Обновляет модель новыми данными и возвращает текущий режим.
        feature_value — например, |WOBI| * 10 + |Taker Aggression| * 5 + spread * 100
        """
        self.feature_buffer.append(feature_value)

        if len(self.feature_buffer) < 50:
            return self.current_regime

        X = np.array(list(self.feature_buffer)).reshape(-1, 1)

        if not self.is_fitted:
            try:
                self.hmm.fit(X)
                self.is_fitted = True
            except Exception:
                return self.current_regime
        else:
            # Дообучаем incrementally (упрощённо)
            try:
                self.hmm.fit(X[-100:])  # последние 100 точек
            except:
                pass

        # Предсказываем режим для последней точки
        try:
            hidden_states = self.hmm.predict(X)
            self.current_regime = int(hidden_states[-1])
        except:
            pass

        return self.current_regime

    def get_regime_name(self) -> str:
        return self.regime_names.get(self.current_regime, "UNKNOWN")

    def get_regime_weights(self) -> dict:
        """
        Возвращает динамические веса для метрик в зависимости от режима.
        Это реализация идеи из документа (W_k(R_t)).
        """
        if self.current_regime == 0:  # Low vol — больше веса на OBI и OFI
            return {
                "wobi": 0.45,
                "taker_aggression": 0.25,
                "cvd": 0.15,
                "leverage_velocity": 0.15
            }
        else:  # High vol — больше веса на CVD и Leverage
            return {
                "wobi": 0.25,
                "taker_aggression": 0.30,
                "cvd": 0.25,
                "leverage_velocity": 0.20
            }