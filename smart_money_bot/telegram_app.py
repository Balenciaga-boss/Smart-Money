from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from .analysis import analyze_market_data
from .config import Settings
from .exchange import BybitMarketData
from .formatting import format_signal
from .watchlist import WatchlistStore


class SmartMoneyBot:
    def __init__(self, settings: Settings, market_data: BybitMarketData, watchlist: WatchlistStore):
        self.settings = settings
        self.market_data = market_data
        self.watchlist = watchlist
        self.last_signals: dict[str, datetime] = {}

    def create_application(self) -> Application:
        application = Application.builder().token(self.settings.telegram_token).build()
        application.add_handler(CommandHandler("add", self.add_symbol))
        application.add_handler(CommandHandler("remove", self.remove_symbol))
        application.add_handler(CommandHandler("list", self.list_symbols))
        application.add_handler(CommandHandler("status", self.status))
        application.job_queue.run_repeating(
            self.scan,
            interval=self.settings.scan_interval_seconds,
            first=10,
        )
        return application

    async def add_symbol(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if not context.args:
            await update.message.reply_text("Пример: /add LABUSDT")
            return

        symbol = context.args[0]
        if self.watchlist.add(symbol):
            await update.message.reply_html(f"✅ Добавлена <code>{WatchlistStore.normalize(symbol)}</code>")
        else:
            await update.message.reply_text("⚠️ Уже в списке или символ пустой")

    async def remove_symbol(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if not context.args:
            await update.message.reply_text("Пример: /remove ENAUSDT")
            return

        symbol = context.args[0]
        if self.watchlist.remove(symbol):
            await update.message.reply_html(f"🗑 Удалена <code>{WatchlistStore.normalize(symbol)}</code>")
        else:
            await update.message.reply_text("⚠️ Такого символа нет в списке")

    async def list_symbols(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        symbols = self.watchlist.load()
        lines = "\n".join(f"• <code>{symbol}</code>" for symbol in symbols)
        await update.message.reply_html(f"<b>SMC Watchlist:</b>\n{lines}")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        await update.message.reply_text(
            "✅ SMC Bot активен\n\n"
            "📡 Подключён через Bybit API\n"
            f"👀 Мониторим: {len(self.watchlist.load())} монет\n"
            f"🔄 Сканирование: каждые {self.settings.scan_interval_seconds} сек"
        )

    async def scan(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        symbols = self.watchlist.load()
        tasks = [self._scan_symbol(context, symbol) for symbol in symbols]
        await asyncio.gather(*tasks)

    async def _scan_symbol(self, context: ContextTypes.DEFAULT_TYPE, symbol: str) -> None:
        try:
            candles_15m = self.market_data.fetch_candles(symbol, "15m", 250)
            candles_1h = self.market_data.fetch_candles(symbol, "1h", 150)
            candles_4h = self.market_data.fetch_candles(symbol, "4h", 100)
            signal = analyze_market_data(symbol, candles_15m, candles_1h, candles_4h)
            if signal is None or self._is_in_cooldown(signal.symbol, signal.side):
                return

            await context.bot.send_message(
                chat_id=self.settings.telegram_chat_id,
                text=format_signal(signal),
                parse_mode=ParseMode.HTML,
            )
            self.last_signals[self._cooldown_key(signal.symbol, signal.side)] = datetime.now(timezone.utc)
        except Exception as exc:
            print(f"Ошибка {symbol}: {exc}")

    def _is_in_cooldown(self, symbol: str, side: str) -> bool:
        key = self._cooldown_key(symbol, side)
        last_sent_at = self.last_signals.get(key)
        if last_sent_at is None:
            return False

        cooldown = timedelta(minutes=self.settings.signal_cooldown_minutes)
        return datetime.now(timezone.utc) - last_sent_at < cooldown

    @staticmethod
    def _cooldown_key(symbol: str, side: str) -> str:
        return f"{symbol}_{side}"
