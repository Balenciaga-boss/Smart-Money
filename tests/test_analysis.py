import unittest

from smart_money_bot.analysis import Candle, analyze_market_data, calculate_atr


def make_candles(opens, closes, highs=None, lows=None):
    highs = highs or [max(o, c) + 1 for o, c in zip(opens, closes)]
    lows = lows or [min(o, c) - 1 for o, c in zip(opens, closes)]
    return [
        Candle(timestamp=index, open=open_, high=high, low=low, close=close, volume=100)
        for index, (open_, close, high, low) in enumerate(zip(opens, closes, highs, lows))
    ]


class AnalysisTest(unittest.TestCase):
    def test_calculate_atr_uses_true_range(self):
        candles = make_candles(
            opens=[10, 11, 9],
            closes=[10, 11, 9],
            highs=[12, 15, 14],
            lows=[9, 10, 8],
        )

        atr = calculate_atr(candles, period=2)

        self.assertIsNone(atr[0])
        self.assertEqual(atr[1], 4)
        self.assertEqual(atr[2], 5.5)

    def test_analyze_market_data_returns_long_signal_with_risk_levels(self):
        candles_15m = make_candles(
            [100] * 39 + [105],
            [101] * 39 + [112],
            highs=[103] * 39 + [113],
            lows=[98] * 39 + [104],
        )
        candles_1h = make_candles([90] * 20, [110] * 20)
        candles_4h = make_candles([80] * 25, [120] * 25)

        signal = analyze_market_data("ENAUSDT", candles_15m, candles_1h, candles_4h)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, "LONG")
        self.assertEqual(signal.symbol, "ENAUSDT")
        self.assertLess(signal.stop_loss, signal.current_price)
        self.assertLess(signal.current_price, signal.take_profit)
        self.assertEqual(signal.bias_1h, "BULLISH")
        self.assertEqual(signal.bias_4h, "BULLISH")

    def test_analyze_market_data_returns_none_when_timeframes_conflict(self):
        candles_15m = make_candles([100] * 40, [102] * 40)
        candles_1h = make_candles([120] * 20, [90] * 20)
        candles_4h = make_candles([80] * 25, [120] * 25)

        self.assertIsNone(analyze_market_data("SUIUSDT", candles_15m, candles_1h, candles_4h))


if __name__ == "__main__":
    unittest.main()
