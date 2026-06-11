# SMC POI Signal Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace market-price-based alerts with tested POI-based Limit or conditional SMC signals whose SL, structural TP, R:R, strength, and deduplication identity are deterministic.

**Architecture:** Keep `analyze_market_data` as the public orchestration entry point, move pure SMC detection and trade-construction functions into a focused `smc.py` module, and expand immutable models so downstream code consumes complete signal data without recalculation. Configuration supplies validated thresholds, Telegram only formats and sends completed signals, and every invalid market state returns `None`.

**Tech Stack:** Python 3.11, standard-library dataclasses and unittest, ccxt market data, python-telegram-bot.

---

## File Structure

- Create `smart_money_bot/smc.py`: pure POI detection, confluence, level, target, strength, and candidate-ranking functions.
- Modify `smart_money_bot/models.py`: immutable `AnalysisSettings`, `POIZone`, `StructuralTarget`, and expanded `Signal`.
- Modify `smart_money_bot/config.py`: validated SMC thresholds exposed through `Settings`.
- Modify `smart_money_bot/analysis.py`: ATR/bias orchestration and conversion of candles into one complete signal.
- Modify `smart_money_bot/formatting.py`: professional POI-based message and Entry-based R:R display.
- Modify `smart_money_bot/telegram_app.py`: pass analysis settings and deduplicate by POI identity.
- Modify `.env.example`: document all SMC thresholds.
- Modify `tests/test_analysis.py`: integration scenarios for remote Limit, conditional retest, invalidation, structural TP, and R:R rejection.
- Modify `tests/test_formatting.py`: exact public message contract and absence of hype/emoji.
- Create `tests/test_smc.py`: focused detector, SL, target, and strength tests.
- Create `tests/test_config.py`: numeric/boolean setting parsing and startup validation.
- Create `tests/test_models.py`: model invariants and stable POI deduplication key.

### Task 1: Immutable POI And Signal Contracts

**Files:**
- Modify: `smart_money_bot/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing model tests**

```python
import unittest

from smart_money_bot.models import AnalysisSettings, POIZone, Signal, StructuralTarget


class ModelsTest(unittest.TestCase):
    def test_analysis_settings_use_public_defaults(self):
        settings = AnalysisSettings()
        self.assertEqual(settings.max_entry_distance_percent, 0.5)
        self.assertEqual(settings.min_risk_reward, 2.0)

    def test_poi_rejects_inverted_bounds(self):
        with self.assertRaisesRegex(ValueError, "lower_bound"):
            POIZone(
                kind="ORDER_BLOCK",
                side="LONG",
                timeframe="1H",
                lower_bound=101.0,
                upper_bound=100.0,
                formed_at=10,
                swing_extreme=99.0,
            )

    def test_signal_identity_distinguishes_new_poi(self):
        zone = POIZone(
            kind="ORDER_BLOCK",
            side="LONG",
            timeframe="1H",
            lower_bound=0.7400,
            upper_bound=0.7425,
            formed_at=100,
            swing_extreme=0.7390,
        )
        target = StructuralTarget(price=0.7521, reason="15m equal highs")
        signal = Signal.from_trade(
            symbol="ENAUSDT",
            bias_4h="BULLISH",
            bias_1h="BULLISH",
            current_price=0.7500,
            zone=zone,
            order_type="LIMIT",
            entry=0.7425,
            stop_loss=0.7378,
            target=target,
            strength="HIGH",
            confluences=("HTF CHoCH", "liquidity sweep"),
            max_entry_distance_percent=0.5,
        )

        self.assertEqual(
            signal.cooldown_key,
            "ENAUSDT:LONG:ORDER_BLOCK:1H:100",
        )
        self.assertAlmostEqual(signal.risk_reward, 2.042553, places=5)
        self.assertAlmostEqual(signal.entry_distance_percent, 1.010101, places=5)
        self.assertTrue(signal.is_remote)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe' -m unittest tests.test_models -v
```

Expected: import failure for missing `POIZone` and `StructuralTarget`.

- [ ] **Step 3: Implement immutable domain models**

Add frozen dataclasses with runtime validation:

```python
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class POIZone:
    kind: str
    side: str
    timeframe: str
    lower_bound: float
    upper_bound: float
    formed_at: int
    swing_extreme: float
    liquidity_sweep: bool = False
    htf_structure_shift: bool = False
    ltf_choch: bool = False
    first_test: bool = True

    def __post_init__(self) -> None:
        prices = (self.lower_bound, self.upper_bound, self.swing_extreme)
        if not all(isfinite(value) and value > 0 for value in prices):
            raise ValueError("POI prices must be finite and positive")
        if self.lower_bound >= self.upper_bound:
            raise ValueError("lower_bound must be below upper_bound")

    @property
    def entry(self) -> float:
        return self.upper_bound if self.side == "LONG" else self.lower_bound


@dataclass(frozen=True)
class AnalysisSettings:
    max_entry_distance_percent: float = 0.5
    min_risk_reward: float = 2.0
    stop_atr_buffer_multiplier: float = 0.15
    displacement_atr_multiplier: float = 1.5
    swing_window: int = 3
    equal_level_atr_tolerance: float = 0.1
    allow_low_strength_signals: bool = True


