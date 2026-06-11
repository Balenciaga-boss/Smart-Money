# SMC POI Signal Engine Design

## Objective

Replace the current market-price-based alert logic with a deterministic signal
engine whose Entry, Stop Loss, Take Profit, risk-to-reward, order type, and
strength are derived from a validated point of interest and market structure.

The first release supports bullish and bearish Order Blocks, Mitigation Blocks,
and Fair Value Gaps through one zone representation and validation pipeline.

## Current Root Cause

`analyze_market_data` currently selects a direction from the last 15-minute
candle, calculates Stop Loss and Take Profit as ATR multiples around
`current_price`, and stores `recent_low` or `recent_high` as a display-only POI.
The formatter then calculates R:R from `current_price`. Consequently, the
published setup describes a market entry even when the displayed POI is far
away, and the strength label is mostly hardcoded.

## Architecture

The analysis layer will be split into deterministic stages:

1. Build higher-timeframe bias and structure context from 4H and 1H candles.
2. Detect candidate POI zones on 4H and 1H.
3. Reject invalidated, malformed, or directionally incompatible zones.
4. Select the best candidate using recency, timeframe priority, zone type, and
   confluence.
5. Derive Entry and Stop Loss from the selected zone.
6. Discover structural liquidity targets and select the nearest target with
   R:R at or above the configured minimum.
7. Classify order type from the current-price distance to Entry.
8. Calculate signal strength from explicit confluence flags.
9. Return a complete immutable `Signal`, or `None` if any mandatory stage fails.

No downstream component may recalculate trade levels from the current price.

## Domain Models

### POIZone

- `kind`: `ORDER_BLOCK`, `FVG`, or `MITIGATION_BLOCK`
- `side`: `LONG` or `SHORT`
- `timeframe`: `4H` or `1H`
- `lower_bound`
- `upper_bound`
- `formed_at`
- `swing_extreme`
- `liquidity_sweep`
- `htf_structure_shift`
- `ltf_choch`

The zone constructor must reject non-positive prices and
`lower_bound >= upper_bound`.

### Signal

The existing model will be expanded with:

- `order_type`: `LIMIT` or `CONDITIONAL`
- `entry`
- `poi_lower`
- `poi_upper`
- `poi_kind`
- `poi_timeframe`
- `risk_reward`
- `strength`: `HIGH`, `MEDIUM`, or `LOW`
- `confluences`: immutable tuple of machine-defined factor labels
- `invalidation_level`
- `target_reason`

`current_price` remains informational and must not influence R:R.

## POI Detection

### Bullish Order Block

Find the last bearish candle before bullish displacement that:

- closes above the recent local swing high or structure level;
- has a displacement body at least the configured ATR multiple;
- leaves the candidate zone unviolated after formation.

The zone spans the candle low to its open. The swing extreme is the minimum of
the order-block low and the local swing low that formed the displacement.

### Bearish Order Block

Find the last bullish candle before bearish displacement that:

- closes below the recent local swing low or structure level;
- has a displacement body at least the configured ATR multiple;
- leaves the candidate zone unviolated after formation.

The zone spans the candle open to its high. The swing extreme is the maximum of
the order-block high and the local swing high that formed the displacement.

### Fair Value Gap

For three consecutive candles:

- bullish FVG: first candle high is below third candle low;
- bearish FVG: first candle low is above third candle high.

The gap boundaries form the zone. An FVG without a liquidity sweep or structure
shift may produce only `LOW` strength and remains subject to all R:R and
invalidation filters.

### Mitigation Block

A Mitigation Block is formed from the last opposing candle before displacement
when price has already returned to mitigate the originating Order Block without
closing through its distal boundary, then resumes in the displacement
direction with a confirmed structure break.

- bullish: zone spans the mitigation candle low to its open;
- bearish: zone spans the mitigation candle open to its high;
- the original Order Block and the mitigation candle must share direction;
- the resumed displacement must satisfy the configured ATR threshold;
- a close through the distal boundary invalidates both related zones.

Mitigation Blocks use the same Entry, Stop Loss, target, R:R, strength, and
deduplication rules as other POI types.

### Zone Invalidation

A bullish POI is invalid after a completed candle closes below its lower bound.
A bearish POI is invalid after a completed candle closes above its upper bound.
Intrabar wicks do not invalidate a zone but may count as a liquidity sweep.

## Entry And Order Type

Entry is always the proximal POI boundary:

- LONG: `entry = poi.upper_bound`
- SHORT: `entry = poi.lower_bound`

The distance percentage is:

`abs(current_price - entry) / entry * 100`

Order classification:

- If current price is outside the zone, return `LIMIT`, regardless of whether
  distance is above or below the configured threshold.
- If current price is inside the zone and distance to Entry is at most the
  configured threshold, return `CONDITIONAL`; execution requires LTF CHoCH.
- Never publish a market-order instruction.

The `MAX_ENTRY_DISTANCE_PERCENT` setting defaults to `0.5`. It controls whether
the message describes the POI as remote, but a remote setup is still sent
immediately as a Limit order, as required.

## Stop Loss

Use a configurable ATR buffer:

`buffer = ATR(15m) * STOP_ATR_BUFFER_MULTIPLIER`

Default multiplier: `0.15`.

