# Invariant Engine Plan

## Product objective

Build an automated prediction-market trading system that discovers logically or economically inconsistent prices, validates the underlying market relationships, determines whether opportunities remain profitable after depth, fees, latency, fill risk, and multi-leg exposure, and eventually executes viable opportunities behind deterministic risk controls.

Analytics, replay, provenance, and monitoring are supporting capabilities. They exist to create a trustworthy path toward profitable automated relationship-based arbitrage.

The eventual system must support both intra-venue opportunities and cross-venue opportunities between Polymarket and Kalshi. The current stage is fully read-only; diagnostic candidates are non-actionable.

## Central system thesis

The primary strategy is relationship-based arbitrage:

1. Identify related propositions.
2. Validate their logical and economic relationships.
3. Compile validated relationships into deterministic pricing constraints.
4. Detect violations using market data.
5. Evaluate executable prices and depth.
6. Account for fees, latency, fill risk, and multi-leg exposure.
7. Calculate supported size and expected net edge.
8. Historically validate the strategy.
9. Simulate execution.
10. Eventually execute qualified opportunities through deterministic risk controls.
11. Reconcile fills, positions, fees, exposure, and PnL.

## Governing architecture principles

- Candidate relationship discovery is separate from relationship validation.
- Relationship validation is separate from price-violation detection.
- Diagnostic opportunities are separate from execution authorization.
- Polymarket and Kalshi require venue-native models.
- Cross-venue relationships connect venue-native contracts without erasing their differences.
- A quoted or midpoint price is not an executable price.
- Depth, fees, latency, slippage, fill probability, and residual exposure are evaluated separately.
- Multi-leg strategy execution must not be assumed atomic.
- Missing and uncertain data remain explicit.
- Money, prices, probabilities, quantities, and fees use `Decimal`-based arithmetic.
- Important domain objects retain raw provenance.
- Mutable venue behavior is time-scoped.
- Risk controls are independent of strategies and models.
- No LLM may validate a relationship by itself, authorize a trade, size a live position, or bypass risk controls.

## Target architecture

The eventual pipeline is:

1. Venue data adapters.
2. Raw event journal and provenance.
3. Venue-native market models.
4. Deterministic snapshot/delta state engine.
5. Proposition and relationship graph.
6. Relationship validation and certification.
7. Deterministic constraint compiler.
8. Price-violation detector.
9. Depth, fee, latency, and fill-risk analysis.
10. Diagnostic opportunity candidates.
11. Historical replay and strategy validation.
12. Execution simulation.
13. Deterministic risk and authorization gateway.
14. Venue execution gateways.
15. Fill, position, fee, exposure, and PnL reconciliation.
16. Operational monitoring and kill switches.

## Relationship model

The relationship model will support:

- implication;
- equivalence;
- complement;
- mutual exclusivity;
- subset/superset;
- exhaustive outcome sets;
- exclusive and exhaustive partitions;
- conditional relationships.

The corresponding coherent-price constraints are:

- Complement: `P(A) + P(not A) = 1`.
- Implication: if `A → B`, then `P(A) ≤ P(B)`.
- Equivalence: if `A ↔ B`, then `P(A) = P(B)`.
- Subset: if `A ⊆ B`, then `P(A) ≤ P(B)`.
- Mutually exclusive set: `ΣP(Aᵢ) ≤ 1`.
- Exhaustive set: `ΣP(Aᵢ) ≥ 1`.
- Exclusive and exhaustive partition: `ΣP(Aᵢ) = 1`.

These are theoretical coherence constraints. Executable arbitrage must be evaluated from actual bid/ask ladders, depth, fees, and payout states.

## Relationship validation

A relationship must not be accepted merely because market titles appear similar.

Each relationship certificate should preserve:

- participating propositions;
- venue-native market and contract references;
- relationship type;
- validation status;
- supporting market rules;
- event scope;
- thresholds and units;
- observation period;
- closing and resolution times;
- resolution source;
- cancellation and void rules;
- payout structure;
- edge cases;
- assumptions;
- uncertainties;
- validation method;
- raw provenance references.

An LLM may eventually propose candidate relationships or extract possible terms. Deterministic checks or explicit review must validate them.

## Opportunity lifecycle

Use explicit states resembling:

`discovered` → `relationship pending` → `relationship validated` → `constraint violated` → `economics validated` → `historically supported` → `simulation supported` → `risk authorized` → `submitted` → `reconciled`

`rejected` may be reached from any applicable non-terminal analytical state.

The current read-only stage must not permit candidates to enter `risk authorized`, `submitted`, or other execution states.

## Domain model direction

Plan these initial objects:

- `RawEnvelope`;
- typed venue and entity IDs;
- `Venue`;
- venue-native market references;
- venue-native contract/token references;
- `OrderBookSnapshot`;
- `PriceLevel`;
- `BookSide`;
- `Proposition`;
- `MarketRelationship`;
- `RelationshipCertificate`;
- `ConstraintEvaluation`;
- `OpportunityCandidate`;
- provenance references such as `raw_ref`;
- warning and uncertainty fields;
- replay-oriented serialization.

`OpportunityCandidate` is an analytical finding, not a proposed order. It must not contain executable order instructions, routing, time-in-force, live sizing, or capital allocation.

## Provenance plan

Preserve the following for captured and normalized data:

