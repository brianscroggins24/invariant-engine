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

The eventual system must support both intra-venue and cross-venue relationships involving Polymarket and Kalshi. Analytics, replay, provenance, and monitoring are supporting capabilities for that trustworthy path. The accepted Milestone 3 and Milestone 4 deliveries are fully local, historical, read-only, fixture-driven, deterministic, network-free, diagnostic, and non-actionable. Milestones 1–5 are accepted and closed. Capture v2 was independently accepted, its required engine-based US operational trial succeeded, and its documentation closure is recorded at `40edb4eae7538a6a4ea0f964d5312cf37650624d`. Its implementation and operational authority are deactivated. The bounded Milestone 6 synthetic execution scenarios slice was independently accepted and commit-verified at `ac9c512ebcd96d2ce11a9c7bb93a2097fb74e61b`. Its implementation authority is deactivated. Its verified documentation closure is the baseline for the final Milestone 6 activation draft, offline delay and queue comparison. Milestone 6 remains open with implementation inactive.

## Central system thesis

The trust and analytical lifecycle is ordered:

```text
RelationshipCandidate
    → RelationshipCertificateDraft
    → explicit semantic review
    → deterministic truth/payoff validation
    → RelationshipCertificate
    → deterministic pricing constraint
    → non-actionable ConstraintEvaluation
    → historical opportunity economics
    → non-actionable OpportunityCandidate
    → historical strategy validation
    → non-actionable historical validation result
    → later execution simulation
    → later deterministic risk authorization
```

The following distinctions are mandatory:

- A relationship candidate is not a validated relationship.
- A validated relationship is not a constraint violation.
- A constraint violation is not an opportunity.
- An `OpportunityCandidate` is not historically supported, executable, an order, a recommendation, or an authorization.
- The accepted Milestone 4 historical strategy-validation result remains explicitly non-actionable.
- Historical validation is not proof of future profitability, executability, capital suitability, or authorization.
- No LLM may authorize trades or bypass deterministic validation.

No earlier object may impersonate a later one. Milestone 2, Milestone 3, and Milestone 4 outputs remain non-actionable. The accepted Milestone 6 synthetic scenario evaluator is independent of this pipeline. Its results confer no `simulation supported` status or other trust promotion.

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
- No LLM or discovery provider may validate a relationship by itself, create a certificate, compile or evaluate a constraint, create an opportunity, authorize a trade, or bypass deterministic checks. Only the deterministic Milestone 3 evaluator may produce a non-actionable `OpportunityCandidate` after all required trust checks pass.

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

The accepted Milestone 3 work includes bounded historical opportunity economics for one synchronized historical constraint violation at a time and ends before aggregate strategy validation, live ingestion, execution simulation, risk authorization, and execution. That description records the accepted boundary and does not authorize further implementation.

The accepted Milestone 4 delivery begins at historical strategy validation over a complete, explicitly defined observation schedule and ends with a non-actionable historical validation result. This historical boundary grants no continuing implementation authority and does not activate live ingestion, execution simulation, risk authorization, execution, or Milestone 5 and later work.

## Milestone 0 — Governance and architecture — completed

The governance documents and approved architecture roadmap were established in Milestone 0. Later work remains subject to a future explicit governance transition, explicit scope gates, provenance requirements, venue-native semantics, deterministic validation, and no-execution boundaries in this plan.

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

`rejected` may be reached from any applicable non-terminal analytical state. Completed Milestone 2 and Milestone 3 remain read-only; no candidate, draft, certificate, constraint evaluation, opportunity evaluation, or `OpportunityCandidate` may enter `historically supported` merely because one or more candidates exist. The completed Milestone 4 may produce only an explicitly non-actionable historical validation result. Any later trusted historical-support artifact must require every caller-specified acceptance criterion to pass and retain process-local trust protections equivalent to the accepted candidate boundaries. No Milestone 4 output may enter `simulation supported`, `risk authorized`, `submitted`, or another execution state.

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
- `OpportunityEconomicsEvaluation` and non-actionable `OpportunityCandidate` as bounded Milestone 3 analytical findings;
- an immutable, versioned strategy-validation specification and explicitly non-actionable historical strategy-validation result;
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

Start as a modular monolith rather than microservices. The Milestone 5 capture package is a historical accepted delivery and grants no continuing path exception. Any implementation change or other package creation requires another explicit governance transition.

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
discovery was manual/synthetic only. Completed 2.2 discovery is limited to
recorded, provider-neutral outputs behind the same deterministic trust
boundary, and those limits remain permanent.

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

### Milestone 2.2 — LLM-assisted relationship discovery — completed and accepted

Milestone 2.2 was completed and accepted on 2026-08-09 at implementation
commit `d7a6dc5aec6a7fb9c24400a269aae4231bbf8572`.

The accepted delivery provides:

- optional, local, read-only, fixture-driven discovery;
- a provider-neutral recorded-response boundary;
- immutable, versioned input and output schemas;
- strict UTF-8 JSON parsing;
- duplicate-key rejection at every depth;
- rejection of non-standard constants and invalid framing whitespace;
- rejection of unpaired Unicode surrogates;
- deterministic topic, entity, date, threshold, and unit prefilters;
- optional non-authoritative recorded similarity metadata;
- untrusted candidate and certificate-draft proposal mapping;
- evidence spans closed exactly against supplied participating rule text;
- exact ordered request, rule, attempt, candidate, draft, binding, evidence, and completeness provenance;
- bounded attempts and deterministic retry exhaustion;
- explicit abstention, rejection, malformed-attempt, and duplicate records;
- preservation of cross-venue Polymarket and Kalshi identities;
- stable serialization;
- labeled synthetic evaluation fixtures and deterministic metrics;
- disableable discovery;
- no network access or provider SDK dependencies;
- no validator invocation, certificate construction, semantic-review attestation, or completeness attestation.

The discovery boundaries above are permanent. Successful parsing remains
untrusted and does not establish semantic truth, review, certification,
state-space completeness, a constraint, an opportunity, or authorization.
Discovery may not certify, attest semantic review or completeness, compile
constraints, or evaluate quotes.

#### Milestone 2.2 acceptance record

The accepted validation baseline was:

- 149 pytest tests passed;
- 105 Milestone 1 and 2.1 regression tests passed;
- Ruff check passed;
- Ruff formatting passed for 50 files;
- strict mypy passed for 37 source files;
- Python 3.11 compilation passed;
- `git diff --check` passed;
- independent parser, provenance, cross-venue identity, certificate-boundary, determinism, and no-network review passed;
- Milestones 1 and 2.1 did not regress;
- no prohibited later-milestone package was added.

The synthetic fixture measurements are recorded separately from acceptance
criteria:

- TP / FP / FN / TN: `4 / 8 / 1 / 24`;
- precision: `0.3333333333333333333333333333`;
- recall: `0.8`;
- false-positive rate: `0.25`;
- abstention rate: `0.05128205128205128205128205128`;
- malformed-output rate: `0.6052631578947368421052631579`;
- repeated-run consistency: `1`;
- reviewer acceptance: `0.3076923076923076923076923077`;
- one recorded cost observation: total/mean `0.0125 USD`;
- one recorded latency observation: total/mean `125 ms`.

These are synthetic, non-authoritative measurements. They are not a
production benchmark, acceptance threshold, provider decision, cost target,
or latency target.

### Milestone 2.3 — Constraint compilation and diagnostic evaluation — completed and accepted

Milestone 2.3 was completed and accepted on 2026-08-15 at implementation commit
`2bdcd2dc6124f8e794ac6e5252f90e3bbb57e22c`. Its bounded purpose was local,
read-only, fixture-driven, deterministic, and network-free
constraint compilation and diagnostic evaluation. The accepted delivery contains only:

- deterministic `Decimal`-based pricing-constraint models;
- compilation only from validator-produced `RelationshipCertificate` objects;
- deterministic verification of every compiled constraint against every certified feasible payoff state;
- venue-native, provenance-bearing quote-interval observations;
- non-actionable constraint evaluation;
- local, read-only, fixture-driven, network-free tests.

The lifecycle remains:

```text
RelationshipCandidate
    → RelationshipCertificateDraft
    → explicit semantic review
    → deterministic truth/payoff validation
    → RelationshipCertificate
    → deterministic pricing constraint
    → non-actionable ConstraintEvaluation
    → later opportunity economics
    → later deterministic risk authorization
```

Only validator-produced `RelationshipCertificate` objects may be compiled.
The compiler must reject candidates, drafts, invalid objects, unsupported
certificate types, and certificates that cannot be represented without
assumptions.

#### Supported binary unit-payout constraints

Using ordered propositions A and B, the approved constraints are:

- Complement: `P(A) + P(B) = 1`;
- Implication: `P(A) - P(B) <= 0`;
- Equivalence: `P(A) - P(B) = 0`;
- Subset: `P(A) - P(B) <= 0`;
- Superset: `P(A) - P(B) >= 0`;
- Mutually exclusive set: `sum(P(A_i)) <= 1`;
- Exhaustive set: `sum(P(A_i)) >= 1`;
- Exclusive-and-exhaustive partition: `sum(P(A_i)) = 1`.

The superset direction matches the accepted Milestone 2.1 ordering: for
`SUPERSET(A, B)`, B implies A.

Do not add conditional relationships, scalar payouts, generalized solvers,
integer programming, or marginal-polytope projection.

#### Constraint verification

The eventual compiler must verify generated coefficients, relation, and bound
against every payoff vector in the certified feasible-state set. It must not
trust the relationship label alone.

This verification does not establish natural-language truth or real-world
state-space completeness. Those remain responsibilities of explicit review
and deterministic certification upstream.

#### Quote observations

Retain interval observations `[best bid, best ask]`. Midpoint is not
authoritative. Polymarket uses directly published venue-native bid and ask
ladders. Kalshi uses the accepted convention-aware unified-YES interpretation
derived from native YES/NO books. Observation provenance and timestamps must
remain ordered and explicit.

Milestone 2.3 v1 requires every participating observation to represent exactly
the same timestamp instant, whether observations are intra-venue or
cross-venue. No timestamp tolerance or freshness duration is approved. Unequal
timestamps produce `UNAVAILABLE`. Explicit replay invalidity or staleness also
produces `UNAVAILABLE`; no staleness threshold may be invented. Initial
cross-venue fixtures must therefore be exactly synchronized. Asynchronous
cross-venue safety policy remains deferred and must not be invented.

#### Evaluation statuses

Retain `SATISFIED`, `VIOLATED`, `INDETERMINATE`, and `UNAVAILABLE`.

- `SATISFIED` means every price vector in the Cartesian product of the closed quote intervals satisfies the compiled certified constraint.
- `VIOLATED` means no price vector in that interval product satisfies the compiled certified constraint.
- `INDETERMINATE` means the interval product contains both satisfying and violating price vectors.
- `UNAVAILABLE` means inputs are missing, invalid, unsupported, stale, unsynchronized, or otherwise cannot be evaluated.
- `VIOLATED` is not an arbitrage opportunity, profit estimate, executable price, order plan, or authorization.
- Missing quote sides are `UNAVAILABLE`, not `INDETERMINATE`.

#### Fail-closed cases

The implementation must fail closed for:

- non-certificate input;
- missing or inconsistent certificate provenance;
- unsupported relationship type;
- unsupported conditional or scalar claims;
- coefficient or payoff-state verification failure;
- incompatible or duplicate claim bindings;
- missing required quote sides, which produce `UNAVAILABLE`;
- crossed or otherwise invalid intervals;
- invalid replay state, which produces `UNAVAILABLE`;
- missing quote provenance;
- unknown payout mapping;
- stale or unsynchronized observations, which produce `UNAVAILABLE`;
- unavailable temporal synchronization.

Exactly synchronized synthetic fixtures are permitted. No general
timestamp-skew tolerance or freshness duration may be invented.

#### Milestone 2.3 acceptance record

The accepted validation baseline was:

- 215 full pytest tests passed;
- 66 constraint tests passed;
- 149 non-constraint regression tests passed;
- Ruff check and format passed;
- strict mypy passed for 42 source files;
- Python compilation and `git diff --check` passed;
- no prohibited dependencies or later-stage behavior was introduced.

Independent probes additionally verified:

- recomputed IDs cannot restore trust after mutation;
- nested mutations fail closed;
- malformed trusted content fails closed;
- copied, deep-copied, pickled, or reconstructed objects are untrusted;
- 512 released constraints and observations self-prune from their weak registries.

The Milestone 2.3 trust boundaries are permanent regression requirements:
only validator-produced `RelationshipCertificate` objects may be compiled;
discovery remains untrusted and cannot certify, attest review or completeness,
compile constraints, evaluate quotes, create opportunities, or authorize
action; trusted compiler and observation producer boundaries remain enforced;
constraint evaluation remains non-actionable; venue-native semantics, exact
ordered provenance, `Decimal` precision, stable serialization, explicit schema
versions, deterministic behavior, and fail-closed handling remain mandatory.
Missing evidence, unsupported semantics, invalid objects, unavailable
observations, and inconsistent state must produce explicit unavailable,
indeterminate, or failure results rather than invented behavior.

## Package boundaries

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

The following package list records the packages delivered during Milestone 2.3
implementation. It is historical and does not authorize further changes to
those packages:

- `src/invariant_engine/constraints/`;
- `tests/constraints/`;
- narrowly necessary synthetic constraint fixtures.

The following paths record the accepted Milestone 3 delivery:

- `src/invariant_engine/opportunities/`;
- `tests/opportunities/`;
- `fixtures/opportunities/`.

The corresponding narrow recognition change in
`tests/relationships/test_relationships.py` is also part of the historical
delivery. These delivered paths and that former exception do not confer
current implementation authority. Milestone 3 remediation or changes within
those paths require a future explicit governance transition.

The following paths record the accepted Milestone 4 delivery:

- `src/invariant_engine/diagnostics/`;
- `tests/diagnostics/`;
- `fixtures/diagnostics/`.

The corresponding diagnostics-recognition change in
`tests/relationships/test_relationships.py` is also part of the historical
Milestone 4 delivery. At delivery the test still prohibited simulation, risk,
execution, and reconciliation packages. These delivered paths and that former
exception confer no current implementation authority or continuing path
exception. Milestone 4 remediation or changes within those paths require a
future explicit governance transition.

The accepted Milestones 1, 2.1, 2.2, 2.3, 3, 4, and 5 foundations and
permanent regression guarantees must not regress. No unrelated package or
later-milestone package is authorized. The exact Milestone 5 read-only capture
connection and narrow caller-owned Kalshi signing adapter described below are
historical delivered behavior and confer no continuing implementation
authority. The accepted synthetic simulation slice below also confers no
continuing implementation authority. Model connections, risk, execution,
reconciliation, wallets, private-key handling, orders, venue cancellation,
routing, and other live provider integration remain prohibited.

## Milestone 2 non-goals

All of Milestone 2 prohibits:

- live venue connections;
- authenticated venue APIs;
- live LLM calls or live embedding calls in the accepted 2.2 discovery implementation;
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

Milestone 3 subsequently delivered the bounded historical depth,
executable-price, fee, counterfactual-quantity, gross- and net-edge, and
residual-exposure work recorded below. This is historical scope documentation,
not continuing implementation authority.

## Milestone 3 — Historical opportunity economics — completed and accepted

Milestone 3 was independently reviewed and accepted on 2026-08-16 at
implementation commit `ecab60460ca0139beea4e289d0511af3e80aa1a9`.
The accepted implementation has parent
`489b5453f0c5b0e325d4cf70638090db299947d6`, tree
`161461d075e93ae8b4ba649b3c7050700abd8cc6`, and content-manifest SHA-256
`847e68a13d66ca20e144daca582ec6992eada2323778de0b60c79ed7a909a6fb`.
Milestone 3 implementation authority remains deactivated. Milestone 4 and
Milestone 5 are also completed and accepted. At the time of Milestone 3
closure, no implementation milestone was active and Milestone 5 and every
later milestone were inactive; their later governance transitions do not
alter this historical acceptance record.

Its purpose is deterministic evaluation of the economics of one synchronized
historical constraint violation at a time. All work remains local, historical,
read-only, fixture-driven, deterministic, network-free, and non-actionable.

The ordered trust lifecycle is:

```text
RelationshipCandidate
    → RelationshipCertificateDraft
    → explicit semantic review
    → deterministic truth/payoff validation
    → RelationshipCertificate
    → deterministic pricing constraint
    → non-actionable ConstraintEvaluation
    → historical opportunity economics
    → non-actionable OpportunityCandidate
    → historical strategy validation
    → non-actionable historical validation result
    → later execution simulation
    → later deterministic risk authorization
```

