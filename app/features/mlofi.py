"""
Улучшенная реализация Multi-Level Order Flow Imbalance (MLOFI)
по методологии Конта и Стойкова (документ, раздел 2.2).

Полная формула:
e_n^(i) = 1_{P^b_n,i >= P^b_{n-1},i} * q^b_n,i - 1_{P^b_n,i < P^b_{n-1},i} * q^b_{n-1},i
        - (аналогично для аска)

MLOFI = Σ β_i * Σ e_n^(i)  за окно
"""

from collections import deque
from typing import List, Dict, Tuple
import numpy as np
from app.models import OrderBookLevel


class MultiLevelOFICalculator:
    """
    Более точная версия MLOFI.
    Хранит предыдущее состояние стакана (цена + объём) по уровням.
    """

    def __init__(self, levels: int = 10, window_updates: int = 60):
        self.levels = levels
        self.window_updates = window_updates

        # История последних состояний: (bid_levels, ask_levels)
        # где levels = список кортежей (price, qty)
        self.history: deque[Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]] = \
            deque(maxlen=window_updates + 1)

        self.last_mlofi: float = 0.0

    def update(self, bids: List[OrderBookLevel], asks: List[OrderBookLevel]) -> float:
        """
        Обновляет калькулятор и возвращает текущее значение MLOFI.
        """
        # Берём топ-N уровней с (price, qty)
        current_bids = [(level.price, level.qty) for level in bids[:self.levels]]
        current_asks = [(level.price, level.qty) for level in asks[:self.levels]]

        self.history.append((current_bids, current_asks))

        if len(self.history) < 2:
            return 0.0

        prev_bids, prev_asks = self.history[-2]

        mlofi = 0.0

        # Считаем по уровням
        for i in range(min(len(current_bids), len(prev_bids), self.levels)):
            # Bid side
            e_bid = self._compute_e_n(
                current_price=current_bids[i][0],
                current_qty=current_bids[i][1],
                prev_price=prev_bids[i][0],
                prev_qty=prev_bids[i][1]
            )

            # Ask side (с минусом)
            e_ask = self._compute_e_n(
                current_price=current_asks[i][0],
                current_qty=current_asks[i][1],
                prev_price=prev_asks[i][0],
                prev_qty=prev_asks[i][1]
            )

            beta = np.exp(-0.25 * i)  # экспоненциальное затухание веса уровня
            mlofi += beta * (e_bid - e_ask)

        self.last_mlofi = mlofi
        return self.last_mlofi

    def _compute_e_n(self, current_price: float, current_qty: float,
                     prev_price: float, prev_qty: float) -> float:
        """
        Точная реализация e_n^(i) из документа.
        """
        if current_price > prev_price:
            return current_qty
        elif current_price < prev_price:
            return -prev_qty
        else:
            # Цена не изменилась → изменение объёма
            return current_qty - prev_qty

    def get_mlofi(self) -> float:
        return self.last_mlofi