@dataclass(frozen=True)
class StructuralTarget:
    price: float
    reason: str


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: str
    order_type: str
    bias_4h: str
    bias_1h: str
    current_price: float
    poi_kind: str
    poi_timeframe: str
    poi_lower: float
    poi_upper: float
    poi_formed_at: int
    entry: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    strength: str
    confluences: tuple[str, ...]
    invalidation_level: float
    target_reason: str
    entry_distance_percent: float
    is_remote: bool
    first_test: bool

    @classmethod
    def from_trade(
        cls,
        *,
        symbol: str,
        bias_4h: str,
        bias_1h: str,
        current_price: float,
        zone: POIZone,
        order_type: str,
        entry: float,
        stop_loss: float,
        target: StructuralTarget,
        strength: str,
        confluences: tuple[str, ...],
        max_entry_distance_percent: float,
    ) -> "Signal":
        risk = abs(entry - stop_loss)
        reward = abs(target.price - entry)
        if risk <= 0:
            raise ValueError("Signal risk must be positive")
        return cls(
            symbol=symbol,
            side=zone.side,
            order_type=order_type,
            bias_4h=bias_4h,
            bias_1h=bias_1h,
            current_price=current_price,
            poi_kind=zone.kind,
            poi_timeframe=zone.timeframe,
            poi_lower=zone.lower_bound,
            poi_upper=zone.upper_bound,
            poi_formed_at=zone.formed_at,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=target.price,
            risk_reward=reward / risk,
            strength=strength,
            confluences=confluences,
            invalidation_level=stop_loss,
            target_reason=target.reason,
            entry_distance_percent=abs(current_price - entry) / entry * 100,
            is_remote=(
                abs(current_price - entry) / entry * 100
                > max_entry_distance_percent
            ),
            first_test=zone.first_test,
        )

    @property
    def cooldown_key(self) -> str:
        return (
            f"{self.symbol}:{self.side}:{self.poi_kind}:"
            f"{self.poi_timeframe}:{self.poi_formed_at}"
        )
```

- [ ] **Step 4: Run model tests and verify GREEN**

Run the Task 1 test command. Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add smart_money_bot/models.py tests/test_models.py
git commit -m "Add POI signal domain models"
```

### Task 2: Validated SMC Configuration

**Files:**
- Modify: `smart_money_bot/config.py`
- Modify: `.env.example`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing configuration tests**

```python
import os
import unittest
from unittest.mock import patch

from smart_money_bot.config import load_settings


class ConfigTest(unittest.TestCase):
    def required_env(self):
        return {
            "BYBIT_API_KEY": "key",
            "BYBIT_API_SECRET": "secret",
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID": "chat",
        }

    def test_loads_smc_defaults(self):
        with patch.dict(os.environ, self.required_env(), clear=True):
            settings = load_settings()

        self.assertEqual(settings.max_entry_distance_percent, 0.5)
        self.assertEqual(settings.min_risk_reward, 2.0)
        self.assertEqual(settings.stop_atr_buffer_multiplier, 0.15)
        self.assertTrue(settings.allow_low_strength_signals)

    def test_rejects_non_positive_risk_reward(self):
        env = {**self.required_env(), "MIN_RISK_REWARD": "0"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "MIN_RISK_REWARD"):
                load_settings()
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe' -m unittest tests.test_config -v
```

Expected: missing SMC attributes on `Settings`.

- [ ] **Step 3: Implement validated settings**

Extend `Settings` with:

```python
max_entry_distance_percent: float = 0.5
min_risk_reward: float = 2.0
stop_atr_buffer_multiplier: float = 0.15
displacement_atr_multiplier: float = 1.5
swing_window: int = 3
equal_level_atr_tolerance: float = 0.1
allow_low_strength_signals: bool = True
```

Add `_positive_float_env` and `_bool_env`; reject non-finite, zero, and negative
values with `RuntimeError(f"{name} must be a finite positive number")`.

Add:

```python
def analysis_settings(self) -> AnalysisSettings:
    return AnalysisSettings(
        max_entry_distance_percent=self.max_entry_distance_percent,
        min_risk_reward=self.min_risk_reward,
        stop_atr_buffer_multiplier=self.stop_atr_buffer_multiplier,
        displacement_atr_multiplier=self.displacement_atr_multiplier,
        swing_window=self.swing_window,
        equal_level_atr_tolerance=self.equal_level_atr_tolerance,
        allow_low_strength_signals=self.allow_low_strength_signals,
    )
```

Update `.env.example`:

```dotenv
MAX_ENTRY_DISTANCE_PERCENT=0.5
MIN_RISK_REWARD=2.0
STOP_ATR_BUFFER_MULTIPLIER=0.15
DISPLACEMENT_ATR_MULTIPLIER=1.5
SWING_WINDOW=3
EQUAL_LEVEL_ATR_TOLERANCE=0.1
ALLOW_LOW_STRENGTH_SIGNALS=true
```

- [ ] **Step 4: Run configuration tests and verify GREEN**

Run the Task 2 test command. Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add smart_money_bot/config.py .env.example tests/test_config.py
git commit -m "Add validated SMC settings"
```

### Task 3: POI Detection And Invalidation

**Files:**
- Create: `smart_money_bot/smc.py`
- Create: `tests/test_smc.py`

- [ ] **Step 1: Write failing POI detector tests**

Create deterministic candle fixtures and tests:

```python
import unittest

