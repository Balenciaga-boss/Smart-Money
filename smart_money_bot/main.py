from __future__ import annotations

from .config import load_settings
from .exchange import BybitMarketData
from .telegram_app import SmartMoneyBot
from .watchlist import WatchlistStore


def main() -> None:
    settings = load_settings()
    market_data = BybitMarketData(settings.bybit_api_key, settings.bybit_api_secret)
    watchlist = WatchlistStore(settings.watchlist_file)
    bot = SmartMoneyBot(settings, market_data, watchlist)
    application = bot.create_application()

    print(f"SMC Smart Money Bot запущен | Монет: {len(watchlist.load())}")
    application.run_polling()


if __name__ == "__main__":
    main()