A constraint violation is not an opportunity. An `OpportunityCandidate` is
not historically supported, executable, an order, a recommendation, or an
authorization. The accepted Milestone 4 historical strategy-validation result
also remains explicitly non-actionable.

Economics evaluation must begin with all of the following:

- a validator-produced `RelationshipCertificate`;
- its corresponding trusted compiler-produced constraint;
- exact venue-native historical snapshots;
- an explicit positive counterfactual quantity;
- an immutable, versioned, time-scoped fee policy with complete semantics and
  ordered provenance.

A supplied `ConstraintEvaluation` is not sufficient authority. The economics
evaluator must independently:

1. validate certificate integrity;
2. reconstruct the expected constraint;
3. verify exact constraint identity and material content;
4. construct fresh trusted observations from the supplied snapshots;
5. rerun the accepted Milestone 2.3 evaluator;
6. continue only for a genuine `VIOLATED` result.

`SATISFIED`, `INDETERMINATE`, `UNAVAILABLE`, malformed, or untrusted upstream
inputs must never produce a candidate.

Only the following buy-only underpricing portfolios may produce candidates:

- complement below its equality bound;
- exhaustive set below its lower bound;
- exclusive-and-exhaustive partition below its equality bound.

The evaluator must return a structured `UNSUPPORTED_TRADE_DIRECTION` result
for implication violations, equivalence violations, subset or superset
violations, mutually-exclusive overpricing, above-bound partition violations,
mixed buy/sell portfolios, and any behavior requiring selling, shorting,
inventory, collateral, borrowing, or complement conversion.

For the caller-supplied positive quantity, the evaluator must:

- canonically validate both native sides of every supplied order book in full;
- consume ordered asks deterministically;
- use direct Polymarket asks;
- derive Kalshi asks through the accepted venue-native YES/NO conventions;
- retain venue-native identifiers;
- use exact `Decimal` arithmetic;
- calculate required quantity, ordered depth slices, cost, and VWAP for every
  required leg;
- require complete observed depth for every leg;
- preserve ordered provenance;
- retain exact Milestone 2.3 timestamp synchronization.

Supplied depth must not be described as complete market capacity. Maximum
observed capacity may be reported only as a diagnostic fact. Milestone 3 does
not optimize size or recommend capital. Missing, malformed, crossed, stale,
unsynchronized, replay-invalid, or insufficient data must fail closed.

Fee behavior must be explicit immutable data, not executable callbacks,
current configuration, or inferred venue defaults. A fee policy must specify
at least:

- venue;
- policy/version ID;
- effective interval;
- role or side;
- formula parameters;
- calculation scope;
- rounding scope;
- currency;
- rounding quantum;
- ordered provenance.

The implementation must not infer current venue fees, hardcode mutable
category, market, series, or event configuration, silently assume zero fees,
apply a policy outside its effective interval, or invent missing rounding or
fill-grouping semantics. Incomplete or unsupported policies must fail closed.
The evaluation reports gross edge, fees or defensible fee bounds, and a
net-edge interval. A candidate may exist only when worst-case net edge is
strictly positive.

Residual-exposure evaluation is limited to deterministic single-leg
complete-failure stress: all other required buy legs fill, one required leg
receives zero fill, and payoff and PnL ranges are calculated across every
certified feasible payoff state. This milestone does not authorize fill
probability, queue position, latency models, partial-fill simulation,
cancellation behavior, multi-failure simulation, or order sequencing.

`OpportunityEconomicsEvaluation` statuses include:

- `VALIDATED`;
- `NO_NET_EDGE`;
- `INSUFFICIENT_DEPTH`;
- `UNSUPPORTED_TRADE_DIRECTION`;
- `UNAVAILABLE`.

Only `VALIDATED` may produce an `OpportunityCandidate`. An
`OpportunityCandidate` must be evaluator-produced, bind every material input
and result, have deterministic identity, ordering, and serialization, preserve
ordered provenance, fail trust validation after material mutation, and state
explicitly that it is non-actionable. Process-local trust must not transfer
through copy, reconstruction, pickle, or JSON, and runtime trust state must
remain outside stable serialization.

The accepted Milestone 3 boundary permanently excludes:

- live ingestion;
- network calls;
- authentication or credentials;
- wallets or signing;
- orders, routes, submissions, or cancellations;
- risk authorization;
- capital allocation;
- recommended sizing;
- aggregate opportunity frequency or persistence statistics;
- portfolio performance or drawdown analysis;
- fill probability;
- queue models;
- latency simulation;
- execution simulation;
- partial-fill economics;
- current fee discovery;
- new relationship-discovery behavior;
- changes to certificate, relationship, constraint, or Milestone 2.3
  evaluation semantics.

The accepted Milestone 3 implementation and all future regression checks must
preserve:

- genuine certificates and compiler-produced constraints;
- independent reconstruction of Milestone 2.3 evaluation;
- genuine supported relationship construction;
- all three supported buy-only classes;
- multi-level depth walking;
- direct Polymarket and derived Kalshi asks;
- exact `Decimal` calculations;
- insufficient-depth rejection;
- unsupported-direction rejection;
- malformed, stale, crossed, unsynchronized, replay-invalid, and unavailable
  data rejection;
- fee-policy completeness, provenance, rounding, and temporal validation;
- gross-positive but worst-case-net-nonpositive rejection;
- single-leg failure across every certified payoff state;
- deterministic IDs, serialization, ordering, and hash-seed behavior;
- mutation, copy, reconstruction, pickle, JSON, and malformed-object probes;
- no candidate from `SATISFIED`, `INDETERMINATE`, or `UNAVAILABLE`;
- full regression, Ruff check, Ruff format, strict mypy, Python compilation,
  whitespace, package-boundary, and no-network checks.

These accepted guarantees are permanent regression requirements. Milestone 3
implementation authority remains deactivated. Milestone 3 remediation requires
a future explicit governance transition. The accepted Milestone 4 delivery
below grants no authority to change Milestone 3 semantics or delivered paths.

## Milestone 4 — Strategy validation — completed and accepted

Milestone 4 was independently reviewed and accepted on 2026-08-29 at
implementation commit `3a4377355b6715d588fb0736e9da3c6d7cd42391`. The
accepted implementation has parent
`b9d73ae7c6f42901c38d6ac0a830c3642eb53bff`, tree
`037416fd7f1a7aac3a59a2573a21c95d1f70751d`, and content-manifest SHA-256
`53cd2df345aa33ee258a1039810daca1a624f0cae9cdce70939a22746cc70a08`.
Milestone 4 implementation authority is deactivated. At Milestone 4 closure,
no implementation milestone was active and Milestone 5 and every later
milestone were inactive. Milestone 5's later activation and accepted delivery
did not reopen Milestone 4 or change its accepted boundary.

The following records the delivered scope and permanent regression boundary;
it grants no continuing implementation authority.

The accepted Milestone 4 delivery validates a fixed strategy specification
over a complete, explicitly defined historical observation schedule by
independently rerunning the accepted Milestone 3 evaluator for every scheduled
observation and aggregating the reconstructed economics without inventing
execution behavior.
All work remains local, historical, read-only, fixture-driven, deterministic,
network-free, and non-actionable. Historical validation is not proof of future
profitability, executability, capital suitability, or authorization.

The ordered trust lifecycle is:

```text
RelationshipCandidate
    → RelationshipCertificateDraft
    → explicit semantic review
    → deterministic truth/payoff validation
    → RelationshipCertificate
    → deterministic pricing constraint
    → non-actionable ConstraintEvaluation
    → historical opportunity economics
    → non-actionable OpportunityCandidate
    → historical strategy validation
    → non-actionable historical validation result
    → later execution simulation
    → later deterministic risk authorization
```

The accepted validator requires an immutable, versioned validation
specification that contains at least:

- strategy ID and version;
- exact included relationship classes;
- exact historical analysis interval;
- an explicit observation schedule and sampling semantics;
- grouping and stratification keys;
- inclusion and exclusion rules;
- the exact denominator definition;
- explicit gap and missing-observation treatment;
- chronological partition definitions wherever partitions are used;
- caller-supplied evaluation quantities;
- required metrics and caller-supplied acceptance thresholds;
- ordered provenance.

Every scheduled observation must provide all inputs required to rerun the
accepted Milestone 3 evaluator:

- a validator-produced `RelationshipCertificate`;
- its trusted compiler-produced constraint;
- exact venue-native historical snapshots;
- an explicit positive counterfactual quantity;
- complete immutable, versioned, time-scoped fee policies.

A supplied `OpportunityEconomicsEvaluation`, `OpportunityEconomicsResult`,
`OpportunityCandidate`, serialized candidate, or previous aggregate report is
not sufficient authority. For every scheduled observation, the Milestone 4
validator must independently invoke the accepted Milestone 3 certificate,
constraint, observation, evaluation, depth, fee, edge, and trust path. Invalid,
copied, reconstructed, mutated, serialized, duplicated, or unavailable
material must fail closed. The validator must not reinterpret, bypass, or
change Milestone 3 semantics.

The accepted Milestone 4 delivery may deterministically report:

- scheduled observation count;
- eligible and ineligible denominator counts;
- counts and rates for every Milestone 3 status and reason;
- validated-opportunity frequency with its exact numerator and denominator;
- consecutive-observation persistence within an explicitly complete schedule;
- exact persistence run lengths and observed durations;
- requested quantity and observed-depth diagnostics;
- purchase cost;
- fee intervals;
- gross-edge intervals;
- net-edge intervals;
- residual single-leg-failure ranges already produced by Milestone 3;
- data-quality failure counts;
- explicitly requested stratification by venue, relationship type, or time
  interval.

All financial and ratio calculations must use exact `Decimal` arithmetic.
Every individual observation and its ordered provenance must be preserved.
Different venues, relationship classes, sampling windows, fee regimes,
currencies, or strategy versions must not be silently pooled. An unavailable
observation or explicit schedule gap must remain in the denominator and break
persistence unless the validation specification explicitly defines another
fail-closed treatment.

Chronological partitions and their membership must be immutable. Validation
or test observations must not be used to select strategy parameters,
thresholds, quantities, or inclusion rules. Reused observations must be
reported explicitly. Duplicate observation identities must be rejected.
Dataset and report identities, ordering, and serialization must be
deterministic and stable across hash seeds. Reordered, omitted, extra, or
duplicated observations, incomplete schedules, invalid partitions, and
temporal leakage must fail closed.

The reviewed authority does not provide complete semantics or defensible
defaults for:

- latency sensitivity;
- queue position;
- fill probability;
- partial fills;
- cancellation or sequencing;
- false-relationship ground truth;
- portfolio capital allocation;
- concurrent capital usage;
- realized portfolio PnL;
- drawdowns.

These metrics must be reported as unavailable or not evaluated. Milestone 4
must not silently use zero, full-fill, immediate-fill, equal-capital,
Kelly-sizing, or another inferred assumption. Per-opportunity counterfactual
purchase cost is permitted, but it must not be described as portfolio capital
usage. The accepted Milestone 6 slice accounts for standalone synthetic
partial fills and cancellations. Empirical latency, queue position, fill
probability, and live sequencing remain deferred. Risk limits and capital
authorization remain Milestone 7 work. A false-relationship statistic requires
a separately governed labeled benchmark and must not be inferred from
certificate outcomes or discovery rejections.

The output must be a deterministic, versioned, explicitly non-actionable
historical strategy-validation result that:

- binds the complete strategy specification;
- binds every scheduled observation and independently reconstructed result;
- preserves the numerator, denominator, exclusions, failures, and provenance;
- distinguishes validated measurements, failed acceptance criteria,
  insufficient evidence, and unavailable metrics;
- has deterministic identity, ordering, and stable serialization;
- cannot claim future profitability, execution support, simulation support,
  risk authorization, or trade authorization.

No historically supported artifact may be issued merely because one or more
`OpportunityCandidate` objects exist. Any later trusted historical-support
artifact must require all caller-specified acceptance criteria to pass and
must retain process-local trust protections equivalent to the existing
candidate boundaries.

The historical Milestone 4 delivered paths are:

- `src/invariant_engine/diagnostics/`;
- `tests/diagnostics/`;
- `fixtures/diagnostics/`.

The delivered diagnostics-recognition change in
`tests/relationships/test_relationships.py` is also historical. At delivery the
test still prohibited simulation, risk, execution, and reconciliation
packages. These paths and that former exception grant no continuing authority.
Any remediation or implementation change requires a future explicit
governance transition.

The accepted Milestone 4 boundary permanently excludes:

- live ingestion or network access;
- authentication, credentials, wallets, or signing;
- orders, routes, submissions, or cancellations;
- current fee discovery;
- new relationship discovery or certificate semantics;
- changes to constraint or Milestone 3 economics semantics;
- recommended sizing or capital allocation;
- execution simulation;
- latency or queue models;
- fill-probability or partial-fill models;
- portfolio construction;
- realized portfolio returns or drawdowns;
- statistical skill, causal, or future-profit claims;
- risk authorization;
- Milestone 5 or later behavior.

### Permanent Milestone 4 regression guarantees

All later work must preserve:

- local, historical, read-only, fixture-driven, deterministic, network-free,
  and explicitly non-actionable behavior;
- immutable, versioned strategy specifications;
- exact ordered schedules, timestamps, identities, partitions, strata,
  quantities, fee regimes, currencies, and provenance;
- explicit unavailable schedule slots that remain in denominators and break
  persistence;
- independent invocation of the accepted public Milestone 3 evaluator for
  every complete slot;
- no trust in supplied evaluations, results, candidates, serialized artifacts,
  or previous reports;
- rejection of duplicate identity or material, cross-partition material reuse,
  invalid partitions, schedule mismatches, and temporal leakage;
- explicit integer numerators and denominators, locally controlled `Decimal`
  ratio precision and rounding, and no mutation of or dependence on the
  process-global `Decimal` context;
- exact status, reason, data-quality, frequency, persistence, scope, and
  stratification reporting;
- data-quality classification by the accepted closed reason semantics rather
  than `UNAVAILABLE` status alone, with at most one data-quality failure per
  observation;
- independently non-empty required metrics, evidence minimums, and acceptance
  criteria, including fail-closed handling of post-construction mutation;
- exact-scope availability for required economics-derived measurements, with
  no borrowing from observations outside the requested partition or stratum;
- preservation of individual requested quantities, depth diagnostics, purchase
  costs, fee intervals, gross-edge intervals, net-edge intervals, and residual
  single-leg-failure results without silent financial pooling;
- explicit unavailable or not-evaluated records for all eleven unsupported
  roadmap metrics listed above;
- the fail-closed status precedence `UNAVAILABLE` →
  `INSUFFICIENT_EVIDENCE` → `CRITERIA_NOT_MET` → `VALIDATED`;
- successful historical records only for overall `VALIDATED`;
- evaluator-only process-local weak object-identity trust;
- rejection of successful-record trust after material mutation, copy,
  deepcopy, pickle, reconstruction, JSON transfer, or subclassing, together
  with self-pruning of weak trust entries after garbage collection;
- stable serialization that excludes all runtime trust state;
- explicit statements denying future-profit, execution, simulation, risk, or
  trading authority;
- continued absence of live ingestion, credentials, wallets, signing, orders,
  routing, cancellation, execution simulation, risk authorization, and trading
  behavior.

### Milestone 4 acceptance record

The accepted content manifest is:

```text
713958c553526732a386456361327082ea1be4d45b72869c63fc38d5bb94a343  fixtures/diagnostics/README.md
9f9b77cdec7db0edafaff022debb78d91f9f973c82cda2f95b69161afeffd9fb  fixtures/diagnostics/strategy_cases.json
782729484c5aa071b1746874acb08c6085e9013835fe5d593249a7e20525a852  src/invariant_engine/diagnostics/__init__.py
41c3e1129875776b7b62c5295201890c589f69d9d3d56db513ccc93f1e548928  src/invariant_engine/diagnostics/evaluator.py
639b764395ecb79dd98c77877424d92c8a0dc773aeaddf783a1fa74772614328  src/invariant_engine/diagnostics/models.py
0670711f17b4377c8bbc20b11925683a8f5460506e9b6aab7f76a4f58d114446  tests/diagnostics/test_strategy_validation.py
41208b5e04b3dce11de1f330a49f731dda2de58e846ea1ac20293cb79bd0fd1f  tests/relationships/test_relationships.py
```