from smart_money_bot.models import Candle
from smart_money_bot.smc import detect_fvgs, detect_order_blocks, is_zone_valid


def candle(index, open_, high, low, close):
    return Candle(index, open_, high, low, close, 100)


class SMCDetectionTest(unittest.TestCase):
    def test_detects_bullish_fvg(self):
        candles = [
            candle(1, 100, 101, 99, 100),
            candle(2, 100, 106, 100, 105),
            candle(3, 104, 108, 103, 107),
        ]
        zones = detect_fvgs(candles, "1H")
        self.assertEqual((zones[0].lower_bound, zones[0].upper_bound), (101, 103))
        self.assertEqual(zones[0].side, "LONG")

    def test_detects_bullish_order_block_before_displacement(self):
        candles = [
            candle(1, 100, 101, 98, 99),
            candle(2, 99, 100, 97, 98),
            candle(3, 98, 110, 98, 109),
            candle(4, 109, 112, 108, 111),
        ]
        atr = [None, 3.0, 5.0, 5.0]
        zones = detect_order_blocks(
            candles,
            atr,
            "1H",
            displacement_atr_multiplier=1.5,
            swing_window=1,
        )
        self.assertEqual(zones[0].kind, "ORDER_BLOCK")
        self.assertEqual((zones[0].lower_bound, zones[0].upper_bound), (97, 99))

    def test_close_through_distal_boundary_invalidates_zone(self):
        zone = detect_fvgs(
            [
                candle(1, 100, 101, 99, 100),
                candle(2, 100, 106, 100, 105),
                candle(3, 104, 108, 103, 107),
            ],
            "1H",
        )[0]
        self.assertFalse(is_zone_valid(zone, [candle(4, 103, 104, 99, 100)]))
```

- [ ] **Step 2: Run detector tests and verify RED**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe' -m unittest tests.test_smc.SMCDetectionTest -v
```

Expected: import failure for missing `smart_money_bot.smc`.

- [ ] **Step 3: Implement pure POI functions**

Implement:

```python
def detect_fvgs(candles: list[Candle], timeframe: str) -> list[POIZone]:
    zones = []
    for first, _, third in zip(candles, candles[1:], candles[2:]):
        if first.high < third.low:
            zones.append(
                POIZone(
                    kind="FVG",
                    side="LONG",
                    timeframe=timeframe,
                    lower_bound=first.high,
                    upper_bound=third.low,
                    formed_at=third.timestamp,
                    swing_extreme=first.low,
                )
            )
        elif first.low > third.high:
            zones.append(
                POIZone(
                    kind="FVG",
                    side="SHORT",
                    timeframe=timeframe,
                    lower_bound=third.high,
                    upper_bound=first.low,
                    formed_at=third.timestamp,
                    swing_extreme=first.high,
                )
            )
    return zones

def detect_order_blocks(
    candles: list[Candle],
    atr: list[float | None],
    timeframe: str,
    displacement_atr_multiplier: float,
    swing_window: int,
) -> list[POIZone]:
    zones = []
    for index in range(swing_window + 1, len(candles)):
        origin = candles[index - 1]
        displacement = candles[index]
        current_atr = atr[index]
        if current_atr is None:
            continue
        prior = candles[index - 1 - swing_window : index - 1]
        body = abs(displacement.close - displacement.open)
        if body < current_atr * displacement_atr_multiplier:
            continue
        if (
            origin.close < origin.open
            and displacement.close > max(item.high for item in prior)
        ):
            zones.append(
                POIZone(
                    kind="ORDER_BLOCK",
                    side="LONG",
                    timeframe=timeframe,
                    lower_bound=origin.low,
                    upper_bound=origin.open,
                    formed_at=origin.timestamp,
                    swing_extreme=min(item.low for item in prior + [origin]),
                    liquidity_sweep=(
                        origin.low < min(item.low for item in prior)
                    ),
                    htf_structure_shift=True,
                )
            )
        elif (
            origin.close > origin.open
            and displacement.close < min(item.low for item in prior)
        ):
            zones.append(
                POIZone(
                    kind="ORDER_BLOCK",
                    side="SHORT",
                    timeframe=timeframe,
                    lower_bound=origin.open,
                    upper_bound=origin.high,
                    formed_at=origin.timestamp,
                    swing_extreme=max(item.high for item in prior + [origin]),
                    liquidity_sweep=(
                        origin.high > max(item.high for item in prior)
                    ),
                    htf_structure_shift=True,
                )
            )
    return zones

def is_zone_valid(zone: POIZone, later_candles: list[Candle]) -> bool:
    if zone.side == "LONG":
        return all(candle.close >= zone.lower_bound for candle in later_candles)
    return all(candle.close <= zone.upper_bound for candle in later_candles)
```

Detectors must use completed candles only, preserve `formed_at`, and produce
chronologically ordered zones.

- [ ] **Step 4: Add mitigation-block failing test**

Add:

