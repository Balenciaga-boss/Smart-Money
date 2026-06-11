from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: str
    bias_4h: str
    bias_1h: str
    current_price: float
    recent_high: float
    recent_low: float
    poi: float
    reason: str
    strength: str
    stop_loss: float
    take_profit: float