Its SHA-256 is
`53cd2df345aa33ee258a1039810daca1a624f0cae9cdce70939a22746cc70a08`,
calculated over the exact UTF-8 lines above without the Markdown fence and
with one trailing newline after every line, including the final line.

The independently observed final validation baseline was:

- 64 diagnostics tests passed;
- 354 complete tests passed;
- 47 relationship tests passed;
- 75 opportunity tests passed;
- 1 no-network test passed;
- Ruff check passed;
- Ruff format check passed for 67 files;
- strict mypy passed for 48 source files;
- Python 3.11 compilation passed;
- diagnostics JSON parsing passed;
- `git diff --check` passed;
- diagnostics passed under `PYTHONHASHSEED=1`, `2`, and `random`;
- networking-import, prohibited-package, prohibited-capability, trust,
  deterministic-serialization, and artifact-hygiene checks passed;
- final review did not mutate tracked content.

Three remediation cycles were completed before acceptance:

1. Required metrics, evidence minimums, and acceptance criteria were made
   independently non-empty, and post-construction mutation was made
   fail-closed.
2. Data-quality failures were classified using explicit accepted reasons
   rather than every `UNAVAILABLE` result.
3. Required economics-derived metrics were made unavailable when their exact
   scope contained no applicable per-observation measurement.

## Milestone 5 delivery and later milestone roadmap

### Milestone 5 — Bounded live read-only capture batch — completed and accepted

#### Historical activation, amendment, acceptance, and closure state

Milestone 5 was activated through governance commit
`282a3a1ccbe9263ce74cb3a38c90773fc817f244`, parent
`ec3a8356a91cdbcf6eefbc140da0f579e0cb6233`, tree
`b8530b7128b4e864e48df45676f0c1ecadaf6b50`. Its bounded trailer-discard
amendment was established through governance commit
`a0776a1b99f334aa953a361da2100ca75c93b9f1`, parent
`282a3a1ccbe9263ce74cb3a38c90773fc817f244`, tree
`175b754c947df4b646fb1cbe6ddbc2e72e824d75`. These are historical identities
of completed, separate governance transitions; they do not grant continuing
implementation authority or operational authorization.

The bounded implementation was independently reviewed and accepted at commit
`e6cfd01d9eb9e3143d3fa23c4e739c8dcecacbfa`, parent
`a0776a1b99f334aa953a361da2100ca75c93b9f1`, tree
`1b76b0c06bf6af5c8aae07358240ead1a844803c`. Its accepted 18-file
content-manifest SHA-256 is
`612c14ec018eed00323fb45003a30ae17578f3c2eff7b6daac0edf35ed0610ef`.

The independently observed acceptance results were:

- 554 total tests, including 200 capture tests and 354 protected Milestones
  1–4 tests;
- 20 materially distinct external adversarial probes;
- the no-network suite and capture suite under `PYTHONHASHSEED=1`, `2`, and
  `random`;
- Ruff check and format check, strict mypy, and Python compilation;
- parsing of all 15 fixture JSON files; and
- package and import boundaries, whitespace, dependency, and artifact-hygiene
  checks.

These historical implementation-acceptance results predate this draft.
Implementation acceptance and governance closure are separate gates.

Milestone 5 implementation authority is deactivated. The separately accepted
Capture v2 extension below did not reopen Milestone 5 or alter its historical
boundary.

#### Purpose and trust boundary

The accepted Milestone 5 delivery provides a finite, one-shot, live, read-only
REST capture batch over an immutable ordered list of caller-supplied venue
identifiers. The boundary begins with a validated capture specification and,
for Kalshi, a runtime-only caller-owned authentication binding. It ends with
immutable capture provenance plus either a venue-native captured REST order
book or an explicit terminal target failure. It does not discover markets or
tokens.

Finite means at most 64 caller-supplied targets and bounded engine-controlled
attempts. It is not a promise of a hard wall-clock completion deadline for
caller-owned signer code or system DNS resolution, neither of which the engine
can forcibly bound.

A live capture is a distinct artifact. It is not and cannot impersonate a
fixture-only `RawEnvelope`, replay input, trusted observation, relationship,
certificate, constraint evaluation, opportunity, historical
strategy-validation result, simulation, risk decision, order, or trade. A
capture does not prove venue truth, freshness, atomicity, completeness,
executability, or successful future access.

#### Reviewed research authority and provenance

The planner verified research commit
`8361a49bcc3519ca17a91c69c46a9b36f3017273`. The following research files are
listed only for provenance and are not part of this repository:

- `wiki/platforms/kalshi.md` — `PLATFORM-0002`;
- `wiki/platforms/polymarket.md` — `PLATFORM-0001`;
- `wiki/concepts/prediction-market-mechanics.md` — `CONCEPT-0002`;
- `registry/sources.yaml`;
- `registry/pages.yaml`;
- `registry/claims.yaml`;
- `index.md`;
- `log.md`; and
- reviewed source summaries for `SRC-0014`, `SRC-0024`, and `SRC-0040`
  through `SRC-0045`.

The applicable sources are active, their summaries and applicable claims are
reviewed, `SRC-0041` supersedes `SRC-0022`, and promotion and synthesis
reconciliation are complete. The accepted governance and implementation use
only the supplied reviewed findings below; they did not inspect the research
repository, use the newly found demo-funds documentation, or rely on
unverified Polymarket staging access. Relevant synthesis provenance remains
`PLATFORM-0001` (`wiki/platforms/polymarket.md`) and `PLATFORM-0002`
(`wiki/platforms/kalshi.md`). This closure adds no external evidence and
claims no research promotion.

The reviewed findings establish for this bounded implementation:

- `SRC-0014` / `CLM-0067`–`CLM-0068`: Polymarket `GET /book` requires
  `token_id`; its documented public operation returns `market`, `asset_id`,
  `timestamp`, `hash`, `bids`, `asks`, `min_order_size`, `tick_size`,
  `neg_risk`, and `last_trade_price`; bids are descending and asks ascending;
  price and size fields are strings; HTTP 200 is documented; and the active
  artifact was reacquired byte-identically on 2026-08-31.
- `SRC-0041` / `CLM-0179`, `CLM-0182`, and `CLM-0185`–`CLM-0187`: Kalshi
  `GET /markets/{ticker}/orderbook` requires a string ticker; HTTP 200 requires
  `orderbook_fp` with `yes_dollars` and `no_dollars` arrays; every level is
  exactly two strings containing dollar price followed by contract quantity.
- `SRC-0041` / `CLM-0184`: Kalshi native YES and NO bids must be preserved;
  published asks must not be fabricated.
- `SRC-0024` / `CLM-0093`: response contract-count `_fp` strings emit two
  decimal places; this does not establish a complete numeric lexical grammar.
- `SRC-0040` / `CLM-0175`–`CLM-0177` and `SRC-0042` / `CLM-0192`: Kalshi
  authentication uses `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-TIMESTAMP`, and
  `KALSHI-ACCESS-SIGNATURE`; the demonstrated signing message concatenates
  timestamp, HTTP method, and the full request path retaining
  `/trade-api/v2`; hostname and query are excluded; examples use Base64
  RSA-PSS/SHA-256 signatures with digest-length salt but are not normative
  cryptographic test vectors.
- `SRC-0042` / `CLM-0190`–`CLM-0191`: demo and production credentials are not
  shared; the recommended REST bases are
  `https://external-api.demo.kalshi.co/trade-api/v2` and
  `https://external-api.kalshi.com/trade-api/v2`; compatibility origins do not
  establish safe failover, data equivalence, or credential portability.
- `SRC-0043`–`SRC-0044` / `CLM-0194`–`CLM-0197`: documented scope labels,
  response-side visibility, and omitted-scope broad read-plus-write behavior
  do not prove the actual environment, scope, or effective permissions of an
  uninspected credential. The engine must not enumerate or create keys.

No current external documentation or unreviewed material may become
implementation authority. If implementation needs evidence beyond this
reviewed scope, work on the dependent portion must stop and report the exact
candidate-source question.

#### Authentication conflict and selected policy

The documentation conflict remains unresolved. `SRC-0041` / `CLM-0180` and
`CLM-0188` declare operation-level authentication and a 401
authentication-required response. `SRC-0045` / `CLM-0198`–`CLM-0199` describe
and demonstrate the same order-book GET without authentication headers.
Neither establishes publication or update precedence.

The accepted implementation signs Kalshi requests from the outset as an
engineering policy under uncertainty. This choice does not resolve the
evidence conflict and must not be described as proof that the endpoint is
universally authenticated, universally public, or optionally authenticated.
Kalshi has no anonymous fallback.

#### Exact operations and environments

Only these operations were implemented and remain supported by the accepted
delivery:

- Polymarket production: `GET https://clob.polymarket.com/book?token_id={caller_supplied_token_id}`;
- Kalshi demo: `GET https://external-api.demo.kalshi.co/trade-api/v2/markets/{ticker}/orderbook`;
- Kalshi production: `GET https://external-api.kalshi.com/trade-api/v2/markets/{ticker}/orderbook`.

Polymarket supports production only. Kalshi supports explicit demo and
production environments with environment-bound authentication inputs. No
staging or compatibility origin, optional depth parameter, arbitrary URL,
additional query parameter, other HTTP method, redirect target, or origin
failover is allowed.

Production support means that the bounded implementation models and tests that
exact operation. It is not permission to deploy or make a live production
request. The initial separately authorized Kalshi live trial, if later
approved, will use demo. A Polymarket production trial also requires separate
bounded operational authorization even though its selected operation is
public. A live trial was not part of implementation or ordinary tests.

#### Historical delivered paths and dependency record

The accepted source delivery consists of:

- `src/invariant_engine/capture/__init__.py`;
- `src/invariant_engine/capture/models.py`;
- `src/invariant_engine/capture/specification.py`;
- `src/invariant_engine/capture/authentication.py`;
- `src/invariant_engine/capture/transport.py`;
- `src/invariant_engine/capture/parsing.py`;
- `src/invariant_engine/capture/batch.py`; and
- `src/invariant_engine/capture/serialization.py`.

The accepted test delivery consists of:

- `tests/capture/conftest.py`;
- `tests/capture/test_specification.py`;
- `tests/capture/test_authentication.py`;
- `tests/capture/test_transport.py`;
- `tests/capture/test_parsing.py`;
- `tests/capture/test_batch.py`;
- `tests/capture/test_serialization.py`; and
- `tests/capture/test_trust_boundaries.py`.

The accepted fixture delivery consists of:

- `fixtures/capture/README.md`; and
- `fixtures/capture/cases.json`.

These 18 paths are historical Milestone 5 delivered paths. They confer no
continuing implementation authority or path exception. No runtime or
development dependency was added; the accepted implementation uses
standard-library transport and a caller-owned signing interface. Any future
change to these paths, `pyproject.toml`, an existing implementation or test,
or another path requires an explicit governance transition.

#### Capture specification and local input limits

The capture specification must be immutable, versioned, provenance-bearing,
and contain 1 through 64 ordered targets. Every target binds its position,
venue, environment, exact permitted origin, identifier, limits, and ordered
provenance. All limits in this section are local engineering restrictions, not
universal venue rules; venue-valid input may be outside this supported local
contract.

The local identifier contract is:

- Polymarket `token_id`: 1 through 128 ASCII decimal digits, grammar
  `[0-9]{1,128}`;
- Kalshi `ticker`: 1 through 128 ASCII characters, grammar
  `[A-Z0-9][A-Z0-9._-]{0,127}`;
- capture specification ID and provenance reference components: 1 through 128
  visible ASCII characters from `[A-Za-z0-9._:/-]`;
- at most 64 ordered provenance references per specification or target, each
  at most 512 ASCII characters after its typed components are serialized.

No identifier normalization is performed. The caller-supplied identifier that
passes the grammar is preserved exactly. A duplicate target is the same exact
venue, environment, origin, and identifier tuple appearing more than once;
any duplicate rejects the entire specification before signing or transport.
The same Kalshi ticker in demo and production is not a duplicate because its
environment and origin differ.

The implementation must validate the complete specification and every nested
value before invoking a signer or transport. Unsupported targets, unknown
versions, empty or oversized lists, invalid provenance, duplicates, ambiguous
types including `bool` used as an integer, and environment/origin mismatches
reject the whole batch with zero signing calls and zero dispatches.
All runtime authentication bindings required by the validated Kalshi targets
must then be present, exactly typed, unique by environment, and internally
consistent before the first attempt begins. A missing, extra, duplicated, or
mismatched binding rejects the batch invocation with zero signer calls and
zero dispatches; bindings are never specification material.

#### Authentication contract

Kalshi uses a narrow runtime-only authentication binding containing:

- the explicit Kalshi demo or production environment and its one permitted
  origin;
- a caller-supplied key ID; and
- a caller-owned signer that receives engine-constructed signing `bytes` and
  returns only the signature string.

The key ID must be an exact `str` of 1 through 256 visible ASCII characters
matching `[A-Za-z0-9._-]{1,256}`. The signature must be an exact `str` of 1
through 4096 ASCII characters in canonical standard Base64, decode with strict
validation to 128 through 1024 bytes, and re-encode byte-identically. Newlines,
control characters, whitespace, non-ASCII text, URL-safe Base64 substitutions,
and noncanonical padding are rejected. These are header-safety and boundedness
restrictions, not proof of cryptographic correctness or a universal venue key-
size rule.

No arbitrary caller-supplied header mapping is accepted. The library must not
load or discover secrets from files, environment variables, keychains,
configuration, network services, ambient HTTP state, or any other location. It
must not implement RSA or other private-key cryptography, persist or serialize
the signer, key ID, signature, signing bytes, or authentication binding, or
send Kalshi authentication to Polymarket.

For each Kalshi target, the engine must first construct the exact ASCII request
path `/trade-api/v2/markets/{ticker}/orderbook`. Immediately before that
target's signer call, it generates a base-10 Unix-epoch millisecond timestamp
as an ASCII digit string of 1 through 20 characters. The signing bytes are the
ASCII concatenation `timestamp + "GET" + full_path`; host and query are absent.
The exact same timestamp, method, and path must be dispatched, and the same
timestamp must be transmitted in `KALSHI-ACCESS-TIMESTAMP` together with the
validated key ID and returned signature in the other two fixed headers.

Environment/origin binding is checked before signing and again immediately
before dispatch. The complete specification material fingerprint is checked
before the signer call and immediately after it; mutation or misbinding during
the callback causes a terminal integrity failure and zero dispatches for that
target. The signer is trusted caller code: engine acceptance cannot prove its
purity, completion time, private-key handling, signature algorithm, or
cryptographic correctness. The engine validates the declared environment
binding only; it does not establish the actual environment, scopes, or
permissions of the key.

Signer exceptions and malformed signer returns become a terminal
`SIGNING_FAILED` result. Public capture results, serialization, logs, and
capture-API exception chains must not include the arbitrary exception text,
exception object, traceback, signing bytes, key ID, or signature. A signing
failure performs zero HTTP dispatches and does not stop later valid targets.

#### Attempt, identity, mutation, and continuation contract

The earlier prospective phrase “exactly one request attempt per target” was
amended: each position receives exactly one logical `TargetAttempt`, while
each target performs at most one HTTP dispatch. A Kalshi signing or integrity
failure is a completed terminal target attempt with zero dispatches. No retry
is performed.

Targets are processed serially in caller order. Ordinary terminal target
failures do not prevent later targets from receiving their one logical
attempt. There is no concurrency, polling, catch-up, retry, redirect, failover,
or implicit second request. A batch-level invalid specification produces no
target attempts because positions are not trusted until complete validation.

Specification, target, attempt, and result identities must be immutable,
deterministic, positional, and bound to the complete specification. Material
mutation or misbinding must be rejected before signing, dispatch, publication,
and serialization. Completed results must reject omitted, extra, reordered,
duplicated, substituted, or positionally misbound attempt records. Runtime
producer trust must be process-local and excluded from stable serialization;
copy, reconstruction, pickle, or JSON does not transfer it.

#### Transport construction, timeouts, and header policy

The transport must connect directly with the standard library to the exact
allowlisted HTTPS origin and construct only the exact allowed method, path,
and query. It must use the default system trust store with certificate and
hostname verification enabled and TLS 1.2 or later. It must not use ambient
proxy configuration, cookies, credentials, authentication handlers, redirects,
retries, connection failover, or caller-supplied transport headers. Requests
have no body and send only the exact-origin `Host`, `Accept: application/json`,
`Accept-Encoding: identity`, and `Connection: close` headers, plus the three
fixed validated Kalshi authentication headers for Kalshi only. A non-identity
content encoding is a terminal header failure.