```python
def test_detects_bullish_mitigation_block_after_valid_return(self):
    candles = [
        candle(1, 100, 101, 98, 99),
        candle(2, 99, 100, 97, 98),
        candle(3, 98, 110, 98, 109),
        candle(4, 109, 112, 108, 111),
        candle(5, 99, 101, 97.5, 100),
        candle(6, 100, 113, 100, 112),
    ]
    atr = [None, 3.0, 5.0, 5.0, 4.0, 5.0]
    order_blocks = detect_order_blocks(
        candles[:4],
        atr[:4],
        "1H",
        displacement_atr_multiplier=1.5,
        swing_window=1,
    )

    zones = detect_mitigation_blocks(
        candles,
        order_blocks,
        atr,
        "1H",
        displacement_atr_multiplier=1.5,
    )

    self.assertEqual(len(zones), 1)
    self.assertEqual(zones[0].kind, "MITIGATION_BLOCK")
    self.assertEqual((zones[0].lower_bound, zones[0].upper_bound), (97.5, 99))
```

- [ ] **Step 5: Run mitigation test and verify RED**

Run the single mitigation test. Expected: no mitigation zone returned.

- [ ] **Step 6: Implement minimal mitigation detection**

Add:

```python
def detect_mitigation_blocks(
    candles: list[Candle],
    order_blocks: list[POIZone],
    atr: list[float | None],
    timeframe: str,
    displacement_atr_multiplier: float,
) -> list[POIZone]:
    zones = []
    index_by_timestamp = {
        item.timestamp: index for index, item in enumerate(candles)
    }
    for origin in order_blocks:
        start = index_by_timestamp[origin.formed_at] + 2
        for index in range(start, len(candles) - 1):
            mitigation = candles[index]
            resumed = candles[index + 1]
            enters = (
                mitigation.low <= origin.upper_bound
                and mitigation.high >= origin.lower_bound
            )
            if not enters or not is_zone_valid(origin, candles[start : index + 1]):
                continue
            resumed_atr = atr[index + 1]
            if resumed_atr is None:
                continue
            body = abs(resumed.close - resumed.open)
            if body < resumed_atr * displacement_atr_multiplier:
                continue
            if origin.side == "LONG" and resumed.close > mitigation.high:
                lower, upper = mitigation.low, mitigation.open
                swing = min(origin.swing_extreme, mitigation.low)
            elif origin.side == "SHORT" and resumed.close < mitigation.low:
                lower, upper = mitigation.open, mitigation.high
                swing = max(origin.swing_extreme, mitigation.high)
            else:
                continue
            zones.append(
                POIZone(
                    kind="MITIGATION_BLOCK",
                    side=origin.side,
                    timeframe=timeframe,
                    lower_bound=lower,
                    upper_bound=upper,
                    formed_at=mitigation.timestamp,
                    swing_extreme=swing,
                    htf_structure_shift=True,
                )
            )
            break
    return zones
```

- [ ] **Step 7: Run all detector tests and verify GREEN**

Run the Task 3 command. Expected: all POI detector tests pass.

- [ ] **Step 8: Commit**

```powershell
git add smart_money_bot/smc.py tests/test_smc.py
git commit -m "Detect and validate SMC POI zones"
```

### Task 4: SL, Structural Targets, R:R, And Strength

**Files:**
- Modify: `smart_money_bot/smc.py`
- Modify: `tests/test_smc.py`

- [ ] **Step 1: Write failing trade-construction tests**

Add tests that assert:

```python
def setUp(self):
    self.long_zone = POIZone(
        kind="ORDER_BLOCK",
        side="LONG",
        timeframe="1H",
        lower_bound=0.7390,
        upper_bound=0.7425,
        formed_at=100,
        swing_extreme=0.7400,
    )
    self.high_zone = replace(
        self.long_zone,
        liquidity_sweep=True,
        htf_structure_shift=True,
        first_test=True,
    )
    self.fvg_zone = POIZone(
        kind="FVG",
        side="LONG",
        timeframe="1H",
        lower_bound=0.7400,
        upper_bound=0.7425,
        formed_at=101,
        swing_extreme=0.7390,
    )

def test_long_stop_is_below_zone_and_swing_with_atr_buffer(self):
    stop = calculate_stop_loss(
        self.long_zone,
        atr=0.02,
        buffer_multiplier=0.15,
    )
    self.assertAlmostEqual(stop, 0.7360)

def test_selects_nearest_structural_target_meeting_minimum_rr(self):
    targets = [
        StructuralTarget(0.7480, "15m swing high"),
        StructuralTarget(0.7521, "15m equal highs"),
    ]
    selected = select_structural_target(
        side="LONG",
        entry=0.7425,
        stop_loss=0.7378,
        targets=targets,
        min_risk_reward=2.0,
        current_price=0.7500,
    )
    self.assertEqual(selected.price, 0.7521)

def test_rejects_targets_below_minimum_rr(self):
    selected = select_structural_target(
        side="LONG",
        entry=0.7425,
        stop_loss=0.7378,
        targets=[StructuralTarget(0.7480, "15m swing high")],
        min_risk_reward=2.0,
        current_price=0.7450,
    )
    self.assertIsNone(selected)

def test_rejects_liquidity_target_already_traded_through(self):
    selected = select_structural_target(
        side="LONG",
        entry=0.7425,
        stop_loss=0.7378,
        targets=[StructuralTarget(0.7521, "15m equal highs")],
        min_risk_reward=2.0,
        current_price=0.7645,
    )
    self.assertIsNone(selected)

def test_strength_high_requires_all_high_factors(self):
    strength, factors = classify_strength(
        self.high_zone,
        follows_htf_bias=True,
    )
    self.assertEqual(strength, "HIGH")
    self.assertIn("liquidity sweep", factors)

def test_fvg_only_strength_is_low(self):
    strength, factors = classify_strength(
        self.fvg_zone,
        follows_htf_bias=True,
    )
    self.assertEqual(strength, "LOW")
```