- original payload;
- venue;
- endpoint or channel;
- capture timestamp;
- retrieval timestamp;
- fixture identity;
- payload hash;
- schema/version metadata;
- normalization warnings;
- references from normalized objects to raw envelopes.

Warnings should cover:

- missing provenance;
- stale snapshot;
- incomplete depth;
- missing or estimated fees;
- derived values;
- ambiguous lifecycle;
- detector assumptions;
- uncertain relationship;
- sequence gap;
- unavailable venue field;
- uncertain account or wallet identity.

Never fabricate missing venue data.

## Venue-native modeling

### Polymarket

Preserve:

- events and markets;
- conditions;
- YES/NO outcome tokens;
- directly published bids and asks;
- CLOB snapshots and incremental changes;
- offchain matching;
- onchain settlement;
- oracle-based resolution;
- token redemption;
- mutable fees and rate limits.

Do not generalize individual matched-trade atomicity to multi-leg strategies.

### Kalshi

Preserve:

- series → event → market hierarchy;
- venue-local tickers;
- binary and scalar market types;
- fixed-point prices and quantities;
- YES and NO bid books;
- complementary derived asks;
- snapshots, deltas, and sequence metadata;
- determined, disputed, amended, and finalized states;
- exchange-managed settlement;
- mutable fees, fee rounding, historical routing, and rate limits.

Do not collapse Kalshi contracts into Polymarket’s token model.

## Recommended implementation direction

The initial system should be a modular Python application using:

- a currently supported Python version;
- explicit typed domain objects;
- `decimal.Decimal`;
- standard-library serialization where practical;
- pytest for tests;
- a conventional `pyproject.toml` when implementation begins;
- a formatter/linter such as Ruff.

Start as a modular monolith, not microservices.

Future structure is expected to be similar to:

```text
src/invariant_engine/domain/
src/invariant_engine/provenance/
src/invariant_engine/venues/polymarket/
src/invariant_engine/venues/kalshi/
src/invariant_engine/relationships/
src/invariant_engine/constraints/
src/invariant_engine/replay/
src/invariant_engine/diagnostics/
src/invariant_engine/simulation/
src/invariant_engine/risk/
src/invariant_engine/execution/
src/invariant_engine/reconciliation/
fixtures/
tests/
```

The `simulation`, `risk`, `execution`, and `reconciliation` packages are future architecture only. Do not create or implement them now.

## Milestone roadmap

### Milestone 0 — Governance and architecture

Create `PLAN.md` and `AGENTS.md`.

### Milestone 1 — Replayable market foundation

Implement later:

- raw envelopes;
- typed IDs;
- Decimal policy;
- venue-native fixture models;
- order-book snapshots and updates;
- deterministic replay;
- provenance;
- warnings;
- stable serialization;
- tests for determinism and venue separation.

### Milestone 2 — Relationship and constraint engine

Implement later:

- propositions;
- relationship candidates;
- relationship certificates;
- payoff-state validation;
- deterministic pricing constraints;
- non-actionable constraint violations.

### Milestone 3 — Historical opportunity economics

Implement later:

- historical depth analysis;
- executable-price calculations;
- fee treatment;
- counterfactual supported size;
- gross and net edge;
- multi-leg residual exposure;
- incomplete-data rejection.

All outputs remain diagnostic.

### Milestone 4 — Strategy validation

Measure:

- opportunity frequency;
- persistence;
- depth;
- fee-adjusted edge;
- latency sensitivity;
- fill assumptions;
- false relationships;
- capital usage;
- drawdowns;
- data-quality failures.

### Milestone 5 — Live read-only scanner

Add public venue data ingestion without authentication, orders, wallets, or trading.

### Milestone 6 — Execution simulation

Model latency, queue assumptions, partial fills, failed legs, cancellations, and residual exposure without sending orders.

### Milestone 7 — Deterministic risk gateway

Add independent limits, stale-data rejection, minimum-edge requirements, exposure controls, strategy enablement, and kill switches.

### Milestone 8 — Restricted venue-local execution

Enable one venue and one validated strategy class with tightly limited capital through the risk gateway.

### Milestone 9 — Cross-venue execution

Add cross-venue execution only after venue-local execution and reconciliation are reliable.

## Current-stage non-goals

The current stage explicitly prohibits:

- live venue connections;
- authenticated APIs;
- secrets;
- wallets;
- signing;
- order submission;
- cancellation;
- routing;
- live sizing;
- live positions;
- capital allocation;
- paper trading;
- portfolio/risk-engine implementation;
- fill reconciliation;
- legal or compliance determinations;
- LLM-authorized trades.

## Open evidence questions

Do not invent answers to these questions:

- How can natural-language proposition relationships be validated deterministically?
- How should websocket gap recovery work?
- What are the complete fill-history semantics?
- What are the current venue schemas and fee schedules?
- What are the relevant latency distributions?
- How should queue position and fill probability be determined?
- What are the economics of partial fills?
- How do cross-venue settlement processes differ?
- What capital-transfer constraints apply?
- How should scalar-market settlement be represented?
- What constitutes economic finality and cash availability?

## First implementation milestone

The next coding task is bounded to Milestone 1: implement only the local, replayable market foundation and its tests. That work may cover raw envelopes, typed IDs, the Decimal policy, venue-native fixture models, order-book snapshots and updates, deterministic replay, provenance, warnings, stable serialization, and determinism/venue-separation tests. It must remain fixture-driven and read-only; it must not add live connections, authentication, trading, execution, risk authorization, or any later-milestone package.