The fixed local timing policy is:

- 5.0 seconds for TCP connection and TLS handshake operations;
- 5.0 seconds as the socket inactivity timeout for each request-write,
  response-header, body-read, or trailer-read operation; and
- a 20.0-second transport elapsed budget beginning immediately before the
  engine invokes system name resolution for the one dispatch and covering
  engine-controlled resolution orchestration, connect, TLS, request write,
  response headers, body reads, and trailer reads.

The engine must check the monotonic elapsed budget before and after every
engine-controlled blocking stage and before and after every body or trailer
read, and must use the smaller remaining budget where a standard-library
timeout accepts one. No further engine-controlled read may begin after the
elapsed budget expires. The budget excludes specification validation and
caller signer execution. System DNS calls may outlast the budget because the
standard library and operating system do not guarantee hard cancellation;
this limitation must be explicit. No hard wall-clock completion guarantee is
made for DNS or external signer code.

Initial and informational response headers are quarantined and limited to at
most 100 fields, at most 8,192 ISO-8859-1 octets for any parsed name/value pair,
and at most 32,768 such octets in aggregate. These limits remain cumulative
across informational responses and are separate from the trailer limits below.
The underlying standard-library maximum accepted header line remains an
additional ceiling, not an expanded capture contract. Invalid names or values,
control characters other than parsing syntax already removed by the library,
obsolete folding, conflicting `Content-Length`, unsupported transfer framing,
or non-identity `Content-Encoding` fail closed.

Unknown and unexpected initial or informational response headers count toward
their limits but are otherwise ignored. Public results may retain only the
integer HTTP status, a strictly parsed nonnegative `Content-Length` when
unambiguous, and a normalized `Content-Type` media type from visible ASCII; raw
response headers and header parameters are not retained or serialized. All
received initial and informational header names and values are nevertheless
scanned by the confidentiality detector before this allowlisted metadata may
be published.

#### Bounded trailer discard policy

Trailers are discarded. They must not be exposed, serialized, logged, merged
into response headers, used as response metadata or market data, or accumulated
as an unrestricted collection. The engine may process trailer framing only as
needed to bound consumption and establish response termination.

The separate fixed local trailer limits are at most 100 nonempty trailer
lines, at most 8,192 raw bytes per line including its line ending, and at most
32,768 raw bytes across the complete trailer section including its final
terminator. Reads must be bounded; only a bounded excess probe may be used to
detect a limit violation. These limits do not reset or change the cumulative
initial/informational-header limits.

Trailer reads remain within the existing 20.0-second elapsed budget and
5.0-second inactivity timeout. The engine checks the elapsed budget before and
after each trailer read, reduces a supported socket timeout to the smaller
remaining budget, and initiates no further read after expiry. The existing DNS
and external-signer deadline limitations remain unchanged.

Interrupted, over-limit, or unterminated trailer consumption prevents normal
response completion. After zero acquired entity-body bytes, deadline or
inactivity failure produces `FAILED_BEFORE_FIRST_BYTE` with `TIMEOUT`; every
other trailer-consumption failure produces `FAILED_BEFORE_FIRST_BYTE` with
`TLS_OR_TRANSPORT_FAILED`. After one or more acquired entity-body bytes, either
kind produces `PARTIAL` with `BODY_PARTIAL`. Existing safely acquired header or
body confidentiality evidence overrides these ordinary statuses. The engine
must not continue unsafe I/O solely to seek additional evidence.

This is a user-selected local engineering policy, not a claim that either
venue sends trailers. Whether either supported endpoint actually sends them
remains unknown. External HTTP documentation considered during planning is not
newly promoted research authority.

#### Body acquisition, retention, and confidentiality

The maximum response entity body is 1,048,576 bytes. The transport reads in
chunks of at most 65,536 bytes and may read one additional byte solely to
classify oversize input. “Received bytes” means entity-body bytes after HTTP
transfer framing is removed and before any content decoding; only identity
content encoding is supported. Trailer and other transfer-framing bytes never
contribute to entity-body counts or digests.

Body acquisition outcome and body retention state are separate closed enums.
The acquisition outcome records what occurred before confidentiality filtering:

- `NOT_STARTED`: no body-read operation began;
- `FAILED_BEFORE_FIRST_BYTE`: acquisition began but failed before receiving
  any entity-body byte, including chunked termination or trailer-consumption
  failure after a zero-length entity body;
- `COMPLETED`: normal EOF or the exact declared body length was reached within
  the cap, including a normally completed zero-length body; for a chunked
  response, completion additionally requires consumption of the terminating
  trailer section within its limits and the transport deadline;
- `PARTIAL`: acquisition failed after receiving at least one entity-body byte
  and before normal response completion, including chunked termination or
  trailer-consumption failure, without crossing the cap; and
- `OVERSIZED`: streaming acquisition observed at least one byte beyond the
  1,048,576-byte cap.

The result separately records `acquisition_started`, `normal_completion`,
`received_byte_count`, `retained_byte_count`, optional retained bytes, and an
optional retained-body SHA-256. `received_byte_count` counts body bytes actually
obtained from the transport, including the one oversize probe byte when read.
`retained_byte_count` counts only bytes retained for publication. The retention
states are:

- `ABSENT`: no body byte was acquired without established normal completion;
  this covers both `NOT_STARTED` and `FAILED_BEFORE_FIRST_BYTE`; retain no body
  and no digest;
- `COMPLETE`: normal completion occurred within the cap; retain the exact
  bytes and their SHA-256, including a present zero-length byte string and the
  empty-body SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
- `PARTIAL`: retain the exact nonempty prefix received before failure and its
  SHA-256;
- `OVERSIZED`: retain only the exact first 1,048,576-byte prefix and its
  SHA-256, never the probe byte; and
- `SUPPRESSED`: confidentiality filtering prevents publication of any body
  material and discards any otherwise retainable body or prefix; retain no
  body and no digest while preserving the actual received-byte count and
  recording whether acquisition started and how it ended.

Every entity-body byte returned by an engine-controlled read is accounted for
before a later deadline or transport failure from that read is classified.
This includes entity-body bytes already buffered when a read subsequently
fails. Trailer and other framing bytes are discarded and cannot change the
body count, retained prefix, or digest.

An unambiguous `Content-Length` greater than the cap permits an immediate
`BODY_OVERSIZED` result without beginning body acquisition; its retention state
is `ABSENT`, and no body digest exists. Otherwise streaming acquisition applies
the prefix rule above. In both cases no oversized material is parsed or
published as a successful capture.

The valid unsuppressed combinations are exhaustive:

| Acquisition outcome | Acquisition started | Normal completion | Retention | Received length | Retained length and material | Ordinary status before integrity or confidentiality override |
|---|---:|---:|---|---:|---|---|
| `NOT_STARTED` | No | No | `ABSENT` | 0 | 0; body and digest absent | Predispatch failure, header failure, timeout/transport failure before body acquisition, or declared `BODY_OVERSIZED`. |
| `FAILED_BEFORE_FIRST_BYTE` | Yes | No | `ABSENT` | 0 | 0; body and digest absent | `TIMEOUT` or `TLS_OR_TRANSPORT_FAILED`, including interrupted, over-limit, or unterminated trailer consumption after zero entity-body bytes. |
| `COMPLETED` | Yes | Yes | `COMPLETE` | 0 through 1,048,576 | Equal to received length; body present and digest present, including zero length. | `BODY_EMPTY`, `HTTP_STATUS_UNSUPPORTED`, parsing/schema/identifier failure, or `CAPTURED` as applicable. |
| `PARTIAL` | Yes | No | `PARTIAL` | 1 through 1,048,576 | Equal to received length; nonempty prefix and digest present. | `BODY_PARTIAL`, including interrupted, over-limit, or unterminated trailer consumption after a body prefix. |
| `OVERSIZED` | Yes | No | `OVERSIZED` | 1,048,577 | 1,048,576-byte prefix and digest present. | `BODY_OVERSIZED`. |

Confidentiality detection replaces the retention state in any safely observed
case with `SUPPRESSED` and makes the primary status
`CONFIDENTIALITY_FAILURE`. Initial/informational-header-only detection must stop
before body acquisition and therefore combines `NOT_STARTED`,
acquisition-started `No`, normal-completion `No`, received length 0, retained
length 0, no body, and no digest. Detection in a complete, partial, or oversized
body preserves its original acquisition outcome, acquisition flags, and actual
received length, but requires retained length 0, no body, and no digest.
Suppression provenance may identify only `HEADER` or `BODY`, never the matched
key ID, signature, or matched bytes.

Normal completion is defined exclusively by acquisition outcome `COMPLETED`,
not by retention state `COMPLETE`. A confidentiality-suppressed body whose
acquisition outcome is `COMPLETED` therefore retains acquisition-started `Yes`
and normal-completion `Yes` while using retention `SUPPRESSED`, retained length
0, and no retained body or digest. Confidentiality suppression changes what
may be retained and published; it does not rewrite independently established
acquisition history.

No other combination is valid. In particular, `ABSENT` or `SUPPRESSED` cannot
carry bytes or a digest; `COMPLETE`, `PARTIAL`, and `OVERSIZED` must carry both
bytes and the SHA-256 of exactly those bytes; retained length must equal the
actual retained body length; normal completion is true if and only if the
acquisition outcome is `COMPLETED`, whose retention may be `COMPLETE` or, after
confidentiality filtering, `SUPPRESSED`; `PARTIAL` and `OVERSIZED` require
positive received length; and `CAPTURED` requires `COMPLETED` plus `COMPLETE`
and a successfully parsed nonempty HTTP 200 body. Contradictory state, status,
flag, length, body, or digest material must fail integrity validation before
publication or serialization.

Every digest identifies exactly the retained bytes under the explicit
retention state; it never purports to identify discarded or unreceived bytes.
`PARTIAL` and `OVERSIZED` are terminal failures and are not parsed as successful
order books. A normally completed zero-length body is retained with the empty-
body digest. It receives `BODY_EMPTY` only for an unsuppressed HTTP 200 response
when no higher-priority failure applies. A completed empty HTTP response with
any other status, including HTTP 404, retains the empty bytes and digest but
receives `HTTP_STATUS_UNSUPPORTED`; confidentiality or a trustworthy observed
integrity failure still takes precedence.

All initial/informational header and entity-body material is quarantined before
publication. The exact confidentiality detector searches for the complete key
ID and signature as raw ASCII byte substrings in every received initial or
informational header name/value and quarantined candidate body or prefix. It
also lexically scans every complete JSON string token in the quarantined
candidate bytes and decodes valid JSON escapes—including `\"`, `\\`, `\/`,
the control escapes, and case-insensitive four-hex-digit `\uXXXX` sequences
with valid surrogate pairing—then searches each decoded string for the exact
key ID or signature. This detects arbitrarily mixed valid JSON escapes within
complete string tokens; malformed or incomplete string tokens are covered only
by the raw-byte search.

Discarded trailers are explicitly outside confidentiality-reflection scanning.
A key ID or signature appearing only in a discarded trailer does not trigger
body suppression or `CONFIDENTIALITY_FAILURE`. This narrow exclusion does not
permit trailer bytes or fields in a public result, serialization, log,
warning, or exposed exception. Existing safely observed initial-header or body
confidentiality findings retain precedence over ordinary trailer-consumption
failures. Suppression provenance remains limited to `HEADER` or `BODY`; no
trailer suppression source or public enum is added.

If either value is detected, the result is terminal
`CONFIDENTIALITY_FAILURE`: suppress the entire body or prefix and its digest,
suppress all response-header metadata except the integer HTTP status when
already safely parsed, and retain only safe attempt identity, target identity,
timing classification, acquisition outcome and flags, received-byte count,
zero retained-byte count, suppression source, and failure code.
Confidentiality failure takes precedence over partial- or oversized-body retention and every other
detected response failure. This is an explicit exception to byte preservation.
The detector is bounded to exact supplied values and the stated JSON escape
normalization; it does not prove the absence of every transformed, encoded,
truncated, hashed, or otherwise derived secret.

No public representation, stable serialization, log, warning, or exposed
exception may contain unrestricted response headers, raw transport or signer
exception messages, authentication bindings, key IDs, signatures, signing
bytes, callbacks, or other runtime-only state.

#### UTF-8, JSON, and numeric parsing restrictions

Only a `COMPLETE` HTTP 200 identity-encoded body proceeds to parsing. Parsing
requires strict UTF-8 with no replacement, strict JSON with exactly one top-
level object, duplicate-key rejection at every depth, rejection of nonstandard
numeric constants, rejection of unpaired Unicode surrogates, and exact required
field types. JSON numbers are not accepted for venue financial, price, size,
quantity, or timestamp strings, and binary floating-point values must never be
created for them.

The local parser limits JSON nesting to 32 containers, any decoded JSON string
to 262,144 Unicode scalar values, any object to 4,096 members, any array to
10,000 elements, and every JSON numeric token to 64 ASCII characters. JSON
integers and decimals are parsed without binary floating point even when they
occur only in unknown retained material. Venue numeric strings are also
limited to 64 ASCII characters. General supported decimal strings use
`(?:0|[1-9][0-9]*)(?:\.[0-9]{1,18})?`; signs, exponent notation, leading
zeros except the single integer zero, trailing decimal points, and non-ASCII
digits are outside the local contract. Kalshi contract-quantity `_fp` strings
use `(?:0|[1-9][0-9]*)\.[0-9]{2}`. Accepted numeric strings are parsed with
exact `Decimal` under a locally controlled context; these lexical subsets and
limits are engineering restrictions, not complete venue grammars or price
bounds.

Unknown JSON fields remain preserved only in the quarantined retained body and
are excluded from the normalized capture model and safe metadata. They are not
silently promoted into semantics. Known required fields must have exact types;
`bool` is never accepted as an integer.

#### Venue-native response contract

For Polymarket HTTP 200, require exactly typed presence of all reviewed fields:
`market`, `asset_id`, `timestamp`, and `hash` are strings; `bids` and `asks`
are arrays whose levels are objects with string `price` and `size` fields;
`min_order_size`, `tick_size`, and `last_trade_price` are supported decimal
strings; and `neg_risk` is a Boolean. Require `asset_id` to equal the requested
`token_id` exactly. Preserve direct bid and ask levels, received duplicates,
and received order without sorting or aggregation. Validate bids as adjacent
non-increasing prices and asks as adjacent non-decreasing prices, so equal
adjacent prices are preserved without assigning tie semantics. Preserve price
and size strings and their exact `Decimal` interpretations. Treat `timestamp`
as an opaque venue string with no unit, ordering, freshness, or atomicity
claim. These exact types and non-strict ordering checks define the supported
local response subset; they do not declare other venue responses invalid.

For Kalshi HTTP 200, require `orderbook_fp` with exactly typed `yes_dollars`
and `no_dollars` arrays. Every level must be an array of exactly two strings:
price followed by contract quantity. Preserve native YES and NO bids, received
level order, exact strings, and duplicate levels without sorting or
aggregation. Structurally empty arrays are accepted without an economic
interpretation. Do not invent asks, a venue timestamp or sequence, price
bounds, tie semantics, per-market tick validity, freshness, atomicity, or a
complete numeric grammar.

#### Terminal classifications and precedence

The batch and target result models must use closed, versioned status and reason
enums. Batch-level `SPECIFICATION_INVALID` or
`AUTHENTICATION_BINDING_INVALID` precedes target construction and causes zero
attempts, signer calls, and dispatches. For a constructed target, only
conditions actually observed are compared, using this precedence:

1. `CONFIDENTIALITY_FAILURE`;
2. `INTEGRITY_FAILURE` for mutation, identity, position, environment, origin,
   method, path, timestamp, header, or material misbinding;
3. `SIGNING_FAILED` before dispatch;
4. `RESPONSE_HEADERS_INVALID`;
5. `BODY_OVERSIZED`;
6. `BODY_PARTIAL` when bytes precede a timeout or transport/framing failure;
7. `TIMEOUT` when no body prefix exists;
8. `TLS_OR_TRANSPORT_FAILED` when no body prefix exists;
9. `HTTP_STATUS_UNSUPPORTED` for a completed response other than HTTP 200;
10. `BODY_EMPTY` only for an unsuppressed completed zero-length HTTP 200 body
    when no higher-priority failure applies;
11. `UTF8_INVALID`;
12. `JSON_INVALID`, including duplicate keys, depth, member, array, constant,
    or surrogate violations;
13. `SCHEMA_INVALID`, including exact-type, numeric-lexical, ordering, or
    structural violations;