- [ ] **Step 2: Run trade-construction tests and verify RED**

Run the new `tests.test_smc` test classes. Expected: missing helper functions.

- [ ] **Step 3: Implement level and strength helpers**

Implement:

```python
from dataclasses import replace

from .models import (
    AnalysisSettings,
    Candle,
    POIZone,
    Signal,
    StructuralTarget,
)


def calculate_stop_loss(
    zone: POIZone,
    atr: float,
    buffer_multiplier: float,
) -> float:
    buffer = atr * buffer_multiplier
    if zone.side == "LONG":
        return min(zone.lower_bound, zone.swing_extreme) - buffer
    return max(zone.upper_bound, zone.swing_extreme) + buffer


def select_structural_target(
    *,
    side: str,
    entry: float,
    stop_loss: float,
    targets: list[StructuralTarget],
    min_risk_reward: float,
    current_price: float,
) -> StructuralTarget | None:
    risk = abs(entry - stop_loss)
    directional = [
        target
        for target in targets
        if (
            side == "LONG"
            and target.price > entry
            and target.price > current_price
        )
        or (
            side == "SHORT"
            and target.price < entry
            and target.price < current_price
        )
    ]
    directional.sort(key=lambda target: abs(target.price - entry))
    return next(
        (
            target
            for target in directional
            if abs(target.price - entry) / risk >= min_risk_reward
        ),
        None,
    )
```

Add:

```python
def find_structural_targets(
    candles: list[Candle],
    opposing_zones: list[POIZone],
    *,
    side: str,
    swing_window: int,
    equal_level_atr_tolerance: float,
    atr: float,
) -> list[StructuralTarget]:
    swing_prices = []
    for index in range(swing_window, len(candles) - swing_window):
        candle = candles[index]
        neighbors = (
            candles[index - swing_window : index]
            + candles[index + 1 : index + 1 + swing_window]
        )
        if side == "LONG" and candle.high > max(item.high for item in neighbors):
            swing_prices.append(candle.high)
        elif side == "SHORT" and candle.low < min(item.low for item in neighbors):
            swing_prices.append(candle.low)

    targets = [
        StructuralTarget(
            price=price,
            reason="15m swing high" if side == "LONG" else "15m swing low",
        )
        for price in swing_prices
    ]
    tolerance = atr * equal_level_atr_tolerance
    for first, second in zip(swing_prices, swing_prices[1:]):
        if abs(first - second) <= tolerance:
            targets.append(
                StructuralTarget(
                    price=(first + second) / 2,
                    reason=(
                        "15m equal highs"
                        if side == "LONG"
                        else "15m equal lows"
                    ),
                )
            )
    for zone in opposing_zones:
        targets.append(
            StructuralTarget(
                price=(
                    zone.lower_bound
                    if side == "LONG"
                    else zone.upper_bound
                ),
                reason=(
                    f"{zone.timeframe} opposing {zone.kind.lower()}"
                ),
            )
        )
    return targets


def has_ltf_choch(
    candles: list[Candle],
    zone: POIZone,
    swing_window: int,
) -> bool:
    touch_indexes = [
        index
        for index, candle in enumerate(candles)
        if candle.low <= zone.upper_bound and candle.high >= zone.lower_bound
    ]
    if not touch_indexes:
        return False
    touch = touch_indexes[-1]
    if touch < swing_window or touch + 1 >= len(candles):
        return False
    prior = candles[touch - swing_window : touch]
    after = candles[touch + 1 :]
    if zone.side == "LONG":
        structure = max(item.high for item in prior)
        return any(item.close > structure for item in after)
    structure = min(item.low for item in prior)
    return any(item.close < structure for item in after)


def classify_strength(
    zone: POIZone,
    follows_htf_bias: bool,
) -> tuple[str, tuple[str, ...]]:
    factors = []
    if zone.htf_structure_shift:
        factors.append("HTF CHoCH/MSB")
    if zone.liquidity_sweep:
        factors.append("liquidity sweep")
    if zone.first_test:
        factors.append("first test of HTF POI")
    if zone.ltf_choch:
        factors.append("LTF CHoCH inside HTF POI")
    if follows_htf_bias:
        factors.append("aligned with HTF bias")
    if (
        zone.htf_structure_shift
        and zone.liquidity_sweep
        and zone.first_test
        and follows_htf_bias
    ):
        return "HIGH", tuple(factors)
    if zone.ltf_choch and follows_htf_bias:
        return "MEDIUM", tuple(factors)
    if zone.kind == "FVG":
        factors.append("FVG-only confirmation")
    if not follows_htf_bias:
        factors.append("countertrend")
    return "LOW", tuple(factors)
```

Add these exact orchestration helpers:

