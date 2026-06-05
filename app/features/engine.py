"""
Feature Engineering Engine — реализация метрик из документа
Weighted OBI (now with price-distance weighting), CVD, Leverage Velocity, MLOFI, Regime (3 states), Basis и др.
"""

import numpy as np
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, Deque, Optional
from app.models import FeatureVector
from app.config import settings
from app.features.mlofi import MultiLevelOFICalculator
from app.features.regime_detector import MarketRegimeDetector
from app.features.basis import CrossExchangeBasis
from app.features.iceberg import IcebergEstimator
from app.features.spoofing import SpoofingDetector


class FeatureEngine:
    def __init__(self, symbol: str):
        self.symbol = symbol

        # Rolling buffers
        self.cvd_buffer: Deque[float] = deque(maxlen=2000)
        self.trade_volume_buffer: Deque[float] = deque(maxlen=2000)
        self.oi_buffer: Deque[float] = deque(maxlen=500)
        self.spot_volume_buffer: Deque[float] = deque(maxlen=500)

        self.last_cvd: float = 0.0
        self.last_mid: float = 0.0

        # For spoof detection
        self.cancelled_volume: Dict[float, float] = {}
        self.filled_volume: Dict[float, float] = {}

        # Модули из документа
        self.mlofi_calc = MultiLevelOFICalculator(levels=10, window_updates=60)
        self.regime_detector = MarketRegimeDetector(n_states=3, window=300)  # 3 состояния
        self.basis_calc = CrossExchangeBasis(window=120)
        self.last_binance_mid: float | None = None
        self.last_bybit_mid: float | None = None

        self.iceberg_estimator = IcebergEstimator(window_trades=40)
        self.spoofing_detector = SpoofingDetector(min_wall_size=40.0, spoof_threshold=10.0)

    def update_cvd(self, price: float, qty: float, is_buy: bool, is_maker: bool = False):
        delta = qty if is_buy else -qty
        self.last_cvd += delta
        self.cvd_buffer.append(self.last_cvd)
        self.trade_volume_buffer.append(qty)

    def calculate_wobi(self, bids: list, asks: list, levels: int = None) -> float:
        """
        Weighted Order Book Imbalance (WOBI)
        Теперь с весами по ценовой дистанции |p - p_mid| (точно как в документе).
        """
        if levels is None:
            levels = settings.wobi_levels

        if not bids or not asks:
            return 0.0

        sorted_bids = sorted(bids, key=lambda x: -x.price)[:levels]
        sorted_asks = sorted(asks, key=lambda x: x.price)[:levels]

        if not sorted_bids or not sorted_asks:
            return 0.0

        mid_price = (sorted_bids[0].price + sorted_asks[0].price) / 2

        wobi_num = 0.0
        wobi_den = 0.0

        for i in range(min(len(sorted_bids), len(sorted_asks))):
            price = (sorted_bids[i].price + sorted_asks[i].price) / 2
            distance = abs(price - mid_price)

            # Вес по ценовой дистанции (как в документе)
            w = np.exp(-settings.wobi_lambda * distance)

            bid_vol = sorted_bids[i].qty
            ask_vol = sorted_asks[i].qty

            wobi_num += w * (bid_vol - ask_vol)
            wobi_den += w * (bid_vol + ask_vol)

        if wobi_den == 0:
            return 0.0

        return wobi_num / wobi_den

    def calculate_taker_aggression(self, window_seconds: int = None) -> float:
        if window_seconds is None:
            window_seconds = settings.cvd_window_seconds

        if len(self.cvd_buffer) < 2 or len(self.trade_volume_buffer) < 2:
            return 0.0

        n = min(len(self.cvd_buffer), 300)
        recent_cvd = list(self.cvd_buffer)[-n:]
        recent_vol = list(self.trade_volume_buffer)[-n:]

        cvd_delta = recent_cvd[-1] - recent_cvd[0]
        total_vol = sum(recent_vol) or 1.0

        return cvd_delta / total_vol

    def calculate_leverage_velocity(self, delta_oi: float, mid_price: float, spot_volume: float) -> float:
        if spot_volume <= 0:
            return 0.0
        return (delta_oi * mid_price) / spot_volume

    def estimate_iceberg(self, traded_qty_at_level: float, visible_delta: float) -> float:
        if visible_delta >= 0:
            return 0.0
        return max(0.0, traded_qty_at_level - abs(visible_delta))

    def calculate_spoof_score(self, cancelled_qty: float, filled_qty: float) -> float:
        if filled_qty < 1e-8:
            return 999.0
        return cancelled_qty / filled_qty

    def get_current_features(
        self,
        bids: list,
        asks: list,
        mid_price: float,
        current_oi: float = 0.0,
        spot_volume_1m: float = 0.0
    ) -> FeatureVector:
        wobi = self.calculate_wobi(bids, asks)
        taker_agg = self.calculate_taker_aggression()

        theta_lv = self.calculate_leverage_velocity(
            delta_oi=current_oi - (self.oi_buffer[-1] if self.oi_buffer else current_oi),
            mid_price=mid_price,
            spot_volume=spot_volume_1m
        )

        if self.oi_buffer:
            self.oi_buffer.append(current_oi)

        spread = (min([a.price for a in asks]) - max([b.price for b in bids])) if bids and asks else 0.0

        mlofi = self.mlofi_calc.update(bids, asks)

        regime_feature = abs(wobi) * 8 + abs(taker_agg) * 5 + spread * 200
        regime = self.regime_detector.update(regime_feature)

        basis = self.basis_calc.get_basis()

        iceberg = self.iceberg_estimator.get_last_estimate()
        spoof_score = self.spoofing_detector.get_spoof_score()

        return FeatureVector(
            symbol=self.symbol,
            timestamp=datetime.utcnow(),
            wobi=wobi,
            cvd=self.last_cvd,
            taker_aggression=taker_agg,
            leverage_velocity=theta_lv,
            iceberg_estimate=iceberg,
            spoof_score=spoof_score,
            mid_price=mid_price,
            spread=spread,
            imbalance_5=self.calculate_wobi(bids, asks, levels=5),
            mlofi=mlofi,
            regime=regime,
            regime_name=self.regime_detector.get_regime_name(),
        )

    def update_basis(self, binance_mid: float | None, bybit_mid: float | None):
        self.last_binance_mid = binance_mid
        self.last_bybit_mid = bybit_mid
        self.basis_calc.update(binance_mid, bybit_mid)

    def update_iceberg(self, price: float, traded_qty: float,
                       visible_before: float, visible_after: float, timestamp: float):
        self.iceberg_estimator.update_trade(price, traded_qty, timestamp)
        return self.iceberg_estimator.estimate_iceberg(price, visible_before, visible_after, timestamp)

    def update_spoofing(self, bids: list, asks: list):
        bid_tuples = [(b.price, b.qty) for b in bids]
        ask_tuples = [(a.price, a.qty) for a in asks]
        self.spoofing_detector.update_orderbook(bid_tuples, ask_tuples)