14. `IDENTIFIER_MISMATCH`; and
15. `CAPTURED`.

This precedence does not require continued unsafe I/O merely to discover a
higher-priority condition. It governs conditions safely observed within the
bounded acquisition. Failure results use fixed safe codes and structured safe
metadata, never arbitrary exception text. Every ordinary terminal target
failure continues to the next already-validated target.

An observed `INTEGRITY_FAILURE` overrides the ordinary acquisition-derived
status, including `BODY_OVERSIZED`, `BODY_PARTIAL`, `TIMEOUT`, transport, HTTP,
empty-body, parsing, schema, identifier, and otherwise possible `CAPTURED`
statuses, but remains below `CONFIDENTIALITY_FAILURE`. It must never be
converted to `CAPTURED`. If the attempt identity and acquisition facts are
independently trustworthy—for example, a separately bound material fingerprint
detects mutation after a transport-local complete or partial acquisition—the
result may retain those exact acquisition outcome, flags, byte counts,
retention state, body, and digest facts while its primary status is
`INTEGRITY_FAILURE`.

If the identity binding, acquisition outcome, flags, counts, retained bytes, or
digest cannot be independently trusted, no attempt artifact containing those
facts may be published or serialized. Without independently trustworthy
confidentiality evidence, the batch must fail closed with a fixed outer
integrity code and safe batch identity only. If independently trustworthy
confidentiality evidence was already established from quarantined material,
suppression and a fixed safe outer confidentiality code take precedence, but
the untrusted attempt facts still must not be emitted. Neither case may
fabricate a well-formed attempt, infer replacement acquisition facts, or reuse
untrusted material.

#### Stable serialization and observer time

Stable, versioned serialization must bind the complete specification, target
order, immutable positional attempt identities, per-target dispatch count,
terminal statuses and reasons, safe ordered provenance, acquisition outcome,
acquisition-started and normal-completion flags, received-byte count, retention
state, retained-byte count, retained body and digest when permitted, and safe
suppression source when applicable. It must reject omitted, extra, reordered,
duplicated, mutated, misbound, or internally contradictory attempt material.
An `INTEGRITY_FAILURE` attempt is serializable only when its attempt identity
and every serialized acquisition and retention fact remain independently
trustworthy and satisfy the state matrix. When those facts are implicated, the
attempt itself is not serializable and only the applicable fixed safe outer
batch failure described above may be emitted.

Authentication bindings, key IDs, signatures, signing bytes, signer callbacks,
raw exceptions, unrestricted headers, all trailer material, suppressed bodies
and digests, sockets, clocks, and all process-local trust state are excluded.
Local observer timestamps are acquisition provenance only; they make no
venue-time, freshness, synchronization, or ordering claim.

#### Permanent Milestone 5 regression guarantees

All future work must preserve:

- immutable, exact-type, versioned specifications and exact ordered targets;
- finite sequential logical attempts, with at most one HTTP dispatch per
  target and ordinary terminal failures continuing to later validated targets;
- exact allowlisted origins, operations, methods, paths, queries, and Kalshi
  environment binding;
- caller-owned Kalshi signing, no anonymous fallback, no Kalshi
  authentication sent to Polymarket, and no ambient credential discovery;
- redacted authentication representations and detached caller-signer
  exception chains that cannot expose arbitrary exception text or runtime
  authentication material;
- bounded transport reads, exact body, initial/informational-header, and
  trailer limits, elapsed-budget enforcement, and rejection of negative chunk
  lengths before an entity-data read;
- truthful acquisition and retention states, exact received and retained byte
  accounting, and exact digest scope, including bytes obtained before an
  interrupted chunked read;
- bounded trailer discard without publication, serialization, logging,
  metadata merging, or trailer reflection scanning;
- initial/informational-header and entity-body confidentiality protection with
  the accepted precedence and suppression semantics;
- strict UTF-8 and JSON, duplicate-key rejection, exact `Decimal` handling,
  and preservation of venue-native strings, received ordering, and duplicate
  levels;
- deterministic identities, ordering, stable serialization, and process-local
  producer trust that does not transfer through copy, reconstruction, pickle,
  or JSON;
- no promotion of a capture artifact into an accepted historical artifact,
  replay input, trusted observation, relationship, evaluation, opportunity,
  simulation, risk decision, execution instruction, order, or trade; and
- entirely synthetic network-free ordinary tests and every protected
  Milestones 1–4 guarantee.

#### Accepted implementation validation contract and record

Implementation acceptance required an independent reviewer to:

1. verify the exact accepted activation commit, its expected parent, tree,
   accepted document/content identities, and local `HEAD`/`origin/main`
   alignment without treating the local remote-tracking ref as a live remote
   query;
2. record complete tracked, staged, unstaged, untracked, and ignored paths and
   SHA-256 values for every changed or untracked file before validation;
3. read every changed and untracked file completely;
4. verify that every path and import is authorized and that no runtime or
   development dependency changed;
5. run the complete required validation independently with caches and probe
   artifacts outside the engine worktree;
6. run materially distinct adversarial probes outside the engine worktree,
   including probes not merely restating implementation-authored tests;
7. recheck content hashes, complete manifests, diff scope, and artifact hygiene
   after validation; and
8. explicitly accept or reject the exact implementation content reviewed.

Implementation acceptance also required deterministic offline tests covering
at least:

- success and every closed terminal-failure path for Polymarket and Kalshi;
- exact Polymarket production and Kalshi demo/production origin binding;
- Kalshi signing-byte construction and equality of the signed timestamp,
  method, and path with transmitted fixed headers;
- malformed key IDs and signer outputs, signer exceptions containing secrets,
  zero dispatch after signing failure, no anonymous fallback, and no Kalshi
  authentication sent to Polymarket;
- specification and nested-material mutation before signing, during a signer
  callback, before dispatch, and before serialization;
- duplicate-target rejection and omitted, extra, reordered, duplicated,
  substituted, or misbound attempt rejection;
- malformed UTF-8 and JSON, duplicate keys at every depth, nonstandard numeric
  constants, unpaired surrogates, depth/member/array/string limits, exact
  required types, numeric ambiguity, ordering, duplicate levels, identifier
  mismatch, and structurally empty Kalshi arrays;
- the 64-target and identifier/provenance limits, exact URL construction,
  TLS and hostname verification, direct no-proxy transport, timeout coverage,
  body, initial/informational-header, and trailer bounds, and no redirects,
  retries, failover, cookies, or ambient credentials;
- the actual production transport code exercised through mocked lower-level
  socket/TLS/HTTP I/O, not only a substituted high-level fake transport;
- body acquisition never started; timeout and transport failure after body
  acquisition starts but before the first byte; normally completed zero-length
  bodies with the actual empty-body digest; retained partial and oversized
  prefixes; and received-versus-retained byte counts;
- normal completion preserved for a confidentiality-suppressed `COMPLETED`
  body; `BODY_EMPTY` for an unsuppressed completed zero-length HTTP 200 response
  with no higher-priority failure; and an empty completed HTTP 404 response
  retaining its empty bytes and digest while receiving
  `HTTP_STATUS_UNSUPPORTED`;
- initial/informational-header-only confidentiality detection and complete,
  partial, and oversized bodies suppressed for confidentiality; exact digest
  scope; raw and mixed JSON-escaped key-ID/signature reflection;
  confidentiality precedence; and suppression from representations and
  serialization;
- valid empty and nonempty trailer sections; discarding trailer-only synthetic
  key-ID or signature reflection without publication or trailer-triggered
  suppression; and continued initial/informational-header and entity-body
  reflection protection;
- exact trailer line-length, nonempty-line-count, and aggregate-byte
  boundaries and their bounded excess cases; elapsed-budget and inactivity
  enforcement during repeated trailer reads; and initiation of no further read
  after budget expiry;
- timeout, transport interruption, over-limit input, and missing trailer
  termination after both zero and nonzero entity-body acquisition; exact
  preservation and digest scope for body bytes already acquired or buffered;
  no trailer contribution to entity-body counts or digests; and no conversion
  of incomplete chunked acquisition to `CAPTURED`;
- no trailer metadata overrides, public or exception leakage, unrestricted
  trailer accumulation, trailer suppression provenance, retries, or extra
  dispatches, plus ordinary later-target continuation after trailer failure;
- `INTEGRITY_FAILURE` detected after complete and partial acquisition,
  including preservation only of independently trustworthy acquisition facts,
  precedence over the ordinary acquisition status, rejection rather than
  serialization when identity or acquisition facts are implicated, continued
  confidentiality precedence, and prohibition on conversion to `CAPTURED`;
- rejection of every contradictory acquisition outcome, retention state,
  failure status, acquisition flag, byte count, body, digest, and suppression-
  source combination;
- stable serialization, process-local trust rejection after copy or transfer,
  repeated-run and hash-seed determinism, and observer-time labeling;
- no entry into replay or any accepted historical trust path;
- no network access anywhere in ordinary capture or regression tests; and
- every protected Milestone 1–4 guarantee and the exact path, import,
  dependency, and artifact boundaries.

Ordinary acceptance tests used only synthetic responses and no actual
credentials or live requests. Offline acceptance established implementation
behavior, not successful real signatures, actual credential validity,
environment or effective permissions, live endpoint availability, deployment
readiness, or successful order-book acquisition. A failure-only live result is
not proof of successful capture.

Implementation acceptance remains distinct from activation, operational
validation, and governance closure. Live-access claims remain unvalidated.
Any later claim that authenticated Kalshi acquisition works live requires a
separately authorized successful demo result for the initial trial; any
Polymarket live-success claim requires a separately authorized production
trial. Neither trial, credentials, deployment, nor production use is
authorized here, and a failure-only result cannot satisfy a live-success
claim. System DNS and caller-owned signer execution still lack a guaranteed
hard deadline, and actual venue trailer behavior remains unknown.

The accepted implementation validation matrix used an identified external
Python 3.11-or-newer toolchain with bytecode and cache output disabled or
redirected outside the repository:

```text
python -m pytest -p no:cacheprovider tests/capture
python -m pytest -p no:cacheprovider
python -m pytest -p no:cacheprovider tests/unit tests/replay tests/relationships tests/discovery tests/constraints tests/opportunities tests/diagnostics
python -m pytest -p no:cacheprovider tests/unit/test_no_network.py
python -m ruff check --no-cache src tests
python -m ruff format --check --no-cache src tests
python -m mypy --strict src/invariant_engine
python -m compileall -q src tests
python -m json.tool fixtures/capture/cases.json
git diff --check
```

The capture suite was also run with `PYTHONHASHSEED=1`, `2`, and `random`, with
external cache locations. Package/import boundaries and repository artifacts
were checked. The independently observed final record was 554 total tests,
including 200 capture and 354 protected Milestones 1–4 tests; 20 external
adversarial probes; one no-network suite; Ruff check and format check; strict
mypy; compilation; all 15 fixture JSON files; and package, dependency,
whitespace, and artifact-hygiene checks. This closure task records those
previously observed results and does not rerun them.

#### Non-goals and stop conditions

Milestone 5 excludes private-key loading, RSA implementation, credential
creation or enumeration, ambient secret discovery, live calls during
implementation or ordinary tests, staging or compatibility origins, market or
token discovery, WebSockets, polling, concurrency, retries, redirects,
failover, replay promotion, cross-venue synchronization, analytics, fees,
relationships, opportunities, strategy evaluation, simulation, risk,
execution, reconciliation, orders, trading, deployment, and Milestone 6 or
later planning or activation.

Future work must stop for unexplained baseline changes, a path or dependency
outside its then-active allowance, missing applicable reviewed evidence, or a
contract that cannot be implemented without an unsupported assumption. It
must report the concrete problem and candidate-source question rather than
expand scope or import current external or unreviewed material.

The bounded trailer-discard amendment and its remediation are completed
historical transitions. Their historical path allowance grants no current
remediation or test authority. Any future remediation requires an explicit
governance transition.

#### Closed governance state

Milestones 1–5 are accepted and closed. Milestone 5 implementation authority
is deactivated and its delivered paths confer no continuing exception. The
accepted Capture v2 extension below had its own governance and left the
Milestone 5 closure intact.

### Milestone 6 — Execution simulation

Model latency, queue assumptions, partial fills, failed legs, cancellations, and residual exposure without sending orders.

#### Synthetic execution scenarios — accepted implementation

The bounded slice was independently accepted and commit-verified. Its
implementation authority is deactivated. The broader Milestone 6 roadmap
remains open and inactive, and every later milestone remains inactive.

The historical pre-activation baseline was Capture v2 closure commit
`40edb4eae7538a6a4ea0f964d5312cf37650624d`, with 102 tracked files and
tracked-content manifest SHA-256
`7407ce55851e88ebc65ad4e00a3dd034ecb664da34883d2bd9be62ba6d10be18`.
The activation draft underwent one governance revision before acceptance.
The verified activation commit `6b8a528c216e9643932b2d41f994be35fd7cf1da`
has that baseline as its parent. A separate explicit prompt tied to the
verified activation commit authorized the bounded implementation and its
temporary path allowance.

#### Permanent public contract

`invariant_engine.simulation.evaluate_scenario(spec)` accepts one deeply
immutable, in-memory synthetic specification and returns an immutable result
or an explicit validation error. The scenario has exactly two labeled buy
legs, A and B. Each starts with zero holdings and has a positive intended
quantity. The caller supplies up to 64 events in their evaluation order and
explicitly states the extent of knowledge at cutoff for each leg, including
fill completeness and, where applicable, whether cancellation completion is
known. The evaluator preserves the supplied order, including interleaving of
the legs. The five approved scenario families are both legs filling, both
legs open with zero confirmed fills through cutoff, either single leg filling
with rejection of the other, uneven partial fills, and cancellation after a
partial fill with or without further fills before cancellation completes.

Every input quantity, fill price, and per-unit payout is a finite,
nonnegative exact `Decimal` with at most 12 integer digits and 8 fractional
digits. Fill quantities must be positive. Fill prices and payouts are
synthetic USD per unit. Exact calculated products and totals can exceed the
input precision or scale limits. Reject malformed nested values and invalid
histories as a whole, with an explicit validation error and no partial
success result.

#### Event transitions and cutoff accounting

| Supplied event | State change for the named leg |
|---|---|
| Initial state | All intended quantity awaits an outcome. Acquired, open, and closed-unfilled quantities are zero. |
| Opening | Move the awaiting quantity to open. |
| Rejection before opening | Move the awaiting quantity to closed unfilled. |
| Fill | Transfer the specified positive quantity from open to acquired at its supplied price, up to the outstanding open quantity. A full fill closes the leg as filled, including while cancellation is pending. |
| Cancellation request | Mark the open leg as pending cancellation. Its remainder stays open and eligible to fill. |
| Cancellation completion | Complete the pending cancellation and move the outstanding remainder to closed unfilled, preserving all earlier fills. |

Reject impossible transitions, including an overfill, filling before opening
or after closure, opening after rejection, rejection after opening, and
cancellation completion without a pending cancellation.

Report both legs' state after every supplied event and at cutoff. Include
intended, acquired, open, closed-unfilled, and awaiting-outcome quantities as
applicable. In each fully known state, acquired, open, closed-unfilled, and
awaiting-outcome quantities sum to the intended quantity. Event snapshots
describe the supplied history. Cutoff reporting also reflects the caller's
declared knowledge. Keep confirmed subtotals when exact cutoff totals are
unavailable, mark the affected totals unavailable with an explanation, and
preserve exact values that the supplied history and cutoff knowledge
establish. Incomplete fill knowledge cannot silently become zero additional
fills. When fill knowledge is complete but cancellation completion is
unknown, the acquired quantity and gross cost can be exact while the split
between open and closed unfilled remains unknown.

Completed cancellation fixes open quantity at zero. If the recorded canceled
remainder is the minimum positive fill quantity (`0.00000001`), an additional
valid fill would have closed the leg as filled and prevented completion of
the cancellation. In that case the remainder, acquired quantity, and gross
cost are exact even when the caller marks fill knowledge incomplete.

Calculate gross USD cost from exact individual fill quantity × price
products and their exact sums. Report confirmed fill costs and exact gross
cost totals wherever established, per leg and across both legs. Arithmetic
must be independent of the caller's decimal context and must leave that
context intact.

#### Hypothetical payouts and trust boundary

