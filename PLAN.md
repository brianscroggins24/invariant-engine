# Invariant Engine Plan

## Product objective

Build an automated prediction-market system whose primary objective is relationship-based arbitrage. The eventual system should:

1. Discover related propositions.
2. Validate implication, equivalence, complement, exclusivity, subset, exhaustive, and partition relationships.
3. Compile validated relationships into deterministic price constraints.
4. Detect quote violations.
5. Evaluate depth, fees, latency, fill risk, and multi-leg exposure.
6. Historically validate strategies.
7. Simulate execution.
8. Eventually trade only through deterministic risk controls.

The eventual system must support both intra-venue and cross-venue relationships involving Polymarket and Kalshi. Analytics, replay, provenance, and monitoring are supporting capabilities for that trustworthy path. The current work is fully read-only, local, fixture-driven, and diagnostic.

## Central system thesis

The trust and analytical lifecycle is ordered:

`relationship candidate` → `relationship certificate draft` → `explicit semantic review` → `deterministic truth/payoff validation` → `validated relationship certificate` → `deterministic pricing constraint` → `non-actionable constraint evaluation` → later economic and execution analysis

The following distinctions are mandatory:

- A relationship candidate is not a validated relationship.
- A validated relationship is not a constraint violation.
- A constraint violation is not an opportunity.
- An opportunity is not an authorized trade.
- No LLM may authorize trades or bypass deterministic validation.

No earlier object may impersonate a later one. The current and planned Milestone 2 outputs remain non-actionable.

## Governing architecture principles

- Candidate discovery is separate from semantic review and deterministic relationship validation.
- Relationship validation is separate from price-constraint compilation and quote evaluation.
- Diagnostic findings are separate from execution authorization.
- Polymarket and Kalshi retain venue-native models and identifiers.
- Cross-venue relationships connect venue-native claims without erasing their differences.
- Quoted or midpoint prices are not executable prices.
- Depth, fees, latency, slippage, fill probability, and residual exposure are evaluated separately.
- Multi-leg strategy execution must not be assumed atomic.
- Raw provenance is preserved on important domain objects and references are ordered and traceable.
- Missing and uncertain data remain explicit, as do unsupported and unavailable states; missing venue behavior is never fabricated.
- Financial and payout values use `Decimal`-based arithmetic.
- Serialization and deterministic validation must be stable across repeated runs.
- Mutable venue behavior is time-scoped.
- Risk controls remain independent of strategies and models.
- Any future execution code must remain behind an independent deterministic risk gateway.
- No LLM may validate a relationship by itself, create a certificate, compile a constraint, create an opportunity, authorize a trade, or bypass deterministic checks.

## Target architecture

The eventual pipeline is:

1. Venue data adapters.
2. Raw event journal and provenance.
3. Venue-native market models.
4. Deterministic snapshot/delta state engine.
5. Proposition and relationship graph.
6. Relationship validation and certification.
7. Deterministic constraint compiler.
8. Quote-violation detector.
9. Depth, fee, latency, and fill-risk analysis.
10. Diagnostic opportunity candidates.
11. Historical replay and strategy validation.
12. Execution simulation.
13. Deterministic risk and authorization gateway.
14. Venue execution gateways.
15. Fill, position, fee, exposure, and PnL reconciliation.
16. Operational monitoring and kill switches.

The current approved work ends before live ingestion, economic opportunity analysis, simulation, risk authorization, and execution.

## Milestone 0 — Governance and architecture — completed

The governance documents and approved architecture roadmap were established in Milestone 0. Later work remains subject to the active milestone, explicit scope gates, provenance requirements, venue-native semantics, deterministic validation, and no-execution boundaries in this plan.

## Accepted foundation: Milestone 1

### Milestone 1 — Replayable market foundation — completed and accepted

Milestone 1 delivered and accepted the local replayable market foundation. Its accepted capabilities are:

- immutable raw envelopes and raw provenance;
- venue-aware typed identifiers;
- `Decimal`-based financial values;
- venue-native Polymarket and Kalshi order books;
- explicit schema versions;
- explicit Kalshi price conventions;
- neutral Kalshi native sides;
- deterministic snapshot/delta replay;
- strict and audit replay validity;
- ordered raw-reference lineage;
- stable serialization;
- synthetic fixtures;
- determinism, precision, provenance, venue-separation, and no-network tests.

