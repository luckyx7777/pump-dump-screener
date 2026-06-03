"""
Iceberg Volume Estimator — улучшенная реализация по документу (раздел 2.5)

Идея:
Если на фиксированном ценовом уровне P* было проторгованно значительно больше объёма,
чем изменился видимый объём в стакане — вероятно, там был скрытый айсберг.
"""

from collections import deque
from typing import Dict, Optional


class IcebergEstimator:
    """
    Оценивает наличие и примерный размер скрытых айсбергов.
    """

    def __init__(self, window_trades: int = 30):
        self.window_trades = window_trades
        # Храним последние сделки по цене: price -> список (timestamp, qty)
        self.trades_by_price: Dict[float, deque] = {}
        self.last_estimate: float = 0.0

    def update_trade(self, price: float, qty: float, timestamp: float):
        """Добавляет новую сделку."""
        if price not in self.trades_by_price:
            self.trades_by_price[price] = deque(maxlen=self.window_trades)
        self.trades_by_price[price].append((timestamp, qty))

    def estimate_iceberg(
        self,
        price: float,
        visible_bid_qty_before: float,
        visible_bid_qty_after: float,
        current_time: float
    ) -> float:
        """
        Оценивает скрытый объём айсберга на уровне price.

        visible_bid_qty_before — объём бида на этом уровне до сделок
        visible_bid_qty_after  — после
        """
        if price not in self.trades_by_price:
            return 0.0

        trades = self.trades_by_price[price]
        if not trades:
            return 0.0

        # Суммируем объём сделок за последние N обновлений на этом уровне
        traded_qty = sum(q for ts, q in trades if current_time - ts < 5.0)  # последние 5 сек

        visible_delta = visible_bid_qty_before - visible_bid_qty_after

        # Если проторговали значительно больше, чем уменьшился видимый объём
        if visible_delta < 0:
            # Цена не упала, несмотря на продажи → вероятно айсберг поддерживал
            iceberg_size = traded_qty - abs(visible_delta)
            self.last_estimate = max(0.0, iceberg_size)
            return self.last_estimate

        return 0.0

    def get_last_estimate(self) -> float:
        return self.last_estimate