# Product

## Register

product

## Users

External traders who receive SMC and ICT trade setups through a public or
commercial Telegram channel. They need precise pending-order levels that can be
placed on an exchange before price returns to a validated point of interest.

## Product Purpose

The bot scans Bybit futures markets and publishes deterministic SMC trade
setups. A valid setup must derive Entry, Stop Loss, Take Profit, risk-to-reward,
and signal strength from market structure and a detected POI rather than from
the current market price.

Success means users receive concise, reproducible Limit or conditional setups
with explicit invalidation, structural targets, and auditable confluence
factors. The bot must suppress setups whose POI, risk, or target is invalid.

## Brand Personality

Professional, concise, and rigorous. The product communicates like a trading
system report: factual, restrained, and explicit about conditions.

## Anti-references

No emojis, exclamation marks, hype, urgency tactics, profit promises, vague
confidence claims, or unexplained labels such as a hardcoded signal strength.
Messages must not imply a market entry when the planned entry is at a POI.

## Design Principles

1. Derive every trade level from observable market structure.
2. Prefer no signal over a weak or internally inconsistent setup.
3. Make every classification auditable through explicit confluence factors.
4. Separate the current market state from the planned order parameters.
5. Keep public messages compact without hiding invalidation or execution rules.

## Accessibility & Inclusion

Use plain structured text that remains understandable without color or icons.
Do not encode direction, strength, or order state through decoration alone.
Keep labels consistent and use unambiguous numeric formatting.