Milestone 1 is not live market ingestion. Its foundation must not regress while later milestones are developed.

The venue-native semantics remain explicit:

- Polymarket preserves markets, conditions, outcome tokens, directly published bid/ask ladders, snapshots, incremental changes, off-chain matching, on-chain settlement, oracle resolution, token redemption, and mutable venue behavior.
- Kalshi preserves the series → event → market hierarchy, venue-local tickers, binary and scalar market types, fixed-point prices and quantities, YES and NO books, complementary derived asks, snapshots, deltas, sequence metadata, lifecycle states, exchange-managed settlement, and explicit price conventions. Kalshi contracts are not collapsed into Polymarket token models.

## Opportunity lifecycle

The Milestone 2 trust pipeline is the detailed beginning of the longer analytical and execution lifecycle:

`discovered` → `relationship pending` → `relationship validated` → `constraint violated` → `economics validated` → `historically supported` → `simulation supported` → `risk authorized` → `submitted` → `reconciled`

`rejected` may be reached from any applicable non-terminal analytical state. Milestone 2 remains read-only; no candidate, draft, certificate, constraint evaluation, or other diagnostic output may enter `risk authorized`, `submitted`, or another execution state.

## Domain model direction

The long-term domain model should include:

- `RawEnvelope`;
- typed venue and entity identifiers;
- `Venue`;
- venue-native market references;
- venue-native contract and token references;
- `OrderBookSnapshot`;
- `PriceLevel`;
- `BookSide`;
- `Proposition`;
- relationship candidates and certificates;
- `ConstraintEvaluation`;
- `OpportunityCandidate` as a later analytical finding;
- provenance references such as `raw_ref`;
- warning and uncertainty fields;
- replay-oriented stable serialization.

An `OpportunityCandidate` is non-actionable and is not a proposed order. It must not contain executable order instructions, routing, time-in-force, live sizing, or capital allocation.

## Provenance plan

Preserve the following for captured, normalized, and derived data:

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
- uncertain relationships;
- sequence gaps;
- unavailable venue fields;
- uncertain identity, including account or wallet identity where such historical data exists.

Milestone 2 additionally preserves provenance for proposition evidence, venue-claim bindings, candidate generation, semantic review, truth/payoff states, certificate validation, future LLM prompt/model/input/output records, and the compiled constraints and evaluations planned for 2.3. Provenance must retain enough raw and ordered references to distinguish supplied evidence, review, deterministic validation, and later diagnostic derivation.

Never fabricate missing data.

## Venue-native modeling

### Polymarket

Preserve:

- events and markets;
- conditions;
- outcome tokens;
- directly published bids and asks;
- CLOB snapshots and incremental changes;
- off-chain matching;
- on-chain settlement;
- oracle-based resolution;
- token redemption;
- mutable fees and limits.

Do not generalize individual matched-trade settlement or atomicity to multi-leg strategies.

### Kalshi

Preserve:

- series → event → market hierarchy;
- venue-local tickers and market identity;
- binary and scalar market types;
- fixed-point prices and quantities;
- native YES and NO sides;
- explicit price conventions;
- convention-aware interpreted ladders;
- snapshots, deltas, and sequence/session metadata;
- distinct lifecycle states;
- exchange-managed settlement;
- mutable fees, migrations, routing, and limits.

Do not collapse Kalshi contracts into Polymarket's token model. Milestone 2.1 supports only binary unit-payout claim bindings, even though the long-term venue model preserves the existence of scalar markets.

## Recommended implementation direction

The system should remain a modular Python application using:

- a currently supported Python version;
- explicit typed immutable domain objects;
- `decimal.Decimal`;
- standard-library serialization where practical;
- pytest for tests;
- a conventional `pyproject.toml`;
- Ruff for formatting and linting;
- strict type checking.

Start as a modular monolith rather than microservices. The full future package map is recorded below, but package creation remains governed by the active milestone and subphase gates.

## Milestone 2 — Relationship trust and diagnostic constraint foundation

Milestone 2 remains fully read-only and fixture-driven. It establishes a deterministic relationship trust pipeline and, in later subphases, diagnostic pricing constraints. It does not authorize actions.

### Milestone 2 trust pipeline

The ordered trust boundary is:

