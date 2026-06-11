from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from .models import Signal


def format_signal(signal: Signal, now: datetime | None = None) -> str:
    timestamp = now or datetime.now(timezone.utc)
    side_label = "LONG" if signal.side == "LONG" else "SHORT"
    side_icon = "🟢" if signal.side == "LONG" else "🔴"
    strength = f"🔥 {signal.strength}" if signal.strength == "СИЛЬНЫЙ" else signal.strength

    return f"""
{side_icon} <b>{side_label} SMC СИГНАЛ</b> | <code>{escape(signal.symbol)}</code>

<b>Market Bias:</b>
• 4H: <b>{escape(signal.bias_4h)}</b>
• 1H: <b>{escape(signal.bias_1h)}</b>

<b>15m Entry Point:</b>
Цена сейчас: <code>{signal.current_price:.4f}</code>
Ликвидность: High <code>{signal.recent_high:.4f}</code> | Low <code>{signal.recent_low:.4f}</code>
POI / Order Block: около <code>{signal.poi:.4f}</code>

<b>Причина:</b> {escape(signal.reason)}
<b>Сила сигнала:</b> {escape(strength)}

Stop-Loss: <code>{signal.stop_loss:.4f}</code>
Take-Profit: <code>{signal.take_profit:.4f}</code> (примерно 1:2.8)

{timestamp.strftime("%H:%M:%S")} UTC
""".strip()
