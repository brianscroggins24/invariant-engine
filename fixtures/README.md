# Milestone 1 fixtures

All fixtures in this directory are small, synthetic examples. They contain no
credentials, account information, wallets, signatures, or live trading data.
The files use the venue-native payload shapes below and are never sent to a
venue.

The fixture payloads were checked against these official documentation pages on
2026-07-25:

- Polymarket order-book snapshots and `price_change` messages:
  https://docs.polymarket.com/market-data/websocket/market-channel
- Polymarket market-channel event overview:
  https://docs.polymarket.com/market-data/websocket/overview
- Kalshi `orderbook_snapshot` and `orderbook_delta` messages:
  https://docs.kalshi.com/websockets/orderbook-updates
- Kalshi order-book price conventions:
  https://docs.kalshi.com/getting_started/order_direction

The supported local delta shapes are limited to the documented fields used in
the fixture files. WebSocket connections and authentication are deliberately
not implemented.

Parser context is explicit and is not inferred from payload values:

- Polymarket fixtures use `polymarket-direct-v1` as the raw-envelope schema
  version.
- Kalshi fixtures use `kalshi-orderbook-v1` as the raw-envelope schema version.
- `orderbook_snapshot.json` and `orderbook_delta.json` use
  `outcome_leg` price context.
- `orderbook_snapshot_unified_yes.json` and
  `orderbook_delta_unified_yes.json` use `unified_yes_leg` price context.

The two Kalshi price contexts are capture metadata supplied to the parser or
replay function; they are intentionally absent from the individual venue
payloads.