```text
RelationshipCandidate
    → RelationshipCertificateDraft
    → explicit semantic review
    → deterministic truth/payoff validation
    → RelationshipCertificate
    → deterministic pricing constraint
    → non-actionable ConstraintEvaluation
```

An LLM may produce only untrusted candidates and drafts. It may never produce
or mark a validated certificate directly. In completed 2.1, candidate
discovery was manual/synthetic only. Active 2.2 discovery is limited to
recorded, provider-neutral outputs behind the same deterministic trust
boundary.

### Milestone 2.1 — Deterministic relationship foundation — completed and accepted

This completed implementation subphase delivered:

1. Typed relationship-domain identifiers.
2. Proposition models representing truth-bearing statements independently of venue instruments.
3. Venue-native claim bindings connecting propositions to exact Polymarket market and outcome-token references, and to exact Kalshi market identity and native YES or NO side.
4. `RelationshipCandidate` as an explicitly untrusted hypothesis.
5. `RelationshipCertificateDraft` containing:
   - participating propositions;
   - exact venue claim bindings;
   - proposed relationship type;
   - supporting market-rule evidence;
   - event scope;
   - thresholds and units;
   - observation period;
   - close and resolution times;
   - resolution sources;
   - cancellation, void, and refund behavior;
   - payout structure;
   - edge cases;
   - assumptions;
   - uncertainties;
   - evidence provenance;
   - validation method;
   - explicit semantic-review attestation;
   - declared state-space completeness.
6. Explicit feasible truth and payoff states.
7. Deterministic validation for implication, equivalence, complement, subset/superset, mutually exclusive sets, exhaustive sets, and exclusive-and-exhaustive partitions.
8. `RelationshipCertificate` as the successful result of validation, never as a user-assigned status flag.
9. Deterministic serialization and tests.

Milestone 2.1 supports only binary unit-payout claims. A complete feasible-state model must be supplied explicitly. The deterministic validator verifies the supplied model's structure, payout consistency, and claimed relationship; it does not claim to understand or prove external natural-language market rules by itself.

Synthetic fixtures must be clearly marked synthetic. Their review attestations must not pretend to represent production authority. Conditional relationships and scalar markets must be represented as unsupported/deferred rather than approximated.

2.1 must not create the constraint compiler, quote evaluator, LLM pipeline, opportunity models, or later-stage packages.

#### Milestone 2.1 acceptance criteria

- Candidates cannot be compiled or treated as certificates.
- Certificate drafts cannot assign themselves validated status.
- Incomplete state spaces fail closed.
- Missing semantic review fails closed.
- Each supported relationship validates against explicit truth states.
- Invalid truth states reject the relationship.
- Payout inconsistencies reject certification.
- Cancellation, void, and refund states participate when present.
- Scalar and conditional inputs are rejected as unsupported.
- Venue-native claim identity is preserved.
- Cross-venue drafts retain each venue's distinct references and provenance.
- All financial and payout values use `Decimal`.
- Serialization is deterministic.
- Validation is deterministic.
- No network or later-milestone behavior exists.
- Tests cover provenance, precision, type-state boundaries, venue separation, and repeated-run determinism.

#### Milestone 2.1 acceptance record

Milestone 2.1 was accepted on 2026-08-09 at implementation commit `fdf6f5e`.
The accepted baseline is:

- 104 pytest tests passed;
- Ruff check passed;
- Ruff format check passed for 40 files;
- strict mypy passed for 29 source files;
- Python 3.11 compilation passed;
- `git diff --check` passed;
- independent trust-boundary and provenance review passed;
- Milestone 1 did not regress;
- no prohibited or later-milestone package was created.

This acceptance records the delivered deterministic relationship foundation;
its trust boundaries, provenance rules, and type-state distinctions remain
mandatory for all later discovery work.

### Milestone 2.2 — LLM-assisted relationship discovery — active

This is the only active implementation subphase. It adds an optional,
untrusted semantic-discovery source after the deterministic 2.1 trust boundary
exists. The initial implementation remains local, read-only, deterministic
outside the recorded model boundary, fixture-driven, network-free,
provider-neutral, replaceable, and disableable. It consumes recorded model
inputs and outputs and requires no secrets, live model credentials, live LLM
API, embedding service, external network, or provider SDK dependency.

