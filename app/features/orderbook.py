"""
Professional Order Book reconstruction for Binance and Bybit.
Handles incremental updates with sequence validation (critical for L2 data).
"""

from collections import deque
from typing import Dict, List, Tuple, Optional
import time
from app.models import OrderBookLevel, OrderBookSnapshot


class OrderBook:
    """
    Local order book reconstruction.
    Supports Binance (@depth@100ms) and Bybit (orderbook.500) formats.
    """

    def __init__(self, symbol: str, max_depth: int = 500):
        self.symbol = symbol
        self.max_depth = max_depth
        self.bids: Dict[float, float] = {}   # price -> qty
        self.asks: Dict[float, float] = {}
        self.last_update_id: Optional[int] = None
        self.last_timestamp: float = 0.0
        self.is_initialized: bool = False

    def apply_snapshot(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]], update_id: int):
        """Apply initial snapshot from REST."""
        self.bids = {price: qty for price, qty in bids[:self.max_depth]}
        self.asks = {price: qty for price, qty in asks[:self.max_depth]}
        self.last_update_id = update_id
        self.is_initialized = True
        self.last_timestamp = time.time()

    def update_binance(self, data: dict) -> bool:
        """
        Process Binance diff depth stream.
        Returns True if update was applied successfully.
        """
        if not self.is_initialized:
            return False

        first_update_id = data.get("U")
        last_update_id = data.get("u")

        # Sequence validation (critical!)
        if self.last_update_id is not None:
            if first_update_id > self.last_update_id + 1:
                # Gap detected → need new snapshot
                return False
            if last_update_id <= self.last_update_id:
                return True  # duplicate or old

        # Apply bid updates
        for price_str, qty_str in data.get("b", []):
            price, qty = float(price_str), float(qty_str)
            if qty == 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = qty

        # Apply ask updates
        for price_str, qty_str in data.get("a", []):
            price, qty = float(price_str), float(qty_str)
            if qty == 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = qty

        self.last_update_id = last_update_id
        self.last_timestamp = time.time()
        return True

    def update_bybit(self, data: dict) -> bool:
        """Process Bybit orderbook delta."""
        if not self.is_initialized:
            return False

        # Bybit sends full delta or snapshot in one message
        for side, levels in [("b", data.get("b", [])), ("a", data.get("a", []))]:
            book = self.bids if side == "b" else self.asks
            for level in levels:
                price = float(level[0])
                qty = float(level[1])
                if qty == 0:
                    book.pop(price, None)
                else:
                    book[price] = qty

        self.last_timestamp = time.time()
        return True

    def get_top_levels(self, n: int = 10) -> Tuple[List[OrderBookLevel], List[OrderBookLevel]]:
        """Return top N bids and asks sorted."""
        sorted_bids = sorted(self.bids.items(), key=lambda x: -x[0])[:n]
        sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])[:n]

        return (
            [OrderBookLevel(price=p, qty=q) for p, q in sorted_bids],
            [OrderBookLevel(price=p, qty=q) for p, q in sorted_asks]
        )

    def get_mid_price(self) -> Optional[float]:
        if not self.bids or not self.asks:
            return None
        best_bid = max(self.bids.keys())
        best_ask = min(self.asks.keys())
        return (best_bid + best_ask) / 2

    def get_spread(self) -> Optional[float]:
        if not self.bids or not self.asks:
            return None
        return min(self.asks.keys()) - max(self.bids.keys())

    def to_snapshot(self) -> OrderBookSnapshot:
        bids, asks = self.get_top_levels(20)
        return OrderBookSnapshot(
            symbol=self.symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.fromtimestamp(self.last_timestamp),
            last_update_id=self.last_update_id
        )

    def clear(self):
        self.bids.clear()
        self.asks.clear()
        self.is_initialized = False
        self.last_update_id = None