An optional table may supply up to 16 uniquely named hypothetical settlement
states with a USD payout per acquired unit for each leg. Calculate exact
gross USD payout from known acquired positions and the supplied per-unit
payouts. Identify unavailable payout totals where unknown positions affect
the calculation. A leg with zero per-unit payout contributes exactly zero.
Every result is explicitly conditional on caller-supplied assumptions and
non-actionable. The table establishes neither real-market equivalence nor
exhaustive settlement coverage.

The evaluator is offline and deterministic, with no file, environment,
clock, random, or network access. Its runtime dependencies are the standard
library and its own simulation package. Exclude venue adapters, live or
historical inputs, capture promotion, fee and net-profit calculations,
liquidation and cash-reuse assumptions, risk decisions, orders, and trading.
Synthetic inputs and results carry no authority into historical,
relationship, opportunity, risk, or execution paths. Empirical latency,
queue position, fill probability, and live sequencing remain deferred.

#### Planner-supplied reviewed evidence

- Reviewed Polymarket US material distinguishes original, filled, and
  remaining quantities, identifies pending cancellation as unprocessed, and
  documents an empty cancellation response (`SRC-0053` / `CLM-0217`–`CLM-0218`,
  `SRC-0054` / `CLM-0220`).
- Reviewed Kalshi material distinguishes immediate fills at placement from
  the remainder canceled at processing (`SRC-0057` / `CLM-0228`, `SRC-0059` /
  `CLM-0234`).

The findings support representing cancellation requests, fills, and
cancellation completion separately. The caller supplies their order. The
planner consulted reviewed Polymarket US, Kalshi, and prediction-market
mechanics synthesis (`PLATFORM-0003`, `PLATFORM-0002`, and `CONCEPT-0002`).
A6 and A7 are addressed solely for the accepted synthetic accounting scope.
The first slice deferred B3, C2, and C3. Keep `invariant-research` outside this work and
return any new source as a candidate only.

#### Delivered implementation paths

The accepted implementation added exactly five files.

- `src/invariant_engine/simulation/__init__.py`
- `src/invariant_engine/simulation/models.py`
- `src/invariant_engine/simulation/evaluator.py`
- `tests/simulation/test_scenarios.py`
- `tests/simulation/test_boundaries.py`

The sole existing-path change was in
`test_only_approved_milestone_2_packages_exist` in
`tests/relationships/test_relationships.py`. It requires the `simulation`
directory and retains the checks that `opportunities` and `diagnostics` exist
and `risk`, `execution`, and `reconciliation` are absent. All other source,
tests, fixtures, configuration, and dependencies remained protected. These
delivered paths confer no continuing authority or path exception. Any future
implementation change requires an explicit governance transition.

#### Acceptance examples

Both legs have 10 intended units. All example fills are at $0.40 per unit
for A and $0.50 per unit for B. Pairs are in A/B order. The outcomes shown
assume the stated events and complete cutoff knowledge.

| Supplied outcome | Acquired | Open | Closed unfilled | Gross cost |
|---|---:|---:|---:|---:|
| Both fill | 10/10 | 0/0 | 0/0 | $9.00 |
| Both open, zero fills confirmed through cutoff | 0/0 | 10/10 | 0/0 | $0.00 |
| A fills, B rejected | 10/0 | 0/0 | 0/10 | $4.00 |
| B fills, A rejected | 0/10 | 0/0 | 10/0 | $5.00 |
| Uneven partial fills, remainders open | 6/4 | 4/6 | 0/0 | $4.40 |
| A fills, B fills 3, B cancellation requested and completed | 10/3 | 0/0 | 0/7 | $5.50 |
| Same sequence with 2 additional B units filled while cancellation is pending | 10/5 | 0/0 | 0/5 | $6.50 |

#### Independent implementation acceptance

Independent review accepted the exact candidate after one implementation
remediation pass for the minimum-fill cancellation case. The original
implementation marked exact cutoff totals unavailable when the leg's
completed cancellation and minimum-size remainder ruled out an additional
fill. The unchanged external probe reproduced the original defect and passed
on the fix. The earlier governance-draft revision is counted separately from
the implementation remediation.

The accepted implementation was commit-verified at
`ac9c512ebcd96d2ce11a9c7bb93a2097fb74e61b`, with activation parent
`6b8a528c216e9643932b2d41f994be35fd7cf1da` and tree
`0a2dccb2360a360943745a03436662cad6b0a9d8`. The 107-file implementation
manifest SHA-256 is
`cf60dd53a23f4ef877de3c0b752298a3420386025ec09b676a1a9dd94929bc74`.
The six-file change manifest SHA-256 is
`1460d8aa8d759bb849015d54d963bf7912c93f5e46add6cbf7a96661f5379a9d`.
Both manifests use the accepted implementation bytes for their respective
path sets. Each bytewise-sorted relative path has a line containing the
file's lowercase SHA-256, two spaces, the pathname, and a newline.

Independent implementation review recorded 690 passing tests under each of
`PYTHONHASHSEED=1`, `2`, and `random`, including the protected Milestones 1–5
and Capture v2 suites. The network audit observed zero attempts across 30
Python processes. Ruff lint and formatting, strict mypy, compilation, and
all 15 fixture JSON parses passed. These results belong to implementation
review. This documentation pass uses document-level checks.

#### Verified documentation closure of the first slice

The historical gate required independent review of the two documents and
their binary diff, user commit and push of the accepted documents, and
verification against their accepted identities. The verified closure commit
`8eacb5f7ac5b795c2e4634d24fa8efebfceb6587` has parent
`ac9c512ebcd96d2ce11a9c7bb93a2097fb74e61b` and tree
`46f5246530a291bfac886d24a496a8523c79cf13`. Only the two documents changed.

| Closure material | SHA-256 |
|---|---|
| `AGENTS.md` | `1091f158598a488195a33674d02a1ade69506b5723431224c47f04f5107c0dc0` |
| `PLAN.md` | `2ac6e2a8bc6d637f449f1cd238651e45b87d536f6a1080850bb35cea7af9b165` |
| Parent-to-closure binary diff | `1b9d9aded9e03a52e0764ef896543aec1de57dceeff5454773b8dc31b974b583` |

#### Final slice activation draft — Offline delay and queue comparison

Compare conditional outcomes by varying caller assumptions across runs of
`invariant_engine.simulation.queue.evaluate_queue_scenario(spec)`. Each
call evaluates one in-memory synthetic scenario. The verified first-slice
closure on engine `main` is the draft baseline. Its 107-file tracked-content
manifest SHA-256 is
`48873a67c1b8045c8d0b25f7f44f9e018f67db5c87767d443b3ccf8e26f08ae5`.

**Inputs and time.** Buy legs A and B start with zero holdings. Each has
its own queue, fixed USD price per unit, positive intended quantity,
submission time, processing delay and opening or rejection outcome. That
outcome takes effect at submission time plus processing delay. For an
opening, the caller supplies the volume ahead at entry. Each leg permits
up to 29 timed incoming sell-volume events and at most one cancellation
request with its own request time and assumed processing delay. Completion
is due at request time plus that delay. All times and delays are nonnegative
integer milliseconds. Both legs share one inclusive cutoff. Process events
at the cutoff in their specified order. Later events have no effect on the
cutoff state.

Apply the accepted evaluator's input limits to quantity, volume and price.
Use finite nonnegative exact `Decimal` values with at most 12 integer digits
and 8 fractional digits. Preserve exact intermediate quantities, products
and totals independently of the caller's decimal context.

**Matching and ordering.** Process events chronologically. At the same
millisecond on one leg, the caller must explicitly order the events,
including processing outcomes, sell arrivals, requests and completions.
Reject unresolved ties and impossible sequences as a whole. At a shared
millisecond display A's events before B's, preserving each leg's order.

- Sell volume arriving before opening passes unused. At opening initialize
  the queue ahead to its supplied entry value. A rejected leg acquires zero.
- While open or pending cancellation, subtract the lesser of incoming
  volume and remaining volume ahead from both. Use any excess to fill up to
  the leg's remaining quantity at its fixed price. Carry the reduced queue
  ahead and order remainder into the next event. Excess after a full fill
  passes unused. Volume after closure also passes unused. Each unit belongs
  to one arrival on one leg and is accounted for exactly once.
- A cancellation request requires an open leg. It leaves the unfilled
  quantity eligible until completion closes the remainder. A full fill
  while pending closes the leg as filled and supersedes the scheduled
  completion. A request made by cutoff remains pending at cutoff if the leg
  still has a remainder and completion is due later.

**Trace and accounting.** Return an immutable trace. For each incoming
event through cutoff, identify its time and leg and account for its volume
as the exact sum consumed ahead, filled and unused. Include the ordered
derived accounting events and the immutable result of passing them to
`invariant_engine.simulation.evaluate_scenario` with the intended quantities
and complete knowledge of the modeled fills through cutoff. For a pending
request, report that completion is known to be outstanding. Emit at most one
positive fill per arrival. Each leg contributes at most 29 fills, one
opening or rejection, one request and one effective completion. Together
these fit the accepted 64-event bound. Submission, unused volume and
queue consumption alone do not generate accounting events.

The result is deterministic, offline, explicitly conditional on caller
assumptions and non-actionable. Runtime dependencies are the standard
library, the two new modules and the accepted public simulation API.
Exclude file, environment, clock, random and network access, venue APIs,
capture and historical inputs, credentials, empirical fill probabilities,
risk authorization, orders and trading. Synthetic traces and results carry
no authority into protected trust paths.

**Evidence.** The planner consulted `PLATFORM-0003`, `PLATFORM-0002` and
`CONCEPT-0002`. Reviewed Polymarket US material distinguishes pending
cancellation from completed processing (`SRC-0053` / `CLM-0217`–`CLM-0218`,
`SRC-0054` / `CLM-0220`). Reviewed Kalshi material distinguishes immediate
fills from the remainder canceled at processing (`SRC-0057` / `CLM-0228`,
`SRC-0059` / `CLM-0234`). These findings support distinct request, fill and
completion events. Entry queue, queue priority and processing delays are
explicit synthetic assumptions. C2 empirical calibration remains deferred.
C3 is addressed only for this selected synthetic queue rule. Keep
`invariant-research` outside builder access.

**Acceptance comparisons.** B opens for 5 units. A single sell event of
6 units arrives on B at 20 ms. The cutoff follows all listed events.

| Units ahead at entry | Cancellation effective | B fills | B canceled |
|---:|---:|---:|---:|
| 3 | 10 ms | 0 | 5 |
| 3 | 30 ms | 3 | 2 |
| 8 | 30 ms | 0 | 5 |

For the middle case, a request at 25 ms with a 5 ms delay permits moving
only the opening from before the sale to 21 ms. The 6 units then pass
unused, B fills zero and all 5 units are canceled. For the tie comparison,
B is open with 3 units ahead and cancellation pending at 20 ms. Completion
then sale yields 0 filled and 5 canceled. Sale then completion yields
3 filled and 2 canceled.

**Independent implementation review.** Check the comparisons above, repeated
and fractional arrivals, exact queue exhaustion, surplus after full fill,
full fill while pending, rejection, unresolved ties, impossible sequences,
cross-leg ordering and independence, and events immediately before, at and
after cutoff. Check both the maximum-size scenario and rejection of excess
inputs. Independently replay the derived events through the accepted public
accounting API and compare the complete result, including states, quantities
and gross USD costs. Check per-arrival conservation and cumulative totals
under altered decimal precision, rounding and traps. Verify the caller's
decimal context is preserved.

Review the exact implementation candidate against the verified activation
commit. Record separate SHA-256 manifests for the complete 110-file candidate
(107 baseline paths plus three additions) and the three added files alone.
Include the new files even before staging. Exclude ignored files and leave
`.env` unread.
For each set use bytewise-sorted relative paths, one lowercase file SHA-256,
two spaces, the pathname and a newline per entry. Hash the manifest bytes.
Verify protected files against the activation tree. Run the new tests and
every protected suite, including first-slice simulation, Milestones 1–5 and
Capture v2. Repeat the full suite with `PYTHONHASHSEED=1`, `2` and `random`
and compare deterministic traces and results. Audit network attempts across
the test processes and their Python children and require zero attempts.
Carry forward Ruff lint and format checks, strict mypy, compilation, fixture
JSON parsing, whitespace and artifact checks. Record observed results with
the exact candidate and verify the accepted manifests against the resulting
implementation commit, parent and tree.

**Delivery and activation gate.**

1. Independently review the unstaged, uncommitted `AGENTS.md` and `PLAN.md`
   against baseline `8eacb5f7ac5b795c2e4634d24fa8efebfceb6587`. Examine the
   full binary diff and changed paths and run `git diff --check`. Accept
   or reject the exact content. On acceptance record both document SHA-256
   values and the SHA-256 of the raw `git diff --binary` output against
   that baseline for those two paths.
2. After independent acceptance, the user commits and pushes only the two
   accepted documents.
3. Verify the activation commit and tree on engine `main`, its exact baseline
   parent, the two changed paths, committed document hashes and
   parent-to-commit binary diff digest against the reviewed identities.
4. A separate implementation prompt naming the verified activation commit
   may then authorize exactly three new files:

   - `src/invariant_engine/simulation/queue.py`
   - `src/invariant_engine/simulation/queue_models.py`
   - `tests/simulation/test_queue.py`

   Every existing implementation file and test is protected, including the
   simulation package exports, models, evaluator and boundary tests. The
   allowance excludes changes to fixtures, dependencies and configuration.
5. Independent implementation acceptance, commit verification and subsequent
   documentation closure of this final slice complete Milestone 6 at the
   agreed scope. Implementation and operational authority remain inactive
   during this draft. Later milestones require separate governance.

### Milestone 7 — Deterministic risk gateway

Add independent limits, stale-data rejection, minimum-edge requirements, exposure controls, strategy enablement, and kill switches.

### Milestone 8 — Restricted venue-local execution

Enable one venue and one validated strategy class with tightly limited capital through the risk gateway.

### Milestone 9 — Cross-venue execution

Add cross-venue execution only after venue-local execution and reconciliation are reliable.

## Evidence dependencies and deferred research

These items identify evidence and design dependencies. The accepted bounded
Milestone 6 slice records the synthetic accounting decisions for A6 and A7.
Wider decisions remain open. Reclassification alone grants no authority to
make assumptions, change milestone scope, or satisfy acceptance criteria.
Excluding a required capability requires an explicit governance decision.

Dependencies apply only to the markets, operations, and strategies actually
supported; they do not require universal answers. Mutable venue facts require
scoped, dated verification. Failure or refusal alone does not satisfy a
milestone whose accepted purpose requires a working capability. These
classifications do not establish new milestone acceptance criteria. Do not
invent answers to these questions.

### Polymarket US future access questions

This subsection records access questions for possible future Polymarket US
work. It does not reclassify or modify any of the 23 existing A–D topics
below, activate implementation, or retroactively make deferred access
questions blockers for the bounded public REST capture recorded later in this
document.

The supplied reviewed evidence records that the retail public market-data
gateway at `https://gateway.polymarket.us` is key-free for the documented
public operation. Public REST capture therefore does not presently require an
API key under that evidence. The same evidence records that future retail
WebSockets, account or portfolio access, and trading require authentication
and introduce credential, onboarding, identity-verification, permission, and
effective-access dependencies. Broad authentication wording coexists with the
explicit public-operation exemption; the exemption must remain scoped to the
documented public REST operation rather than generalized to other interfaces.
No self-service retail demo equivalent to Kalshi demo has been verified.

The following URLs are candidate-source leads only. They have not been
ingested and reviewed for this engine proposal and are not implementation
authority:

- `https://docs.polymarket.us/trader-guide/environments` appears to document
  Exchange development and pre-production environments and onboarding-based
  access.
- `https://docs.polymarket.us/trader-guide/api-overview` appears to distinguish
  Exchange or direct-access APIs from retail APIs.
- `https://docs.polymarket.us/trader-guide/authentication` appears to describe
  separate environment onboarding and Exchange authentication.

The open access question is: can this user's intended retail integration
access a suitable testing environment, or would separate Exchange onboarding
and a different integration be necessary? Do not assume that retail
credentials work on Exchange endpoints, that the interfaces are
interchangeable, or that the user qualifies for access. Any new external
finding must return through research ingestion and review before it can become
implementation authority.

### A. Decisions needed for remaining capabilities

These are bounded decisions for a supported capability, not requirements for
a universal natural-language proof system.

