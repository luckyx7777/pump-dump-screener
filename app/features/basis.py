"""
Cross-Exchange Basis Calculator
Binance Spot mid price vs Bybit Linear Perpetual mid price.

Согласно документу (раздел 3.3):
Аномальное расширение базиса + рост CVD на Binance + рост OI на Bybit
= высокий шанс скоординированного импульса (пампа).
"""

from collections import deque
from typing import Optional


class CrossExchangeBasis:
    """
    Отслеживает динамику базиса между Binance Spot и Bybit Perp.
    """

    def __init__(self, window: int = 120):
        self.window = window
        self.binance_mids: deque[float] = deque(maxlen=window)
        self.bybit_mids: deque[float] = deque(maxlen=window)
        self.last_basis: float = 0.0
        self.last_basis_change: float = 0.0

    def update(self, binance_mid: Optional[float], bybit_mid: Optional[float]) -> float:
        """
        Обновляет базис и возвращает текущее значение.
        """
        if binance_mid is None or bybit_mid is None:
            return self.last_basis

        self.binance_mids.append(binance_mid)
        self.bybit_mids.append(bybit_mid)

        self.last_basis = bybit_mid - binance_mid

        if len(self.binance_mids) >= 2:
            prev_basis = self.bybit_mids[-2] - self.binance_mids[-2]
            self.last_basis_change = self.last_basis - prev_basis

        return self.last_basis

    def get_basis(self) -> float:
        return self.last_basis

    def get_basis_change(self) -> float:
        return self.last_basis_change

    def is_anomalous_expansion(self, threshold: float = 0.8) -> bool:
        """
        Простой детектор аномального расширения базиса.
        """
        return abs(self.last_basis_change) > threshold and len(self.binance_mids) > 30