```python
def detect_all_zones(
    candles: list[Candle],
    atr_values: list[float | None],
    *,
    timeframe: str,
    displacement_atr_multiplier: float,
    swing_window: int,
) -> list[POIZone]:
    order_blocks = detect_order_blocks(
        candles,
        atr_values,
        timeframe,
        displacement_atr_multiplier,
        swing_window,
    )
    mitigation_blocks = detect_mitigation_blocks(
        candles,
        order_blocks,
        atr_values,
        timeframe,
        displacement_atr_multiplier,
    )
    candidates = order_blocks + mitigation_blocks + detect_fvgs(
        candles,
        timeframe,
    )
    index_by_timestamp = {
        item.timestamp: index for index, item in enumerate(candles)
    }
    valid = []
    for zone in candidates:
        formed_index = index_by_timestamp[zone.formed_at]
        later = candles[formed_index + 1 :]
        if not is_zone_valid(zone, later):
            continue
        retest_candles = candles[formed_index + 2 :]
        first_test = not any(
            candle.low <= zone.upper_bound
            and candle.high >= zone.lower_bound
            for candle in retest_candles
        )
        valid.append(replace(zone, first_test=first_test))
    return valid


def build_candidate_signals(
    *,
    symbol: str,
    zones: list[POIZone],
    candles_15m: list[Candle],
    opposing_zones: list[POIZone],
    current_price: float,
    bias_4h: str,
    bias_1h: str,
    atr: float,
    settings: AnalysisSettings,
) -> list[Signal]:
    targets = find_structural_targets(
        candles_15m,
        opposing_zones,
        side=zones[0].side if zones else "LONG",
        swing_window=settings.swing_window,
        equal_level_atr_tolerance=settings.equal_level_atr_tolerance,
        atr=atr,
    )
    signals = []
    for zone in zones:
        zone = replace(
            zone,
            ltf_choch=has_ltf_choch(
                candles_15m,
                zone,
                settings.swing_window,
            ),
        )
        entry = zone.entry
        stop_loss = calculate_stop_loss(
            zone,
            atr,
            settings.stop_atr_buffer_multiplier,
        )
        target = select_structural_target(
            side=zone.side,
            entry=entry,
            stop_loss=stop_loss,
            targets=targets,
            min_risk_reward=settings.min_risk_reward,
            current_price=current_price,
        )
        if target is None:
            continue
        follows_bias = (
            zone.side == "LONG" and bias_4h == bias_1h == "BULLISH"
        ) or (
            zone.side == "SHORT" and bias_4h == bias_1h == "BEARISH"
        )
        strength, confluences = classify_strength(zone, follows_bias)
        if strength == "LOW" and not settings.allow_low_strength_signals:
            continue
        inside_zone = zone.lower_bound <= current_price <= zone.upper_bound
        signals.append(
            Signal.from_trade(
                symbol=symbol,
                bias_4h=bias_4h,
                bias_1h=bias_1h,
                current_price=current_price,
                zone=zone,
                order_type="CONDITIONAL" if inside_zone else "LIMIT",
                entry=entry,
                stop_loss=stop_loss,
                target=target,
                strength=strength,
                confluences=confluences,
                max_entry_distance_percent=(
                    settings.max_entry_distance_percent
                ),
            )
        )
    return signals


def rank_candidate_signals(signals: list[Signal]) -> list[Signal]:
    timeframe_rank = {"4H": 0, "1H": 1}
    kind_rank = {"ORDER_BLOCK": 0, "MITIGATION_BLOCK": 1, "FVG": 2}
    strength_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(
        signals,
        key=lambda signal: (
            0 if signal.first_test else 1,
            timeframe_rank[signal.poi_timeframe],
            kind_rank[signal.poi_kind],
            strength_rank[signal.strength],
            -signal.poi_formed_at,
            -signal.risk_reward,
        ),
    )
```

- [ ] **Step 4: Run trade-construction tests and verify GREEN**

Run all `tests.test_smc` tests. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add smart_money_bot/smc.py tests/test_smc.py
git commit -m "Build POI trade levels and strength"
```

### Task 5: End-To-End Signal Analysis

**Files:**
- Modify: `smart_money_bot/analysis.py`
- Modify: `tests/test_analysis.py`

- [ ] **Step 1: Replace old behavior tests with failing contract tests**

Use real candles for bias/ATR and patch only the already-tested POI detector and
target discovery boundaries:

```python
from unittest.mock import patch

from smart_money_bot.models import AnalysisSettings, Candle, POIZone, StructuralTarget


def make_trend(count, start, step):
    candles = []
    price = start
    for index in range(count):
        open_ = price
        close = price + step
        candles.append(
            Candle(
                timestamp=index,
                open=open_,
                high=max(open_, close) + abs(step),
                low=min(open_, close) - abs(step),
                close=close,
                volume=100,
            )
        )
        price = close
    return candles


def build_market(current_price):
    candles_15m = make_trend(40, 0.7500, 0.0001)
    last = candles_15m[-1]
    candles_15m[-1] = Candle(
        timestamp=last.timestamp,
        open=last.open,
        high=max(last.high, current_price),
        low=min(last.low, current_price),
        close=current_price,
        volume=last.volume,
    )
    return (
        candles_15m,
        make_trend(20, 0.7000, 0.0030),
        make_trend(20, 0.6500, 0.0050),
    )


def setUp(self):
    self.analysis_settings = AnalysisSettings()
    self.zone = POIZone(
        kind="ORDER_BLOCK",
        side="LONG",
        timeframe="1H",
        lower_bound=0.7390,
        upper_bound=0.7425,
        formed_at=100,
        swing_extreme=0.7390,
        liquidity_sweep=True,
        htf_structure_shift=True,
    )

