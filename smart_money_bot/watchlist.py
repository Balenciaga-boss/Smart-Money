from __future__ import annotations

import json
from pathlib import Path


DEFAULT_SYMBOLS = ["ENAUSDT", "SUIUSDT", "XMRUSDT", "RIVERUSDT", "VVVUSDT", "LABUSDT"]


class WatchlistStore:
    def __init__(self, path: str | Path, default_symbols: list[str] | None = None):
        self.path = Path(path)
        self.default_symbols = default_symbols if default_symbols is not None else DEFAULT_SYMBOLS

    def load(self) -> list[str]:
        if not self.path.exists():
            self.save(self.default_symbols)
            return list(self.default_symbols)

        with self.path.open("r", encoding="utf-8") as file:
            symbols = json.load(file)

        if not isinstance(symbols, list):
            raise ValueError(f"Watchlist file must contain a JSON list: {self.path}")

        return [self.normalize(symbol) for symbol in symbols if self.normalize(symbol)]

    def save(self, symbols: list[str]) -> None:
        normalized = []
        seen = set()
        for symbol in symbols:
            clean_symbol = self.normalize(symbol)
            if clean_symbol and clean_symbol not in seen:
                normalized.append(clean_symbol)
                seen.add(clean_symbol)

        with self.path.open("w", encoding="utf-8") as file:
            json.dump(normalized, file, indent=2, ensure_ascii=False)

    def add(self, symbol: str) -> bool:
        symbols = self.load()
        clean_symbol = self.normalize(symbol)
        if not clean_symbol or clean_symbol in symbols:
            return False

        symbols.append(clean_symbol)
        self.save(symbols)
        return True

    def remove(self, symbol: str) -> bool:
        symbols = self.load()
        clean_symbol = self.normalize(symbol)
        if clean_symbol not in symbols:
            return False

        symbols.remove(clean_symbol)
        self.save(symbols)
        return True

    @staticmethod
    def normalize(symbol: str) -> str:
        return str(symbol).strip().upper()
