# Milestone 2.1 relationship fixtures

These fixtures are deliberately small, local, and synthetic. They are not
production market rules, current venue authority, or semantic approval from
Polymarket or Kalshi. The fixture schema is `relationship-fixture-v1`.

`relationships.json` records the supported relationship declarations and the
negative cases exercised by `tests/relationships/`. The tests construct typed
objects from these declarations and attach explicit synthetic evidence and
raw references. No fixture is sent to a venue or a model provider.

Venue provenance remains distinct: Polymarket examples use a market and
outcome-token reference; Kalshi examples use a market ticker/ID and native
YES or NO side. Cross-venue examples retain both ordered raw-reference and
evidence lineages.
