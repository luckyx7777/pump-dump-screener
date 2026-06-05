"""
Market Regime Detection с помощью HMM.
Максимально стабильная версия (без ошибок transmat rows must sum to 1).
"""

import numpy as np
from hmmlearn.hmm import GaussianHMM
from collections import deque
import structlog

logger = structlog.get_logger()


class MarketRegimeDetector:
    def __init__(self, n_states: int = 3, window: int = 300):
        self.n_states = n_states
        self.window = window

        self.hmm = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=100,
            random_state=42,
            init_params="",
            params="mcd"
        )

        if n_states == 3:
            # Жёстко задаём переходы
            raw_transmat = np.array([
                [0.70, 0.25, 0.05],
                [0.15, 0.65, 0.20],
                [0.10, 0.30, 0.60],
            ], dtype=float)
            self._transmat = raw_transmat / raw_transmat.sum(axis=1, keepdims=True)

            self._startprob = np.array([0.5, 0.3, 0.2], dtype=float)
            self._startprob = self._startprob / self._startprob.sum()

            self.hmm.startprob_ = self._startprob.copy()
            self.hmm.transmat_ = self._transmat.copy()

        self.is_fitted = False
        self.feature_buffer: deque[float] = deque(maxlen=window)
        self.current_regime: int = 0
        self.regime_names = {0: "LOW_VOL", 1: "TRENDING", 2: "HIGH_VOL"}

    def update(self, feature_value: float) -> int:
        if not np.isfinite(feature_value):
            return self.current_regime

        self.feature_buffer.append(float(feature_value))

        if len(self.feature_buffer) < 50:
            return self.current_regime

        X = np.array(list(self.feature_buffer)).reshape(-1, 1)

        try:
            if not self.is_fitted:
                self.hmm.fit(X)
                self.is_fitted = True
            else:
                self.hmm.fit(X[-min(120, len(X)): ])

            # Всегда восстанавливаем нашу матрицу после fit
            if self.n_states == 3:
                self.hmm.startprob_ = self._startprob.copy()
                self.hmm.transmat_ = self._transmat.copy()

            hidden_states = self.hmm.predict(X)
            self.current_regime = int(hidden_states[-1])

        except Exception as e:
            logger.warning("HMM update failed", error=str(e))

        return self.current_regime

    def get_regime_name(self) -> str:
        return self.regime_names.get(self.current_regime, "UNKNOWN")

    def get_regime_weights(self) -> dict:
        regime = self.current_regime
        if regime == 0:
            return {"wobi": 0.45, "taker_aggression": 0.25, "cvd": 0.15, "leverage_velocity": 0.15}
        elif regime == 1:
            return {"wobi": 0.30, "taker_aggression": 0.25, "cvd": 0.25, "leverage_velocity": 0.20}
        else:
            return {"wobi": 0.20, "taker_aggression": 0.30, "cvd": 0.25, "leverage_velocity": 0.25}