def test_remote_poi_returns_limit_signal(self):
    candles_15m, candles_1h, candles_4h = build_market(0.7645)
    with patch(
        "smart_money_bot.analysis.detect_all_zones",
        side_effect=[[], [self.zone]],
    ), patch(
        "smart_money_bot.smc.find_structural_targets",
        return_value=[StructuralTarget(0.7800, "15m equal highs")],
    ):
        signal = analyze_market_data(
            "ENAUSDT",
            candles_15m,
            candles_1h,
            candles_4h,
            self.analysis_settings,
        )
    self.assertEqual(signal.order_type, "LIMIT")
    self.assertEqual(signal.entry, signal.poi_upper)
    self.assertNotEqual(signal.entry, signal.current_price)
    self.assertGreaterEqual(signal.risk_reward, 2.0)

def test_price_inside_poi_returns_conditional_signal(self):
    candles_15m, candles_1h, candles_4h = build_market(0.7410)
    with patch(
        "smart_money_bot.analysis.detect_all_zones",
        side_effect=[[], [self.zone]],
    ), patch(
        "smart_money_bot.smc.find_structural_targets",
        return_value=[StructuralTarget(0.7800, "15m equal highs")],
    ):
        signal = analyze_market_data(
            "ENAUSDT",
            candles_15m,
            candles_1h,
            candles_4h,
            self.analysis_settings,
        )
    self.assertEqual(signal.order_type, "CONDITIONAL")

def test_invalidated_poi_returns_none(self):
    candles_15m, candles_1h, candles_4h = build_market(0.7645)
    with patch(
        "smart_money_bot.analysis.detect_all_zones",
        side_effect=[[], []],
    ):
        signal = analyze_market_data(
            "ENAUSDT",
            candles_15m,
            candles_1h,
            candles_4h,
            self.analysis_settings,
        )
    self.assertIsNone(signal)

def test_no_structural_target_with_minimum_rr_returns_none(self):
    candles_15m, candles_1h, candles_4h = build_market(0.7645)
    with patch(
        "smart_money_bot.analysis.detect_all_zones",
        side_effect=[[], [self.zone]],
    ), patch(
        "smart_money_bot.smc.find_structural_targets",
        return_value=[StructuralTarget(0.7460, "15m swing high")],
    ):
        signal = analyze_market_data(
            "ENAUSDT",
            candles_15m,
            candles_1h,
            candles_4h,
            self.analysis_settings,
        )
    self.assertIsNone(signal)
```

- [ ] **Step 2: Run analysis tests and verify RED**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe' -m unittest tests.test_analysis -v
```

Expected: old signature/model does not satisfy new assertions.

- [ ] **Step 3: Implement analysis orchestration**

Import `AnalysisSettings` from `models.py`, keep `calculate_atr`, then
implement:

```python
def analyze_market_data(
    symbol: str,
    candles_15m: list[Candle],
    candles_1h: list[Candle],
    candles_4h: list[Candle],
    settings: AnalysisSettings | None = None,
) -> Signal | None:
    config = settings or AnalysisSettings()
    if len(candles_15m) < 40 or len(candles_1h) < 20 or len(candles_4h) < 20:
        return None
    bias_4h = determine_bias(candles_4h, lookback=20)
    bias_1h = determine_bias(candles_1h, lookback=12)
    if bias_4h != bias_1h:
        return None
    atr_15m = calculate_atr(candles_15m)[-1]
    if atr_15m is None or atr_15m <= 0:
        return None
    atr_4h = calculate_atr(candles_4h)
    atr_1h = calculate_atr(candles_1h)
    zones_4h = detect_all_zones(
        candles_4h,
        atr_4h,
        timeframe="4H",
        displacement_atr_multiplier=config.displacement_atr_multiplier,
        swing_window=config.swing_window,
    )
    zones_1h = detect_all_zones(
        candles_1h,
        atr_1h,
        timeframe="1H",
        displacement_atr_multiplier=config.displacement_atr_multiplier,
        swing_window=config.swing_window,
    )
    zones = zones_4h + zones_1h
    expected_side = "LONG" if bias_4h == "BULLISH" else "SHORT"
    current_price = candles_15m[-1].close
    signals = build_candidate_signals(
        symbol=symbol,
        zones=[zone for zone in zones if zone.side == expected_side],
        candles_15m=candles_15m,
        opposing_zones=[zone for zone in zones if zone.side != expected_side],
        current_price=current_price,
        bias_4h=bias_4h,
        bias_1h=bias_1h,
        atr=atr_15m,
        settings=config,
    )
    return rank_candidate_signals(signals)[0] if signals else None
```

Order type must be `CONDITIONAL` only while price is inside the zone; all
outside-zone signals are `LIMIT`. Reject low-strength signals when
`allow_low_strength_signals` is false.

The three orchestration helpers are implemented in `smc.py` during Task 4 and
are imported by `analysis.py`.

