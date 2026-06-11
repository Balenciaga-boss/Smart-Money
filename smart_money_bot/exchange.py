from __future__ import annotations

from typing import Any

import ccxt

from .models import Candle


class BybitMarketData:
    def __init__(self, api_key: str, api_secret: str):
        self.exchange = ccxt.bybit(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
            }
        )

    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        rows = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return [self._row_to_candle(row) for row in rows]

    @staticmethod
    def _row_to_candle(row: list[Any]) -> Candle:
        timestamp, open_, high, low, close, volume = row
        return Candle(
            timestamp=int(timestamp),
            open=float(open_),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=float(volume),
        )
