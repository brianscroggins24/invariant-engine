# Agent instructions

- `PLAN.md` defines the current approved roadmap.
- Work only within the active milestone.
- The current milestone is read-only and fixture-driven.
- Preserve venue-native semantics.
- Preserve raw provenance.
- Use `Decimal` for financial values.
- Never fabricate missing fields.
- Relationship candidates are not validated relationships.
- Validated relationships are not executable opportunities.
- Opportunity candidates are non-actionable.
- No LLM may authorize trades or bypass deterministic validation.
- No live connections, authentication, secrets, wallets, signing, orders, routing, positions, capital allocation, paper trading, risk engine, or reconciliation are allowed in Milestone 1.
- Future execution code must remain behind a deterministic risk gateway.
- Do not create future milestone packages prematurely.
- Stop and report missing evidence rather than inventing venue behavior.
- Tests must verify determinism, provenance, precision, and venue separation.
- Scope expansion requires an updated approved plan.

The active work is Milestone 1: the local replayable market foundation. It is fixture-driven and read-only; it is not authorization to implement later-stage execution or live-system behavior.