- [ ] **Step 4: Run analysis and SMC tests and verify GREEN**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe' -m unittest tests.test_analysis tests.test_smc -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add smart_money_bot/analysis.py tests/test_analysis.py
git commit -m "Generate POI-based SMC signals"
```

### Task 6: Professional Telegram Signal Format

**Files:**
- Modify: `smart_money_bot/formatting.py`
- Modify: `tests/test_formatting.py`

- [ ] **Step 1: Write failing formatting tests**

Construct a complete `Signal` and assert:

```python
message = format_signal(signal, now=fixed_time)
self.assertIn("SMC SIGNAL | <code>ENAUSDT</code>", message)
self.assertIn("Direction: <b>LONG</b>", message)
self.assertIn("Order type: <b>LIMIT</b>", message)
self.assertIn("Entry: <code>0.7425</code>", message)
self.assertIn("R:R: <b>1:2.04</b>", message)
self.assertIn("Strength: <b>HIGH</b>", message)
self.assertIn("Distance to Entry: <code>1.01%</code> (remote)", message)
self.assertIn("Status: Pending retest of POI", message)
self.assertNotRegex(message, r"[🟢🔴🔥✅⚠️🗑]")
self.assertNotIn("Входить по рынку", message)
```

Add a separate `CONDITIONAL` assertion for:

`Status: Awaiting LTF CHoCH confirmation inside POI`.

- [ ] **Step 2: Run formatting tests and verify RED**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe' -m unittest tests.test_formatting -v
```

Expected: old Russian market-price template and old Signal constructor fail.

- [ ] **Step 3: Implement dry structured formatter**

Delete `calculate_risk_reward`; the formatter reads the already validated
`signal.risk_reward`. Add a price formatter that preserves useful precision:

```python
def format_price(value: float) -> str:
    if value >= 1000:
        precision = 2
    elif value >= 1:
        precision = 4
    else:
        precision = 6
    return f"{value:.{precision}f}".rstrip("0").rstrip(".")
```

Render Direction, Order type, Current price, POI bounds/type/timeframe, Entry,
SL, TP, target reason, R:R, Strength, Confluence, Status, and UTC timestamp.

- [ ] **Step 4: Run formatting tests and verify GREEN**

Run the Task 6 test command. Expected: all pass with no emoji or hype copy.

- [ ] **Step 5: Commit**

```powershell
git add smart_money_bot/formatting.py tests/test_formatting.py
git commit -m "Format professional POI signals"
```

### Task 7: Scanner Integration And POI Cooldown

**Files:**
- Modify: `smart_money_bot/telegram_app.py`
- Create: `tests/test_telegram_app.py`

- [ ] **Step 1: Write failing cooldown test**

Build two signals with the same symbol/side but different `poi_formed_at`, then:

```python
bot.last_signals[first.cooldown_key] = datetime.now(timezone.utc)
self.assertTrue(bot._is_in_cooldown(first))
self.assertFalse(bot._is_in_cooldown(second))
```

Also assert `_scan_symbol` passes all SMC settings into
`analyze_market_data`.

- [ ] **Step 2: Run integration test and verify RED**

Run:

```powershell
$env:PYTHONPATH = "$PWD\.deps;$PWD"
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe' -m unittest tests.test_telegram_app -v
```

Expected: `_is_in_cooldown` still expects symbol and side.

- [ ] **Step 3: Implement scanner integration**

Call `self.settings.analysis_settings()` in `_scan_symbol`, pass the result to
the new analysis signature, and change:

```python
def _is_in_cooldown(self, signal: Signal) -> bool:
    last_sent_at = self.last_signals.get(signal.cooldown_key)
    if last_sent_at is None:
        return False
    cooldown = timedelta(minutes=self.settings.signal_cooldown_minutes)
    return datetime.now(timezone.utc) - last_sent_at < cooldown
```

After successful delivery:

```python
self.last_signals[signal.cooldown_key] = datetime.now(timezone.utc)
```

Keep per-symbol exception isolation and log the symbol plus analysis stage.

- [ ] **Step 4: Run integration test and verify GREEN**

Run the Task 7 command. Expected: all scanner integration tests pass.

- [ ] **Step 5: Commit**

```powershell
git add smart_money_bot/telegram_app.py tests/test_telegram_app.py
git commit -m "Deduplicate signals by POI"
```

### Task 8: Full Regression And Runtime Smoke Verification

**Files:**
- Modify only if verification exposes a defect in files already covered above.

- [ ] **Step 1: Run the complete unit suite**

```powershell
$env:PYTHONPATH = "$PWD\.deps;$PWD"
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe' -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Compile every Python module**

```powershell
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe' -m compileall -q smart_money_bot tests
```

Expected: exit code 0 and no syntax output.

- [ ] **Step 3: Run a deterministic formatted-signal smoke script**

Instantiate a known remote bullish POI fixture, call `analyze_market_data`, and
print `format_signal`. Verify the output contains:

```text
Order type: LIMIT
Entry:
Stop Loss:
Take Profit:
R:R: 1:
Strength:
Status: Pending retest of POI
```

Verify Entry equals the POI proximal boundary and differs from current price.

- [ ] **Step 4: Review the final diff**

```powershell
git diff --check
git status --short
git diff HEAD~7 -- smart_money_bot tests .env.example
```

Expected: no whitespace errors, only intended source/test/config changes, and
pre-existing `.gitignore` or `.dual-graph` changes remain untouched.

- [ ] **Step 5: Commit any verification-only correction**

Only when Step 1-4 required a source correction:

```powershell
git add smart_money_bot tests .env.example
git commit -m "Fix SMC signal regression"
```