| # | Topic and affected capability | Trigger | Required evidence or decision | Status |
|---:|---|---|---|---|
| A1 | State-space completeness for real market rules; relationship certification for each market admitted to the supported strategy. | A strategy admits a real market to deterministic certification. | What review evidence establishes complete payoff states for each admitted market, including applicable cancellation, void, refund, and edge-case states? | Unresolved decision. |
| A2 | Certificate invalidation after conflicting or changing resolution rules; certificate trust. | Evidence shows that resolution rules conflict with or materially change the rules bound by a certificate. | Decide the fail-closed invalidation conditions and the evidence that demonstrates them for affected certificates. | Unresolved decision. |
| A3 | Certificate versioning after amended venue rules; certificate identity and lifecycle. | A venue amends rules material to a supported certificate. | Decide how amended rules produce, supersede, or retire certificate versions while preserving time-scoped provenance. | Unresolved decision. |
| A4 | Safe asynchronous cross-venue observations; cross-venue analytics. | A supported analytical or later execution capability uses observations that are not exactly synchronized. | Decide the bounded safety policy and supporting evidence for acceptable timing, staleness, and failure handling. | Unresolved decision. |
| A5 | Inventory and collateral requirements; supported strategy economics, simulation, risk, and execution. | A selected supported strategy or venue operation consumes inventory or collateral. | Establish the exact, time-scoped requirements and how available inventory and collateral are represented and checked. | Unresolved decision. |
| A6 | Partial-fill economics; execution simulation. | A supported simulation capability models less than complete fills. | Decide the exact economic accounting across supported partial-fill states without inventing fill behavior. | The accepted slice covers caller-supplied synthetic fills and gross accounting. Wider economics remain open. |
| A7 | Safe execution sequencing; multi-leg execution simulation and later execution. | A supported strategy requires multiple non-atomic operations. | Decide which sequences are permitted and how failures, cancellations, exposure, and venue constraints are evaluated. | The accepted slice covers validation of caller-supplied synthetic event order and cancellation accounting. Live sequencing remains deferred. |
| A8 | Cross-venue settlement differences; cross-venue strategy economics, risk, and reconciliation. | A supported strategy spans venues with distinct settlement processes. | Establish the applicable settlement rules, timing, failure states, and reconciliation treatment for the selected markets and operations. | Unresolved decision. |
| A9 | Economic finality and cash availability; settlement, reconciliation, and reusable-capital accounting. | A supported capability relies on a result being economically final or funds being available for reuse. | Decide the exact, venue- and operation-specific evidence for finality and cash availability. | Unresolved decision. |

### B. Venue contracts requiring scoped verification

These mutable venue facts require dated verification for the exact interfaces,
operations, and effective periods used by the selected capability.

| # | Topic and affected capability | Trigger | Required evidence or decision | Status |
|---:|---|---|---|---|
| B1 | Fill-history semantics; reconciliation of supported orders. | The selected capability must retrieve and reconcile fills for its supported order operations. | Verify which fill identifiers, corrections, ordering, and retrieval semantics are needed for that reconciliation, without presuming that any particular venue behavior exists. | Scope-specific verification required. |
| B2 | Current venue schemas; selected capture, execution, or reconciliation interfaces. | A selected capability consumes a venue interface. | Verify the exact request, response, event, versioning, and compatibility schemas used by its supported operations for the applicable effective period. | Scope-specific verification required. |
| B3 | Current venue fee schedules; selected economics, simulation, risk, or execution operations. | A selected capability requires fees for specified venues, markets, roles or sides, operations, and times. | Verify the exact effective fee policies, formulas, scopes, rounding, currency, and provenance applicable to those operations and periods. | Deferred for this slice. Scope-specific verification required if triggered. |

### C. Dependencies triggered by a design choice

These dependencies do not choose a design or authorize implementation.

| # | Topic and affected capability | Trigger | Required evidence or decision | Status |
|---:|---|---|---|---|
| C1 | WebSocket gap recovery; streaming market-data capture and state reconstruction. | Streaming market data is selected. | Define the venue- and channel-specific sequence, gap detection, recovery, replay-validity, and fail-closed semantics. | Conditional dependency. |
| C2 | Latency distributions; calibrated latency analysis or simulation. | The design makes calibrated latency claims. | Supply empirical, scope-matched evidence for the claimed distributions. Explicit scenario assumptions must be labeled and are not empirical estimates. | Empirical calibration deferred. Final-slice processing delays are caller assumptions. |
| C3 | Queue position and fill probability; execution simulation. | The selected simulation design models queue position or fill probability. | Define the selected simulation model and the evidence needed for any empirical or predictive claim; do not silently assume full fills or a queue model. | Addressed only for the selected final-slice synthetic queue rule. Empirical queue position and fill probability remain deferred. |
| C4 | Borrowing and short-sale mechanics; strategy economics, simulation, risk, and execution. | An authorized strategy depends on borrowing or shorting. | Verify the exact permitted mechanics, availability, costs, collateral, lifecycle, and failure handling for the supported venue operations. | Conditional dependency. |
| C5 | Complement conversion; strategy economics, simulation, risk, and execution. | An authorized strategy depends on conversion. | Verify the exact conversion eligibility, mechanics, timing, costs, identifiers, settlement effects, and failure handling. | Conditional dependency. |
| C6 | Capital-transfer constraints; available-capital accounting and cross-venue strategy operation. | The design relies on capital movement. | Define transfer timing, limits, costs, failure and finality semantics, and accounting. Cross-venue execution does not inherently require transfers during execution; prefunded venues still require separate available-capital accounting. | Conditional dependency. |

### D. Deferred capability and research extensions

These extensions do not block the currently bounded roadmap unless the
corresponding capability is explicitly added. They remain unresolved and all
existing exclusions remain in force.

| # | Topic and affected capability | Trigger | Required evidence or decision | Status |
|---:|---|---|---|---|
| D1 | Natural-language relationship validation beyond explicit review; expanded relationship-validation automation. | That capability is explicitly added. | Decide how natural-language meaning could be validated without allowing a model or discovery provider to bypass explicit review and deterministic certification. | Deferred extension. |
| D2 | A labeled benchmark for LLM-assisted discovery; empirical discovery evaluation. | Production-relevant LLM discovery evaluation is explicitly added. | Establish a separately governed, representative labeled benchmark with provenance and leakage controls. | Deferred extension. |
| D3 | Precision and reviewer-load thresholds for LLM discovery; discovery-governance decisions. | Production use or acceptance thresholds for LLM discovery are explicitly considered. | Decide the evidence-backed precision and reviewer-load thresholds; existing synthetic measurements remain non-authoritative. | Deferred extension. |
| D4 | Conditional relationships; relationship modeling, certification, compilation, and evaluation. | Conditional-relationship support is explicitly added. | Define representation, complete payoff semantics, deterministic validation, constraint semantics, and fail-closed boundaries. | Deferred extension. |
| D5 | Scalar payouts; relationship modeling, certification, compilation, and evaluation. | Scalar-payout support is explicitly added. | Define exact payout representation, units, state spaces, deterministic validation, and constraint semantics without approximating binary unit payouts. | Deferred extension. |

## Capture v2 — accepted and closed bounded capture extension

### Contract status and effect

This documentation records the completed activation, accepted implementation,
and successful required operational trial for the separate bounded extension
named Capture v2. It is not Milestone 6 and does not reopen or renumber
Milestone 5. Capture v2 implementation and operational authority are
deactivated. Milestones 1–5 remain accepted and closed. The historical
Capture v2 closure granted no implementation or operational authority for
the separate Milestone 6 synthetic slice.

Every Capture v2 restriction below is a local engineering policy under
uncertainty, not a universal Polymarket US, international Polymarket, or Kalshi
venue contract.

The accepted outcome extends bounded capture support to the Polymarket US
retail public order-book operation while preserving all accepted international
Polymarket and Kalshi behavior. Inputs are explicit caller-supplied Polymarket
US market slugs in immutable capture specifications. There is no automatic
event or market discovery. Each target ends in either a distinct US-native
captured order book or an explicit terminal failure, with immutable
acquisition provenance and retained raw evidence under the accepted Milestone
5 confidentiality and retention rules.

### Supplied reviewed evidence and limits

The planner consulted research commit
`add0b312e5788e0cbabf8a2d35476141872f7da8`, including
`wiki/platforms/polymarket-us.md` (`PLATFORM-0003`), the corresponding
`SRC-0046` through `SRC-0049` source summaries, and
`registry/sources.yaml`, `registry/pages.yaml`, and `registry/claims.yaml`.
Those research files were not accessed during this task. Local origin
alignment for that research repository has not established that the supplied
research commit was pushed. The documentation was captured on 2026-09-07 and
reviewed on 2026-09-09. This accepted contract relies only on the supplied
reviewed findings below:

- `SRC-0046` / `CLM-0200`: the retail public market-data gateway is
  `https://gateway.polymarket.us` and is documented as key-free.
- `SRC-0047` / `CLM-0201`–`CLM-0202`: trading, portfolio access, and
  WebSockets require authentication. API-key onboarding describes account
  creation, identity verification, developer-portal sign-in, and Key ID and
  Secret Key issuance. Broad authentication wording coexists with the
  explicit public exemption, so neither statement may be generalized beyond
  its documented scope. The reviewed material proves neither credential scope
  nor account eligibility.
- `SRC-0048` / `CLM-0203`: an event may contain multiple markets, and the US
  order-book operation uses a market slug rather than an international CLOB
  token identifier.
- `SRC-0049` / `CLM-0204`–`CLM-0207`: the documented operation is
  `GET https://gateway.polymarket.us/v1/markets/{slug}/book` on the production
  server with `security: []`. Documented response properties include
  `marketData.marketSlug`, `bids`, `offers`, `state`, `stats`, and
  `transactTime`. Book entries define `px` and string `qty`. `Amount` requires
  `value` and `currency`; `value` is declared to be a decimal string even
  though an example shows an unquoted JSON number. Other response objects do
  not explicitly require their properties.

The string declaration and numeric example are inconsistent. The reviewed
material also does not establish a complete numeric grammar, level ordering,
duplicate-level semantics, freshness, atomicity, or a mapping from a side to
an outcome. These absences must remain explicit. A local parser contract may
be narrower than the venue, but it must be labeled as an engineering policy
under uncertainty rather than a venue guarantee or a resolution of the source
inconsistency.

An independent diagnostic—not an engine acceptance test—successfully fetched
the user's US event and one public order book without credentials on
2026-09-15. The order-book request returned HTTP 200, its market slug matched
`paccc-usse-midterms-2026-11-03-dem`, and the observed prices and quantities
were strings. This observation is not ingested source authority, a permanent
wire-format guarantee, proof of engine support, or the separately authorized
engine-based trial recorded below.

### Exact accepted local Polymarket US policy

Every restriction in this subsection is a local engineering policy under
uncertainty, not a universal venue contract. Only the exact production public
operation is supported:

`GET https://gateway.polymarket.us/v1/markets/{caller_supplied_slug}/book`

The caller provides every market slug explicitly in an immutable,
ordered, versioned capture specification. Event lookup, event-to-market
expansion, automatic discovery, and identifier translation are excluded. The
target identity binds a distinct Polymarket US venue value, production
environment, exact gateway origin, exact market slug, position, fixed limits,
and ordered provenance. The response identity must contain
`marketData.marketSlug` exactly equal to the requested slug. Identity mismatch
produces the existing explicit terminal mismatch class rather than a
capture.

A successful output uses a distinct US-native captured-book model. It
preserves native `bids` and `offers`, every received level in received
order, duplicate levels, each `px.value` textual representation and currency,
each `qty` textual representation, and exact `Decimal` interpretations only
after lexical validation. It does not call offers international asks, assign
outcome semantics to either side, sort or aggregate levels, infer tie
semantics, or convert the slug to an international market, condition, or token
identifier. `state`, `stats`, and `transactTime` remain in retained raw
evidence without normalized fields or inferred semantics.

The exact identity policy is:

- `Venue.POLYMARKET_US = "polymarket_us"`, distinct from international
  `Venue.POLYMARKET = "polymarket"`;
- production only;
- exact origin `https://gateway.polymarket.us`;
- exact GET path `/v1/markets/{slug}/book`; and
- ASCII slug full-match `[a-z0-9][a-z0-9-]{0,127}`.

There is no normalization, trimming, case conversion, query, percent encoding,
slash, fragment, arbitrary URL, or origin override.

The exact required response structure is a top-level JSON object containing
an object `marketData`. `marketData` must contain exact-string `marketSlug` and
exact-array `bids` and `offers`. Every level must be an object containing
object `px` and exact-string `qty`; `px` must contain exact-string `value` and
exact-string `currency`. Currency must equal `USD` and is preserved on every
level. Missing, null, wrong-type, or unsupported-currency material fails schema
validation; values are neither coerced nor fabricated. Empty arrays are
structurally permitted without economic interpretation. Required structure
and numeric fields are validated before reporting an otherwise well-formed
response-slug mismatch.

Price and quantity strings are at most 64 ASCII characters and must full-match
`(?:0|[1-9][0-9]*)(?:\.[0-9]{1,18})?`. Signs, whitespace, exponents,
leading-zero variants, non-finite values, Unicode digits, and JSON numbers are
rejected. Accepted strings are parsed directly to exact `Decimal` without
binary floating point or rounding. Original strings, including trailing
fractional zeros, are preserved. No added price upper bound, tick-validity
rule, or integer-only quantity assumption applies. Zero is structurally
permitted without assigned economic meaning. These rules do not alter the
accepted Kalshi or international Polymarket numeric policies. Schema-first
rejection of the reviewed numeric example does not resolve its documentary
inconsistency.

The frozen US-native models are:

- `PolymarketUSPriceLevel(price_text, quantity_text, currency, price,
  quantity)`; and
- `PolymarketUSOrderBook(market_slug, bids, offers)`.

Both `bids` and `offers` must remain exact tuples, and every element must remain
an exact `PolymarketUSPriceLevel`. During issuance and every subsequent attempt
and batch trust validation, `market_slug`, `price_text`, `quantity_text`, and
`currency` must remain exact strings; `price` and `quantity` must remain exact
`Decimal` values; both native strings must still satisfy the approved grammar;
and each `Decimal` value and scale must remain exactly consistent with its
preserved native string. Currency must remain exactly `USD`, and book identity
must remain consistent with the target and response. Lists, dictionaries,
equivalent strings substituted for `Decimal`, relevant subclasses, and
mutation of either ladder or either price or quantity representation revoke
attempt and batch trust. Public capture serialization must revalidate these
nested requirements and raise `CaptureSerializationError` rather than emit
unchanged bytes from invalid native material.

Immutable tuples retain received order and duplicate levels. Existing
`PriceLevel` and historical order-book models are unchanged. `state`, `stats`,
`transactTime`, and every other extra field remain only in raw evidence, with
no normalized fields or semantic interpretation. The accepted strict UTF-8,
strict JSON, duplicate-key, and global structural limits apply to the complete
payload, including ignored fields. Existing closed JSON, schema, identity,
transport, and integrity classifications and precedence are reused; no new
public status is introduced.

### Exact v1/v2 batch, version, transport, and authentication contract

The existing public `capture_batch` interface and capture-specification model
remain in place. Existing dataclass fields and public signatures are preserved
where applicable.

V1 retains the current values of every existing schema constant and preserves
unchanged international Polymarket production, Kalshi demo, and Kalshi
production behavior. V1 rejects every Polymarket US target.

V2 defines these exact additional constants:

- `CAPTURE_SPECIFICATION_SCHEMA_VERSION_V2 = "capture-specification-v2"`;
- `CAPTURE_RESULT_SCHEMA_VERSION_V2 = "capture-result-v2"`.

V2 permits any nonempty combination of Kalshi demo, Kalshi production, and
Polymarket US production targets, including a single-venue batch. It excludes
international Polymarket. Every batch contains 1 through 64 targets and is
attempted sequentially in caller order. Every target receives exactly one
logical attempt and at most one dispatch. There is no automatic splitting,
upgrading, discovery, retry, or synchronization. Existing duplicate-target
rejection and continuation after ordinary target failure remain unchanged.

The complete specification and all authentication bindings must validate
before any signing or dispatch. An invalid later target invalidates the entire
specification. A validated specification selects its batch and attempt result
version. A completed batch must have matching specification, batch-result, and
attempt versions; mixed-version attempts and version mutation are rejected.

Inputs that fail specification validation retain the existing sanitized v1
`SPECIFICATION_INVALID` outer-failure envelope: no specification,
fingerprint, attempts, or provenance is published. This is a version-neutral
rejection, not acceptance or conversion of the rejected input. After
successful specification validation, an outer authentication or integrity
failure uses the selected result version while preserving the existing
sanitized outer-failure shape.

