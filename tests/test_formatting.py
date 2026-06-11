import unittest
from datetime import datetime, timezone

from smart_money_bot.formatting import calculate_risk_reward, format_signal
from smart_money_bot.models import Signal


class FormattingTest(unittest.TestCase):
    def test_calculate_risk_reward_uses_signal_levels(self):
        signal = Signal(
            symbol="RIVERUSDT",
            side="SHORT",
            bias_4h="BEARISH",
            bias_1h="BEARISH",
            current_price=5.0710,
            recent_high=5.2600,
            recent_low=5.0010,
            poi=5.2600,
            reason="Медвежья свеча + сопротивление",
            strength="Средний",
            stop_loss=5.1465,
            take_profit=4.9368,
        )

        self.assertAlmostEqual(calculate_risk_reward(signal), 1.77748, places=5)

    def test_format_signal_shows_calculated_risk_reward(self):
        signal = Signal(
            symbol="RIVERUSDT",
            side="SHORT",
            bias_4h="BEARISH",
            bias_1h="BEARISH",
            current_price=5.0710,
            recent_high=5.2600,
            recent_low=5.0010,
            poi=5.2600,
            reason="Медвежья свеча + сопротивление",
            strength="Средний",
            stop_loss=5.1465,
            take_profit=4.9368,
        )

        message = format_signal(signal, now=datetime(2026, 6, 11, 20, 0, 46, tzinfo=timezone.utc))

        self.assertIn("Take-Profit: <code>4.9368</code> (примерно 1:1.78)", message)


if __name__ == "__main__":
    unittest.main()