The discovery layer's allowed software output shapes are still explicitly
untrusted domain objects. “Trusted outputs” here means only that these shapes
are permitted at the software boundary; it does not mean validated semantic
truth. Allowed shapes include:

- `RelationshipCandidate`;
- `RelationshipCertificateDraft`;
- proposition proposals;
- venue-claim-binding proposals;
- proposed relationship types;
- bounded evidence spans from supplied market rules;
- assumptions;
- uncertainties;
- edge cases;
- abstention reasons;
- rejection reasons;
- malformed-output records;
- prompt, model, parameter, input, output, and source provenance.

The provider-neutral boundary must consume recorded fixture responses. It must
not call a live LLM, live embedding model, or external network.

Plan for:

- deterministic topic, entity, date, threshold, and unit prefilters;
- optional similarity metadata from recorded fixtures;
- strict structured-output parsing;
- explicit input and output schema versions;
- proposition proposals;
- venue-claim-binding proposals;
- proposed relationship types;
- evidence-span extraction only from supplied market-rule text;
- assumptions, uncertainties, edge cases, abstention, and rejection reasons;
- bounded attempts and malformed-output rejection;
- deterministic retry exhaustion;
- no repair that invents missing semantic content;
- recorded model inputs and responses for deterministic tests;
- stable serialization and ordered provenance;
- a labeled evaluation fixture set;
- precision, recall, false-positive, abstention, malformed-output, consistency, reviewer-acceptance, cost, and latency measurements.

An LLM or discovery provider in 2.2 may never:

- validate its own candidate;
- perform semantic-review attestation;
- declare state-space completeness;
- invent missing market rules;
- silently resolve conflicting rules;
- create a `RelationshipCertificate` directly;
- call or bypass deterministic certification;
- compile a pricing constraint;
- evaluate quotes;
- create an opportunity, order, or execution instruction;
- authorize a trade.

All candidates and drafts remain explicitly untrusted even when their
structured output parses successfully. The discovery component must be
replaceable and disableable without affecting deterministic certificates or
constraints.

Recorded-output tests must cover valid proposals, malformed JSON or equivalent
malformed structure, missing required fields, unsupported schema versions,
unknown relationship types, conditional and scalar proposals, ambiguous
wording, conflicting evidence, abstention, duplicate proposals, deterministic
retry exhaustion, provenance preservation, cross-venue identity preservation,
repeated-run determinism, no-network behavior, and inability to construct
certificates.

Evaluation planning may measure precision, recall, false-positive rate,
abstention rate, malformed-output rate, repeated-run consistency, reviewer
acceptance, cost metadata, and latency metadata. No minimum precision,
acceptable reviewer workload, cost target, or latency target is approved yet.

### Milestone 2.3 — Constraint compilation and diagnostic evaluation — planned, not active

2.3 plans a `Decimal`-based linear pricing-constraint model compiled only from validated `RelationshipCertificate` objects.

Supported theoretical constraints for binary unit-payout claims are:

- Complement: `P(A) + P(B) = 1`.
- Implication: `P(A) - P(B) <= 0`.
- Equivalence: `P(A) - P(B) = 0`.
- Subset: `P(A) - P(B) <= 0`.
- Mutually exclusive set: `sum(P(A_i)) <= 1`.
- Exhaustive set: `sum(P(A_i)) >= 1`.
- Exclusive-and-exhaustive partition: `sum(P(A_i)) = 1`.

The compiler must verify each generated constraint against every certified payoff state rather than trusting only the relationship label.

Quote observations are planned as intervals `[best bid, best ask]`; midpoint is not the implementation authority. Polymarket observations use directly published bid and ask ladders. Kalshi observations use the convention-aware interpreted ladders created in Milestone 1.

Planned evaluation statuses are `SATISFIED`, `VIOLATED`, `INDETERMINATE`, and `UNAVAILABLE`.

`VIOLATED` means only that no price vector inside the observed intervals satisfies the certified relationship. It is not an opportunity, profit estimate, order plan, or execution authorization.

Evaluation must fail closed for invalid replay state, missing required book sides, missing provenance, unknown payout mappings, incompatible claim bindings, unsupported relationship types, unsupported scalar payouts, and unavailable temporal synchronization. Initial fixtures should use exactly synchronized observations; real timestamp-skew policy remains deferred.

## Milestone 2 package boundaries

The expected future structure may resemble:

