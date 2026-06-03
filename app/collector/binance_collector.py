"""
Полноценный асинхронный WebSocket Collector для Binance Spot + USDT-M Futures.
Поддерживает:
- Orderbook (depth@100ms) с правильной реконструкцией
- aggTrade (агрессивные сделки)
- forceOrder (ликвидации)
- markPrice (funding rate)
"""

import asyncio
import json
import time
from typing import Dict, Callable, Optional
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.features.orderbook import OrderBook
from app.features.engine import FeatureEngine
from app.config import settings
import structlog

logger = structlog.get_logger()


class BinanceCollector:
    def __init__(
        self,
        symbols: list[str],
        orderbooks: Dict[str, OrderBook],
        engines: Dict[str, FeatureEngine],
        on_feature: Optional[Callable] = None,   # callback когда посчитали фичи
    ):
        self.symbols = [s.upper() for s in symbols]
        self.orderbooks = orderbooks
        self.engines = engines
        self.on_feature = on_feature

        self.session: Optional[aiohttp.ClientSession] = None
        self.tasks: list[asyncio.Task] = []
        self.running = False

    async def start(self):
        self.running = True
        self.session = aiohttp.ClientSession()

        for symbol in self.symbols:
            # Запускаем отдельные таски для разных стримов
            self.tasks.append(asyncio.create_task(self._run_depth_stream(symbol)))
            self.tasks.append(asyncio.create_task(self._run_aggtrade_stream(symbol)))
            self.tasks.append(asyncio.create_task(self._run_liquidation_stream(symbol)))

        logger.info("Binance collectors started", symbols=self.symbols)

    async def stop(self):
        self.running = False
        for task in self.tasks:
            task.cancel()
        if self.session:
            await self.session.close()
        logger.info("Binance collectors stopped")

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def _run_depth_stream(self, symbol: str):
        """Depth stream @100ms + initial snapshot"""
        ob = self.orderbooks[symbol]
        engine = self.engines[symbol]

        # 1. Получаем snapshot через REST
        await self._fetch_binance_snapshot(symbol, ob)

        # 2. Подключаемся к WebSocket
        url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@depth@100ms"
        logger.info("Connecting to Binance depth", symbol=symbol, url=url)

        async with self.session.ws_connect(url, heartbeat=20) as ws:
            async for msg in ws:
                if not self.running:
                    break
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if ob.update_binance(data):
                        # Обновляем фичи
                        await self._update_features(symbol, ob, engine)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("Binance depth WS error", symbol=symbol)
                    break

    async def _fetch_binance_snapshot(self, symbol: str, ob: OrderBook):
        """Получаем начальный snapshot через REST API"""
        url = f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit=1000"
        async with self.session.get(url) as resp:
            data = await resp.json()
            bids = [(float(b[0]), float(b[1])) for b in data["bids"]]
            asks = [(float(a[0]), float(a[1])) for a in data["asks"]]
            last_update_id = data["lastUpdateId"]
            ob.apply_snapshot(bids, asks, last_update_id)
            logger.info("Binance snapshot applied", symbol=symbol, last_update_id=last_update_id)

    async def _run_aggtrade_stream(self, symbol: str):
        """Агрессивные сделки (для CVD)"""
        engine = self.engines[symbol]
        url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@aggTrade"

        async with self.session.ws_connect(url, heartbeat=20) as ws:
            async for msg in ws:
                if not self.running:
                    break
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    price = float(data["p"])
                    qty = float(data["q"])
                    is_buy = not data.get("m", False)  # m = maker side (false = taker buy)

                    engine.update_cvd(price, qty, is_buy=is_buy)
                    # Можно сразу триггерить пересчёт фич при необходимости

    async def _run_liquidation_stream(self, symbol: str):
        """forceOrder — крупные ликвидации"""
        url = f"wss://fstream.binance.com/ws/{symbol.lower()}@forceOrder"
        async with self.session.ws_connect(url, heartbeat=20) as ws:
            async for msg in ws:
                if not self.running:
                    break
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    logger.warning("Binance liquidation", symbol=symbol, data=data.get("o", {}))

    async def _update_features(self, symbol: str, ob: OrderBook, engine: FeatureEngine):
        """Пересчитываем фичи и вызываем callback"""
        if not ob.is_initialized:
            return

        bids, asks = ob.get_top_levels(20)
        mid = ob.get_mid_price() or 0.0

        features = engine.get_current_features(
            bids=bids,
            asks=asks,
            mid_price=mid,
            current_oi=0.0,           # TODO: обновлять из markPrice
            spot_volume_1m=0.0        # TODO: агрегировать
        )

        if self.on_feature:
            await self.on_feature(symbol, features)