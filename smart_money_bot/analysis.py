from __future__ import annotations

from statistics import mean

from .models import Candle, Signal


def calculate_atr(candles: list[Candle], period: int = 14) -> list[float | None]:
    true_ranges: list[float] = []

    for index, candle in enumerate(candles):
        if index == 0:
            true_range = candle.high - candle.low
        else:
            previous_close = candles[index - 1].close
            true_range = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        true_ranges.append(true_range)

    atr: list[float | None] = []
    for index in range(len(true_ranges)):
        if index + 1 < period:
            atr.append(None)
            continue
        window = true_ranges[index + 1 - period : index + 1]
        atr.append(mean(window))

    return atr


def analyze_market_data(
    symbol: str,
    candles_15m: list[Candle],
    candles_1h: list[Candle],
    candles_4h: list[Candle],
) -> Signal | None:
    if len(candles_15m) < 40 or len(candles_1h) < 12 or len(candles_4h) < 20:
        return None

    bias_4h = "BULLISH" if candles_4h[-1].close > candles_4h[-20].open else "BEARISH"
    bias_1h = "BULLISH" if candles_1h[-1].close > candles_1h[-12].open else "BEARISH"
    if bias_4h != bias_1h:
        return None

    current_price = candles_15m[-1].close
    recent = candles_15m[-40:]
    recent_high = max(candle.high for candle in recent)
    recent_low = min(candle.low for candle in recent)
    last = candles_15m[-1]
    atr = calculate_atr(candles_15m)[-1]
    if atr is None or atr <= 0:
        return None

    side: str | None = None
    reason = ""
    strength = "Средний"

    if bias_4h == "BULLISH" and last.close > last.open and current_price > recent_low * 1.002:
        side = "LONG"
        reason = "Бычья свеча + поддержка"
        if last.close - last.open > atr * 1.8:
            strength = "СИЛЬНЫЙ"
    elif bias_4h == "BEARISH" and last.close < last.open and current_price < recent_high * 0.998:
        side = "SHORT"
        reason = "Медвежья свеча + сопротивление"
        if last.open - last.close > atr * 1.8:
            strength = "СИЛЬНЫЙ"

    if side is None:
        return None

    stop_loss = current_price - atr * 1.8 if side == "LONG" else current_price + atr * 1.8
    take_profit = current_price + atr * 3.2 if side == "LONG" else current_price - atr * 3.2
    poi = recent_low if side == "LONG" else recent_high

    return Signal(
        symbol=symbol,
        side=side,
        bias_4h=bias_4h,
        bias_1h=bias_1h,
        current_price=current_price,
        recent_high=recent_high,
        recent_low=recent_low,
        poi=poi,
        reason=reason,
        strength=strength,
        stop_loss=round(stop_loss, 4),
        take_profit=round(take_profit, 4),
    )
