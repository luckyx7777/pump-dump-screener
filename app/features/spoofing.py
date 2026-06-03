"""
Spoofing / Layering Detector — реализация по документу (раздел 3.1)

Отслеживает:
- Время жизни крупных лимитных уровней (τ_life)
- Коэффициент Ψ_spoof = cancelled_volume / filled_volume
- Если стена исчезает очень быстро без значительного исполнения — спуфинг
"""

from collections import defaultdict
from typing import Dict, List, Tuple
import time


class SpoofingDetector:
    """
    Детектор спуфинга и лейринга.
    """

    def __init__(self, min_wall_size: float = 50.0, spoof_threshold: float = 8.0):
        self.min_wall_size = min_wall_size          # минимальный размер "стены" для анализа
        self.spoof_threshold = spoof_threshold      # порог Ψ_spoof

        # Храним время появления крупных уровней: price -> timestamp
        self.level_appear_time: Dict[float, float] = {}

        # Статистика по уровням
        self.cancelled_volume: Dict[float, float] = defaultdict(float)
        self.filled_volume: Dict[float, float] = defaultdict(float)

        self.last_spoof_score: float = 0.0
        self.detected_spoof_levels: List[float] = []

    def update_orderbook(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]):
        """
        Обновляет состояние на основе текущего стакана.
        bids/asks = список (price, qty)
        """
        current_time = time.time()
        current_prices = {price for price, qty in bids + asks if qty >= self.min_wall_size}

        # Удаляем уровни, которых больше нет
        disappeared = set(self.level_appear_time.keys()) - current_prices

        for price in disappeared:
            appear_time = self.level_appear_time.pop(price, current_time)
            lifetime = current_time - appear_time

            # Если уровень исчез очень быстро — считаем как потенциальный спуф
            if lifetime < 0.8:  # менее 800 мс
                self.cancelled_volume[price] += 1.0  # упрощённо

        # Добавляем новые крупные уровни
        for price, qty in bids + asks:
            if qty >= self.min_wall_size and price not in self.level_appear_time:
                self.level_appear_time[price] = current_time

    def register_fill(self, price: float, qty: float):
        """Регистрирует исполнение на уровне (из trades)."""
        self.filled_volume[price] += qty

    def calculate_spoof_score(self) -> float:
        """
        Считает общий коэффициент спуфинга Ψ_spoof.
        """
        total_cancelled = sum(self.cancelled_volume.values())
        total_filled = sum(self.filled_volume.values()) or 1e-8

        self.last_spoof_score = total_cancelled / total_filled
        return self.last_spoof_score

    def is_spoofing_detected(self) -> bool:
        return self.calculate_spoof_score() > self.spoof_threshold

    def get_spoof_score(self) -> float:
        return self.last_spoof_score

    def reset_stats(self):
        """Сброс статистики (можно вызывать периодически)."""
        self.cancelled_volume.clear()
        self.filled_volume.clear()
        self.detected_spoof_levels.clear()