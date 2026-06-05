"""
Полноценный асинхронный WebSocket Collector для Bybit V5 (Linear).
Поддерживает orderbook, trades, tickers (OI + funding), liquidation.
"""

import asyncio
import json
from typing import Dict, Callable, Optional
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.features.orderbook import OrderBook
from app.features.engine import FeatureEngine
from app.config import settings
import structlog

logger = structlog.get_logger()


class BybitCollector:
    def __init__(
        self,
        symbols: list[str],
        orderbooks: Dict[str, OrderBook],
        engines: Dict[str, FeatureEngine],
        on_feature: Optional[Callable] = None,
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
            self.tasks.append(asyncio.create_task(self._run_bybit_stream(symbol)))

        logger.info("Bybit collectors started", symbols=self.symbols)

    async def stop(self):
        self.running = False
        for task in self.tasks:
            task.cancel()
        if self.session:
            await self.session.close()
        logger.info("Bybit collectors stopped")

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def _run_bybit_stream(self, symbol: str):
        ob = self.orderbooks[symbol]
        engine = self.engines[symbol]

        url = "wss://stream.bybit.com/v5/public/linear"
        logger.info("Connecting to Bybit V5", symbol=symbol)

        async with self.session.ws_connect(url, heartbeat=20) as ws:
            subscribe_msg = {
                "op": "subscribe",
                "args": [
                    f"orderbook.500.{symbol}",
                    f"publicTrade.{symbol}",
                    f"tickers.{symbol}",
                    f"liquidation.{symbol}"
                ]
            }
            await ws.send_json(subscribe_msg)

            async for msg in ws:
                if not self.running:
                    break
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)

                    topic = data.get("topic", "")
                    if topic.startswith("orderbook"):
                        await self._handle_bybit_orderbook(data, ob, engine, symbol)
                    elif topic.startswith("publicTrade"):
                        await self._handle_bybit_trade(data, engine)
                    elif topic.startswith("tickers"):
                        self._handle_bybit_ticker(data, engine, symbol)
                    elif topic.startswith("liquidation"):
                        self._handle_bybit_liquidation(data, engine, symbol)

    async def _handle_bybit_orderbook(self, data: dict, ob: OrderBook, engine: FeatureEngine, symbol: str):
        if data.get("type") == "snapshot":
            bids = [(float(x[0]), float(x[1])) for x in data["data"]["b"]]
            asks = [(float(x[0]), float(x[1])) for x in data["data"]["a"]]
            ob.apply_snapshot(bids, asks, update_id=int(data["data"].get("u", 0)))
        else:
            if ob.update_bybit(data["data"]):
                await self._update_features(symbol, ob, engine)

    async def _handle_bybit_trade(self, data: dict, engine: FeatureEngine):
        for trade in data.get("data", []):
            price = float(trade["p"])
            qty = float(trade["v"])
            is_buy = trade["S"] == "Buy"
            engine.update_cvd(price, qty, is_buy=is_buy)

    def _handle_bybit_ticker(self, data: dict, engine: FeatureEngine, symbol: str):
        """ Обработка tickers: OI + fundingRate (critical for θ_LV и Basis) """
        ticker = data.get("data", {})
        if not ticker:
            return

        try:
            open_interest = float(ticker.get("openInterest", 0) or 0)
            funding_rate = float(ticker.get("fundingRate", 0) or 0)

            # Обновляем в engine (OI для Leverage Velocity)
            if hasattr(engine, "update_derivative_data"):
                engine.update_derivative_data(open_interest, funding_rate)

            # Обновляем mid для cross-exchange Basis
            last_price = float(ticker.get("lastPrice", 0) or 0)
            if last_price > 0 and hasattr(engine, "update_basis"):
                # Bybit mid приблизительно = lastPrice (Perp)
                engine.update_basis(None, last_price)  # binance_mid будет обновляться из другого места

        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Bybit ticker parse error", symbol=symbol, error=str(e))

    def _handle_bybit_liquidation(self, data: dict, engine: FeatureEngine, symbol: str):
        """ Базовая обработка ликвидаций (placeholder для кластеров) """
        liqs = data.get("data", [])
        for liq in liqs:
            try:
                side = liq.get("side", "")
                price = float(liq.get("price", 0) or 0)
                size = float(liq.get("size", 0) or 0)
                logger.info("Bybit liquidation", symbol=symbol, side=side, price=price, size=size)
                # TODO: добавить в engine буфер ликвидаций для кластерного анализа и proximity
            except Exception:
                pass

    async def _update_features(self, symbol: str, ob: OrderBook, engine: FeatureEngine):
        if not ob.is_initialized:
            return

        bids, asks = ob.get_top_levels(20)
        mid = ob.get_mid_price() or 0.0

        features = engine.get_current_features(
            bids=bids,
            asks=asks,
            mid_price=mid
        )

        if self.on_feature:
            await self.on_feature(symbol, features)