Versions are bound into the existing fingerprints, identities, and
process-local trust commitments. Exact v1 bytes and identities must remain
unchanged for identical valid v1 inputs, response bytes, clock values, and
signing outputs. No implicit conversion or trust transfer is permitted.

The accepted bounded implementation has these permanent requirements:

- for Polymarket US targets, use only the production public gateway and exact
  GET operation above;
- for Polymarket US targets, send no credentials or authentication headers and
  provide no authentication fallback;
- preserve the accepted finite, serial, caller-ordered logical-attempt model,
  with at most one dispatch per target and no retry;
- reuse the accepted direct standard-library transport, TLS verification,
  timeout, elapsed-budget, header, trailer, body, confidentiality,
  acquisition, retention, digest, and safe-error behavior where feasible;
- preserve native bids and offers, currency, exact numeric representations,
  received order, duplicate levels, raw response evidence, and ordered
  provenance;
- require exact response-identity matching as a local safety policy after
  required structure and numeric validation;
- fail closed for unknown versions, unsupported venue/environment/origin
  combinations, malformed or missing locally required structure, numeric JSON
  where strings are required, unknown currency treatment, identifier
  mismatch, or any unsupported assumption; and
- keep capture artifacts separate from historical or replay trust,
  relationships, constraints, evaluations, opportunities, strategy
  validation, simulation, risk, execution, orders, and trades.

These Polymarket US-specific gateway and no-authentication restrictions do not
alter signed Kalshi demo and production support in mixed v2 batches.

No parser, target, order book, provenance record, or serialized value may
alias international Polymarket and Polymarket US. No transport redesign is
authorized. Reuse the accepted transport and every body,
initial/informational-header, trailer, confidentiality, deadline, acquisition,
retention, digest, and safe-error rule. This includes the 1 MiB body limit,
bounded reads, strict JSON, 20-second engine-controlled elapsed budget,
5-second operation limits, and documented system-DNS and external-signer
deadline limitations.

Capture paths dispatch explicitly by supported venue and do not rely on
“not international Polymarket therefore Kalshi” fallthrough. Standalone
transport validation for US constructs a valid US-capable contract without
weakening actual batch version validation or changing the public transport
signature.

US requests receive no authentication headers, signer, or confidentiality
values. Supplied authentication material is rejected at the US transport
boundary. Batch authentication bindings must exactly cover the Kalshi
environments present, as in v1. A US-only batch requires no bindings. A mixed
batch must never transmit Kalshi authentication material to a US target.
Missing, extra, duplicate, or misbound bindings fail before requests. Existing
signing bytes, redacted representations, detached caller exceptions, and
confidentiality protections remain unchanged.

Explicit exclusions are WebSockets; account or portfolio access; credential,
secret, private-key, or signer implementation; institutional Exchange or
direct-access integration; assumptions about development, pre-production,
staging, or retail credential portability; event or market discovery;
retries; polling; concurrency; redirects; failover; analytics; replay
promotion; historical normalization; simulation; orders; trading; deployment;
and any Milestone 6 or later behavior.

### Historical delivered paths and former implementation allowance

The activation transition temporarily authorized the following 19 delivered
paths. It also permitted `tests/unit/test_no_network.py` only if needed; that
path remained unchanged. The former allowance and the delivered paths confer
no continuing implementation authority or path exception.

Historical delivered source paths:

- `src/invariant_engine/domain/ids.py`: added the distinct Polymarket US venue
  identity without changing the meaning of existing identities.
- `src/invariant_engine/capture/models.py`: added the US-native immutable models,
  exact venue-to-model integrity checks, and approved v1/v2 schema handling.
- `src/invariant_engine/capture/specification.py`: added the exact US origin,
  explicit venue/environment binding, approved slug validation, and exact
  request path while removing any reliance on venue fallthrough.
- `src/invariant_engine/capture/parsing.py`: added the separate strict US parser,
  response-identity check, schema-first string-decimal policy, and native
  bids/offers preservation.
- `src/invariant_engine/capture/transport.py`: recognizes the US target as an
  explicitly anonymous exact-origin request while preserving all accepted
  transport limits and rejecting unsupported venues.
- `src/invariant_engine/capture/batch.py`: routes approved specification/result
  versions and the new parser result through the existing one-attempt flow
  without adding retries, credentials, or transport behavior.
- `src/invariant_engine/capture/__init__.py`: exports only the approved public US
  models, origin, and schema symbols.

Historical delivered test paths:

- `tests/unit/test_domain.py`: proves that international Polymarket and
  Polymarket US identities are distinct and serialize distinctly.
- `tests/unit/test_venues.py`: proves the accepted historical international
  venue parser does not accept or reinterpret US material.
- `tests/capture/conftest.py`: provides synthetic US targets and response bytes
  for offline tests only.
- `tests/capture/test_specification.py`: covers origin, environment, slug,
  duplicate identity, exact type, version, mixed-batch, and unsupported-venue
  rejection.
- `tests/capture/test_authentication.py`: proves US targets require and transmit
  no authentication and cannot consume Kalshi bindings.
- `tests/capture/test_transport.py`: covers exact method/origin/path, empty
  authentication material, one dispatch, and preservation of every accepted
  transport bound without live network access.
- `tests/capture/test_parsing.py`: covers US success; identity mismatch;
  exact-type failures; missing and malformed local schema; string-only decimal
  values; currency preservation; received order; duplicate levels; and lack
  of invented side, freshness, or atomicity semantics.
- `tests/capture/test_batch.py`: covers success and every applicable terminal
  failure, ordinary continuation, no credential fallback, no unsupported-
  venue fallthrough, and no promotion into another trust domain.
- `tests/capture/test_serialization.py`: covers v1 byte stability, v2 stable
  ordering and identity, native representation preservation, and exclusion of
  runtime trust.
- `tests/capture/test_trust_boundaries.py`: covers exact-type enforcement,
  mutation, copy, reconstruction, pickle, JSON transfer, and process-local
  trust for the new model and versioned result.

Historical delivered fixture paths:

- `fixtures/capture/README.md`: documents the synthetic US case and denies live,
  credential, replay, and venue-guarantee status.
- `fixtures/capture/cases.json`: contains a minimal synthetic US response that
  exercises native market-slug identity, bids/offers, string values and
  quantities, currency, received order, and duplicates.

No dependency was added. `pyproject.toml`, environment files,
`src/invariant_engine/capture/authentication.py`,
`src/invariant_engine/capture/serialization.py`, shared serializers,
historical venue and replay code, relationship and evaluation code, and every
other source, test, or fixture path remained protected. The new venue enum does
not enable US capture material to enter a historical trust path. Any future
correction, test change, or implementation work requires a new explicit
governance transition; this historical path list is not permission to edit.

### Historical activation, acceptance, operational trial, and closure

Capture v2 activation completed at governance commit
`2214b0459542d987b41d0af14d63653b8f707194`, parent
`8a18f40ec74be348d59832282ac12650d5cd15a6`, tree
`004e5faac8a32fbbd5e1e442b0680e9aff47c759`. The independently accepted
activation-content identities were:

- `AGENTS.md` SHA-256
  `775149f8e2a11dfbe9f59488e92b8f882d413a802565f7e4d60a00a738c26700`;
- `PLAN.md` SHA-256
  `9af07eae94802887ac97f051c05862515010e84f6aec128fe021f8f51a2ef36b`;
  and
- parent-to-commit binary governance-diff SHA-256
  `60b09384d36153826492480e88730dbe8e5690d89fc4b98645f448432f1a0082`.

After planner verification and the separate bounded implementation prompt,
the Capture v2 implementation was independently reviewed and accepted at
commit `02f5b1872e4dc422af3fa18964fd142288d63794`, parent
`2214b0459542d987b41d0af14d63653b8f707194`, tree
`94e7253f7f5d830a2e311f8864681c77a7464ab1`. Its accepted 19-file
content-manifest SHA-256 is
`8332fa7a1f7b91657ebc26576f5d9081d181f5a199b3f1dc829e2da6f5dbb481`.

The accepted deterministic offline coverage included:

- v1 success and every reachable closed failure as byte- and
  identity-compatible golden cases;
- v2 US-only, Kalshi-only, and mixed caller-order batches;
- both Kalshi environments with correctly bound authentication;
- v1 rejection of US targets and v2 rejection of international targets;
- invalid complete-specification rejection before signer or network activity;
- version, identity, model-type, and positional binding;
- currency, numeric grammar, missing fields, malformed JSON, exact strings,
  received ordering, duplicate levels, raw bytes, and digest preservation;
- the production transport through mocked lower-level I/O;
- absence of credentials, authentication fallback, discovery, and live network
  activity in tests;
- mutation, copy, reconstruction, pickle, JSON trust-transfer, exact nested US
  ladder/level/string/`Decimal` type, native-value, currency, scale, and
  identity revalidation and rejection; and
- every protected Milestones 1–5 regression.

The accepted implementation validation matrix was:

```text
python -m pytest -p no:cacheprovider tests/capture
python -m pytest -p no:cacheprovider
python -m pytest -p no:cacheprovider tests/unit tests/replay tests/relationships tests/discovery tests/constraints tests/opportunities tests/diagnostics
python -m pytest -p no:cacheprovider tests/unit/test_no_network.py
python -m ruff check --no-cache src tests
python -m ruff format --check --no-cache src tests
python -m mypy --strict src/invariant_engine
python -m compileall -q src tests
python -m json.tool fixtures/capture/cases.json
git diff --check
```

The previously observed independent result was 627 full-suite tests, including
271 capture tests and 356 protected-suite tests, plus 12 external adversarial
tests. Exact v1 success and every reachable closed failure compatibility golden
and signed Kalshi success were independently verified against the activation
baseline. A network-audited full suite reported 627 passed and zero connection
attempts. Ruff check, Ruff format check, strict mypy, compilation, parsing of
every fixture JSON file, capture-suite repeats with `PYTHONHASHSEED=1`, `2`, and
`random`, package and import boundaries, dependency checks, content identity,
whitespace, and artifact hygiene passed with caches and bytecode disabled or
redirected outside the repository. These are historical Capture v2
acceptance results.

The required, separately authorized engine-based US operational trial used
implementation `02f5b1872e4dc422af3fa18964fd142288d63794`, the public
`capture_batch` API, v2, and one anonymous production request:

`GET https://gateway.polymarket.us/v1/markets/paccc-usse-midterms-2026-11-03-dem/book`

The trial started at `2026-09-20T17:53:09.245538+00:00` and finished at
`2026-09-20T17:53:09.672534+00:00`. It returned HTTP 200 and `CAPTURED`, made
exactly one dispatch, completed acquisition and retention, retained 3,313
bytes, parsed 20 bids and 14 offers, and required an exact response-slug match.
The retained body SHA-256 was
`8cc51dc0413e53ba4be279242e6030ff5c1a7bdfc3b02065bcf3146c66ecc8c7`;
the serialized capture SHA-256 was
`dd1256794571c0eb1424945824d162131811ec0b707833299df0978b2c94081f`.
The temporary evidence paths were
`/tmp/invariant-us-live.n2yO0q/summary.json`,
`/tmp/invariant-us-live.n2yO0q/capture.json`, and
`/tmp/invariant-us-live.n2yO0q/response.bin`; no temporary response artifact
was copied into this repository. The trial used no retries or credentials and
made no repository modification.

This is one observed operational success. It does not establish a universal
venue or permanent wire-format contract, freshness, atomicity, cross-target or
cross-venue synchronization, account eligibility, credential validity,
portfolio or trading access, future availability, or deployment readiness. It
grants no authority for polling, another live request, credentials, account
access, trading, or deployment. Offline mixed-batch tests still imply no
synchronization. System DNS and caller-owned signer execution still lack a
guaranteed hard deadline, and actual venue trailer behavior remains unknown.

Capture v2 implementation and operational authority are deactivated. Every
contract and trust boundary in this section is now a permanent regression
guarantee, including exact v1 byte and identity compatibility; explicit v1/v2
venue separation; mixed-batch Kalshi authentication isolation; exact nested
US native type, value, currency, scale, and identity validation during issuance
and trust revalidation; raw native evidence preservation; bounded transport,
acquisition, retention, confidentiality, deadline, and digest behavior; and
complete separation from historical, replay, relationship, evaluation,
opportunity, simulation, risk, execution, order, and trade trust paths.

The documentation closure is recorded at commit
`40edb4eae7538a6a4ea0f964d5312cf37650624d`. Its historical gate required this
separate sequence:

1. An independent reviewer reads the exact uncommitted `AGENTS.md` and
   `PLAN.md` content and complete HEAD-relative governance diff, records both
   document SHA-256 values and the full binary governance-diff SHA-256 as the
   accepted-content identity, and explicitly accepts or rejects that exact
   content.
2. After acceptance, committing and pushing only `AGENTS.md` and `PLAN.md`
   was the user's role. The closure draft did not specify its eventual
   commit hash or tree.
3. The planner was to verify the resulting commit with expected parent
   `02f5b1872e4dc422af3fa18964fd142288d63794`, its tree, the committed document
   blobs and parent-to-commit governance diff against the accepted-content
   identity, local `HEAD` and local `origin/main` alignment, and complete
   manifests establishing a clean tracked worktree and index, no unexpected
   untracked or ignored artifacts, and exactly one permitted ignored pathname,
   `.env`, whose contents must not be read or hashed.

Comparison to local `origin/main` is offline inspection of the local
remote-tracking ref. It is not a fetch, remote API call, live remote query, or
proof of server state. The historical closure gate permitted the researcher
handoff after verification and left Milestone 6 inactive.
Discovery, polling, retries, concurrency, failover, WebSockets, institutional
integration, retail sandbox assumptions, account access, credential loading,
new signers, replay promotion, analytics, simulation, risk, orders, trading,
deployment, and further live requests remain outside the Capture v2 scope.

## Historical closure summary and current governance state

Milestone 3 — Historical opportunity economics is completed and accepted at
implementation commit `ecab60460ca0139beea4e289d0511af3e80aa1a9`, with an
implementation acceptance date of 2026-08-16. Its accepted guarantees are
permanent regressions, its implementation authority is deactivated, and its
delivered paths grant no continuing authority.

Milestone 4 — Strategy validation is completed and independently accepted at
implementation commit `3a4377355b6715d588fb0736e9da3c6d7cd42391`, with an
implementation acceptance date of 2026-08-29. Its accepted guarantees are
permanent regressions, its implementation authority is deactivated, and its
delivered diagnostics paths and relationship boundary-test change grant no
continuing authority.

Milestone 5 — Bounded live read-only capture batch is completed and
independently accepted at implementation commit
`e6cfd01d9eb9e3143d3fa23c4e739c8dcecacbfa`, parent
`a0776a1b99f334aa953a361da2100ca75c93b9f1`, tree
`1b76b0c06bf6af5c8aae07358240ead1a844803c`, with accepted 18-file
content-manifest SHA-256
`612c14ec018eed00323fb45003a30ae17578f3c2eff7b6daac0edf35ed0610ef`.
Its accepted guarantees are permanent regressions, and its delivered capture
paths grant no continuing authority or exception.

Capture v2 is independently accepted at implementation commit
`02f5b1872e4dc422af3fa18964fd142288d63794`, parent
`2214b0459542d987b41d0af14d63653b8f707194`, tree
`94e7253f7f5d830a2e311f8864681c77a7464ab1`, with accepted 19-file
content-manifest SHA-256
`8332fa7a1f7b91657ebc26576f5d9081d181f5a199b3f1dc829e2da6f5dbb481`.
Its separately authorized required engine-based US operational trial succeeded
as recorded above. Capture v2 is not Milestone 6, did not reopen Milestone 5,
and grants no continuing implementation, operational, or path authority. Its
accepted contract and trust boundaries are permanent regression guarantees.

Milestones 1–5 and Capture v2 remain accepted and closed. Independent review
accepted and commit-verified the bounded Milestone 6 synthetic execution
scenarios slice at `ac9c512ebcd96d2ce11a9c7bb93a2097fb74e61b`. Its contract
is a permanent regression boundary and its implementation authority is
deactivated. Its verified documentation closure is recorded at
`8eacb5f7ac5b795c2e4634d24fa8efebfceb6587`.

Milestone 6 remains open. The only current work is the two-document
activation draft for offline delay and queue comparison. Independent draft
acceptance, the user's commit and push, activation commit verification and a
separate implementation prompt precede implementation. Acceptance and
closure of the final slice complete Milestone 6 at the agreed scope.
Empirical calibration, fill probability and live sequencing remain deferred.
No implementation milestone, extension or operational trial is active.