```text
src/invariant_engine/domain/
src/invariant_engine/provenance/
src/invariant_engine/venues/polymarket/
src/invariant_engine/venues/kalshi/
src/invariant_engine/relationships/
    ids.py
    propositions.py
    claims.py
    candidates.py
    evidence.py
    states.py
    certificates.py
    validation.py

src/invariant_engine/discovery/

src/invariant_engine/constraints/
    models.py
    compiler.py
    observations.py
    evaluator.py

src/invariant_engine/replay/
src/invariant_engine/diagnostics/
src/invariant_engine/simulation/
src/invariant_engine/risk/
src/invariant_engine/execution/
src/invariant_engine/reconciliation/

fixtures/
fixtures/relationships/
tests/
tests/relationships/
tests/constraints/
```

During active 2.2, only packages required by bounded recorded-response
discovery may be created. The accepted 2.1 relationship foundation must not
regress. `constraints/` must not be created until 2.3. Quote evaluation,
opportunity models, diagnostics unrelated to bounded discovery evaluation,
simulation, risk, execution, reconciliation, and other future-milestone
packages remain prohibited. No live provider or model integration is allowed.

## Milestone 2 non-goals

All of Milestone 2 prohibits:

- live venue connections;
- authenticated venue APIs;
- live LLM calls or live embedding calls in the initial 2.2 implementation;
- secrets;
- wallets;
- signing;
- orders;
- cancellations;
- routing;
- order sizing;
- executable-size calculation;
- fee-adjusted profit;
- depth consumption;
- live positions;
- capital allocation;
- paper trading;
- portfolio/risk engine;
- execution simulation;
- fill reconciliation;
- legal or compliance determinations;
- LLM-authorized relationships, constraints, opportunities, or trades.

Also deferred are general natural-language proof, general SAT or integer-programming solvers, marginal-polytope projection, conditional-relationship compilation, scalar-market constraints, opportunity candidates, and historical opportunity economics.

Milestone 3 remains responsible for historical depth, executable prices, fees, counterfactual supported size, gross and net edge, and residual multi-leg exposure.

## Later milestone roadmap

### Milestone 3 — Historical opportunity economics

Implement later:

- historical depth analysis;
- executable-price calculations;
- fee treatment;
- counterfactual supported size;
- gross and net edge;
- residual multi-leg exposure;
- incomplete-data rejection.

All outputs remain diagnostic.

### Milestone 4 — Strategy validation

Measure opportunity frequency, persistence, depth, fee-adjusted edge, latency sensitivity, fill assumptions, false relationships, capital usage, drawdowns, and data-quality failures.

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

## Open evidence questions

Do not invent answers to these questions:

- How can natural-language relationship meaning eventually be validated beyond explicit review?
- How should state-space completeness be established for real market rules?
- How should conflicting or changing resolution rules invalidate certificates?
- How should certificate versions respond to amended venue rules?
- What labeled benchmark should evaluate LLM-assisted discovery?
- What precision and reviewer-load thresholds should govern whether LLM discovery is useful?
- How should conditional relationships be represented?
- How should scalar payouts be represented?
- How should asynchronous cross-venue observations be evaluated safely?
- How should websocket gap recovery work?
- What are the complete fill-history semantics?
- What are the current venue schemas and fee schedules?
- What are the relevant latency distributions?
- How should queue position and fill probability be determined?
- What are the economics of partial fills?
- How do cross-venue settlement processes differ?
- What capital-transfer constraints apply?
- What constitutes economic finality and cash availability?

## First implementation task

The next implementation task is explicitly bounded to active Milestone 2.2
only:

- provider-neutral recorded-response interface;
- versioned discovery input and output schemas;
- deterministic topic, entity, date, threshold, and unit prefilters;
- strict structured-output parser;
- candidate and draft proposal mapping;
- abstention and rejection handling;
- prompt/model/parameter/input/output provenance;
- recorded synthetic fixtures;
- evaluation fixture labels and metrics;
- tests.

This task must remain local, read-only, deterministic outside the recorded
model boundary, fixture-driven, provider-neutral, replaceable, disableable,
and network-free. It explicitly excludes live providers, live embeddings,
certificate creation, changes to deterministic validation, Milestone 2.3, all
later work, the constraint compiler, quotes, opportunities, execution
instructions, and any live-system behavior.