- LONG:
  `stop_loss = min(poi.lower_bound, poi.swing_extreme) - buffer`
- SHORT:
  `stop_loss = max(poi.upper_bound, poi.swing_extreme) + buffer`

Reject a setup unless:

- LONG: `stop_loss < entry`
- SHORT: `stop_loss > entry`
- absolute risk is positive and finite.

The same level is exposed as `invalidation_level`.

## Structural Take Profit

Candidate targets are extracted from completed candles after the POI lookback:

- confirmed swing highs for LONG and swing lows for SHORT;
- equal highs or equal lows within an ATR-relative tolerance;
- the proximal boundary of an opposing POI.

Only targets beyond Entry in the trade direction are considered. Candidates
are sorted by distance from Entry. Select the nearest candidate satisfying:

`abs(target - entry) / abs(entry - stop_loss) >= MIN_RISK_REWARD`

`MIN_RISK_REWARD` defaults to `2.0`.

If no structural target satisfies the minimum R:R, return `None`. The engine
must not synthesize a mathematical ATR-multiple TP as a fallback.

## Signal Strength

Strength is derived from named factors:

### HIGH

All conditions are required:

- HTF structure shift (`MSB` or `CHoCH`);
- liquidity sweep before displacement;
- selected POI is on 4H or 1H and remains valid;
- current price is testing the zone or the setup is waiting for its first test.

### MEDIUM

- selected valid HTF POI;
- LTF CHoCH occurs inside that POI;
- setup follows the HTF directional bias.

### LOW

Any otherwise valid setup that lacks the complete HIGH or MEDIUM combination,
including FVG-only confirmation or a countertrend setup.

Countertrend setups and FVG-only setups remain configurable. The initial public
release will reject countertrend setups and permit FVG-only setups as `LOW`.

The formatter displays the exact factor labels used in the classification.

## Candidate Selection

Valid candidates are ranked deterministically:

1. aligned with 4H and 1H bias;
2. untested zone before partially mitigated zone;
3. 4H before 1H;
4. Order Block before Mitigation Block before FVG;
5. HIGH before MEDIUM before LOW;
6. most recently formed zone.

If two candidates are otherwise equal, choose the one with higher R:R.

## Configuration

Add environment-backed settings:

- `MAX_ENTRY_DISTANCE_PERCENT=0.5`
- `MIN_RISK_REWARD=2.0`
- `STOP_ATR_BUFFER_MULTIPLIER=0.15`
- `DISPLACEMENT_ATR_MULTIPLIER=1.5`
- `SWING_WINDOW=3`
- `EQUAL_LEVEL_ATR_TOLERANCE=0.1`
- `ALLOW_LOW_STRENGTH_SIGNALS=true`

Numeric settings must be finite and positive. Invalid configuration must fail
at startup with a precise setting name in the error message.

## Telegram Message

The public message contains no emojis, hype, or market-entry language:

```text
SMC SIGNAL | ENAUSDT

Direction: LONG
Order type: LIMIT
Current price: 0.7645
POI: 1H ORDER_BLOCK [0.7400 - 0.7425]
Entry: 0.7425
Stop Loss: 0.7378
Take Profit: 0.7521
Target: 15m equal highs
R:R: 1:2.04
Strength: HIGH
Confluence: HTF CHoCH; liquidity sweep; first test of HTF POI

Status: Pending retest of POI
```

For `CONDITIONAL`, status states that execution requires LTF CHoCH inside the
zone. Prices use a symbol-sensitive precision helper rather than a fixed four
decimal places.

## Cooldown And Deduplication

Cooldown identity becomes:

`symbol + side + poi_kind + poi_timeframe + formed_at`

This prevents repeated publication of the same pending setup while allowing a
new POI on the same symbol and side to be published immediately.

The first release keeps cooldown state in memory, matching the existing bot.
Persistent delivery state is outside this change.

## Failure Handling

Return `None` without sending when:

- candle history is insufficient;
- 4H and 1H bias conflict;
- no valid aligned POI exists;
- the POI is invalidated;
- Entry or Stop Loss is malformed;
- no structural target reaches minimum R:R;
- any computed value is non-finite.

Per-symbol exceptions remain isolated by the Telegram scanner. Error logging
must name the symbol and analysis stage without exposing API credentials.

## Testing Strategy

Tests will be written before production changes and must demonstrate:

- Entry equals the proximal POI boundary, not current price;
- a remote POI produces a `LIMIT` signal immediately;
- price inside the POI produces `CONDITIONAL`;
- invalidated POIs produce no signal;
- SL is beyond the distal boundary or swing plus ATR buffer;
- TP is selected from a structural target;
- signals below configured minimum R:R are rejected;
- R:R uses Entry rather than current price;
- HIGH, MEDIUM, and LOW classifications follow their factor contracts;
- formatter contains the required professional fields and no emoji;
- cooldown distinguishes separate POIs on the same symbol and side;
- invalid numeric configuration fails at startup.

Existing tests that encode market-price Entry and fixed `1:1.78` behavior will
be replaced with contract-based assertions.

## Non-goals

- Automatic order placement on Bybit.
- Position sizing or account-risk calculation.
- Persistent signal lifecycle storage.
- Backtesting profitability or making performance claims.
- Machine-learning or probabilistic signal scoring.
