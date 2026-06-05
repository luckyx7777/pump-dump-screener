"""
Market Regime Detection с помощью Hidden Markov Model (HMM).
Полная реализация идеи из документа (3 состояния: LV / TR / HV + динамические веса).
"""

import numpy as np
from hmmlearn.hmm import GaussianHMM
from collections import deque
from typing import Literal

import structlog

logger = structlog.get_logger()


class MarketRegimeDetector:
    def __init__(self, n_states: int = 3, window: int = 300):
        self.n_states = n_states
        self.window = window
        self.hmm = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=150,
            random_state=42,
            init_params="kmeans"  # better init
        )
        # Explicit transition matrix and start probabilities (aligned with methodology spirit)
        # States: 0=LOW_VOL, 1=TRENDING, 2=HIGH_VOL
        if n_states == 3:
            self.hmm.startprob_ = np.array([0.5, 0.3, 0.2])
            self.hmm.transmat_ = np.array([
                [0.70, 0.25, 0.05],  # LOW_VOL  -> stay calm or move to trend
                [0.15, 0.65, 0.20],  # TRENDING -> can go high vol
                [0.10, 0.30, 0.60],  # HIGH_VOL -> eventually calm down
            ])
        self.is_fitted = False
        self.feature_buffer: deque[float] = deque(maxlen=window)
        self.current_regime: int = 0
        self.regime_names = {
            0: "LOW_VOL",
            1: "TRENDING",
            2: "HIGH_VOL"
        }

    def update(self, feature_value: float) -> int:
        """
        Обновляет модель и возвращает текущий режим.
        """
        self.feature_buffer.append(feature_value)

        if len(self.feature_buffer) < 50:
            return self.current_regime

        X = np.array(list(self.feature_buffer)).reshape(-1, 1)

        try:
            if not self.is_fitted:
                self.hmm.fit(X)
                self.is_fitted = True
            else:
                # Incremental refit on recent data
                self.hmm.fit(X[-min(150, len(X)): ])

            hidden_states = self.hmm.predict(X)
            self.current_regime = int(hidden_states[-1])
        except Exception as e:
            logger.warning("HMM update failed", error=str(e))

        return self.current_regime

    def get_regime_name(self) -> str:
        return self.regime_names.get(self.current_regime, "UNKNOWN")

    def get_regime_weights(self) -> dict:
        """
        Динамические веса для скоринга в зависимости от режима (W_k(R_t) из документа).
        """
        regime = self.current_regime
        if regime == 0:  # LOW_VOL - фокус на OBI / MLOFI
            return {
                "wobi": 0.45,
                "taker_aggression": 0.25,
                "cvd": 0.15,
                "leverage_velocity": 0.15
            }
        elif regime == 1:  # TRENDING - фокус на CVD и плечо
            return {
                "wobi": 0.30,
                "taker_aggression": 0.25,
                "cvd": 0.25,
                "leverage_velocity": 0.20
            }
        else:  # HIGH_VOL - фильтры ликвидности и плеча
            return {
                "wobi": 0.20,
                "taker_aggression": 0.30,
                "cvd": 0.25,
                "leverage_velocity": 0.25
            }
