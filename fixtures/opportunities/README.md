# Synthetic opportunity-economics fixtures

`cases.json` is a versioned `opportunity-fixtures-v2` document containing
three complete, ordered, synthetic cases: a Polymarket complement, a
Polymarket exhaustive set, and a Kalshi exclusive-and-exhaustive partition.
Each case contains its propositions, bindings, states, venue-native snapshots,
fee-policy assignments, ordered provenance, quantity, and exact expected
economics.

These fixtures are synthetic, versioned, local test data. They are
non-authoritative and do not describe current Polymarket or Kalshi fee
schedules or complete market capacity. Depth is only deterministic
counterfactual input for the Milestone 3 tests.

The fee policies use the explicit declarative schema implemented by the
opportunities package, including explicit interval boundaries, formula
parameters, scopes, rounding, currency, and quantum. Their provenance
references are synthetic fixture lineage and are retained in order.
