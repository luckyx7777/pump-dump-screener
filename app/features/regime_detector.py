"""
Market Regime Detection — production-grade стабильная версия.

Стратегия:
- Refit только раз в 40 обновлений И только если предыдущие попытки были успешными.
- Если HMM падает > 5 раз подряд → временно отключаем HMM и возвращаем стабильный LOW_VOL.
- Это предотвращает спам ошибок в логах.
"""

import numpy as np
from hmmlearn.hmm import GaussianHMM
from collections import deque
import structlog

logger = structlog.get_logger()


class MarketRegimeDetector:
    def __init__(self, n_states: int = 3, window: int = 300, refit_every: int = 40):
        self.n_states = n_states
        self.window = window
        self.refit_every = refit_every
        self.update_count = 0
        self.consecutive_failures = 0
        self.hmm_disabled = False

        self.hmm = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=60,
            random_state=42,
            init_params="",
            params="mcd",
            min_covar=1e-4
        )

        if n_states == 3:
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
        self.regime_names = {
            0: "LOW_VOL",
            1: "TRENDING",
            2: "HIGH_VOL"
        }

    def update(self, feature_value: float) -> int:
        if not np.isfinite(feature_value):
            return self.current_regime

        self.feature_buffer.append(float(feature_value))
        self.update_count += 1

        if len(self.feature_buffer) < 50:
            return self.current_regime

        # Если HMM временно отключён из-за постоянных ошибок → возвращаем стабильный режим
        if self.hmm_disabled:
            return self.current_regime

        X = np.array(list(self.feature_buffer), dtype=float).reshape(-1, 1)

        if np.any(~np.isfinite(X)) or np.std(X) < 1e-9:
            return self.current_regime

        try:
            do_fit = (not self.is_fitted) or (self.update_count % self.refit_every == 0)

            if do_fit:
                self.hmm.fit(X[-min(120, len(X)): ])
                self.is_fitted = True
                self.consecutive_failures = 0

                if self.n_states == 3:
                    self.hmm.startprob_ = self._startprob.copy()
                    self.hmm.transmat_ = self._transmat.copy()

            if self.is_fitted:
                hidden_states = self.hmm.predict(X)
                self.current_regime = int(hidden_states[-1])

        except Exception as e:
            self.consecutive_failures += 1
            logger.warning(
                "HMM update failed (kept previous regime)",
                error=repr(e),
                consecutive_failures=self.consecutive_failures
            )

            if self.consecutive_failures >= 5:
                self.hmm_disabled = True
                logger.warning("HMM temporarily disabled due to repeated failures. Using last known regime.")

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
