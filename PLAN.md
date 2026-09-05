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

The eventual system must support both intra-venue and cross-venue relationships involving Polymarket and Kalshi. Analytics, replay, provenance, and monitoring are supporting capabilities for that trustworthy path. The accepted Milestone 3 and Milestone 4 deliveries are fully local, historical, read-only, fixture-driven, deterministic, network-free, diagnostic, and non-actionable. This uncommitted Milestone 5 activation draft grants no implementation authority. If and only if it is independently reviewed, committed, accepted, and the accepted activation commit is verified by the planner, Milestone 5 becomes the sole active implementation milestone for its bounded capture scope; implementation must still await a separate bounded implementation prompt. Milestone 6 and every later milestone remain explicitly inactive.

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

No earlier object may impersonate a later one. Milestone 2, Milestone 3, and Milestone 4 outputs remain non-actionable.

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

Start as a modular monolith rather than microservices. The only package creation that may take effect under this transition is the exact Milestone 5 capture-path allowance in its activation section, effective only after the accepted activation commit is verified and a separate bounded implementation prompt is issued. Any other change requires another explicit governance transition.

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
Milestone 4 delivery and retains every prohibition for simulation, risk,
execution, and reconciliation. These delivered paths and that former
exception confer no current implementation authority or continuing path
exception. Milestone 4 remediation or changes within those paths require a
future explicit governance transition.

The accepted Milestones 1, 2.1, 2.2, 2.3, 3, and 4 foundations and permanent
regression guarantees must not regress. No unrelated package or
later-milestone package is authorized. After the accepted activation commit is
verified, only the exact Milestone 5 read-only capture connection and narrow
caller-owned Kalshi signing adapter described below are permitted. All model
connections, simulation, risk, execution, reconciliation, wallets, private-key
handling, orders, cancellation, routing, and other live provider integration
remain prohibited.

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
Milestone 3 implementation authority remains deactivated. Milestone 4 is also
completed and accepted. At the time of Milestone 3 closure, no implementation
milestone was active and Milestone 5 and every later milestone were inactive;
the conditional Milestone 5 activation draft below does not alter this
historical acceptance record.

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
milestone were inactive. The conditional Milestone 5 activation draft below
does not reopen Milestone 4 or change its accepted boundary.

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
usage. Latency, queue, partial-fill, cancellation, and sequencing simulation
remain Milestone 6 work. Risk limits and capital authorization remain Milestone
7 work. A false-relationship statistic requires a separately governed labeled
benchmark and must not be inferred from certificate outcomes or discovery
rejections.

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
`tests/relationships/test_relationships.py` is also historical and retains
the prohibitions for simulation, risk, execution, and reconciliation. These
paths and that former exception grant no continuing authority. Any remediation
or implementation change requires a future explicit governance transition.

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

## Later milestone roadmap

### Milestone 5 — Bounded live read-only capture batch (activation draft)

#### Activation state and separation of authority

This is an uncommitted activation governance draft. It does not activate
implementation, network access, credentials, deployment, or a live trial. If
and only if every activation gate below is satisfied, Milestone 5 becomes the
sole active implementation milestone for the exact bounded scope below.

The activation sequence is mandatory:

1. An independent reviewer must read the exact uncommitted `AGENTS.md` and
   `PLAN.md` content and complete HEAD-relative governance diff, record the two
   document SHA-256 values and full-diff SHA-256 as the accepted-content
   identity, and explicitly accept or reject that exact content.
2. After acceptance, the user—not the reviewing or implementation agent—must
   commit and push the accepted content. This draft need not and cannot contain
   its eventual commit hash or tree.
3. Before activation takes effect, the planner must verify the resulting
   commit identity, its expected parent
   `ec3a8356a91cdbcf6eefbc140da0f579e0cb6233`, its tree, the committed document
   blobs and parent-to-commit governance diff against the accepted-content
   identity, local `HEAD` and local `origin/main` alignment, and complete clean
   tracked, staged, unstaged, untracked, and ignored manifests.
4. After that verification, implementation must still await a separate
   bounded implementation prompt before any file is created or changed.

The `origin/main` check in step 3 is an offline comparison with the locally
stored remote-tracking ref. It is not a fetch, remote API call, or proof of the
server's current state. Any actual remote query requires separate authority;
the required user push is not delegated to an agent by this draft.

Implementation acceptance and governance closure remain separate. A future
review may accept the implementation without deactivating Milestone 5. A later
explicit governance closure must deactivate Milestone 5 authority; this draft
does not write or presume that closure. Milestone 6 and every later milestone
remain inactive.

#### Purpose and trust boundary

Milestone 5 implements a finite, one-shot, live, read-only REST capture batch
over an immutable ordered list of caller-supplied venue identifiers. The
boundary begins with a validated capture specification and, for Kalshi, a
runtime-only caller-owned authentication binding. It ends with immutable
capture provenance plus either a venue-native captured REST order book or an
explicit terminal target failure. It does not discover markets or tokens.

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
reconciliation are complete. This activation draft uses only the supplied
reviewed findings below; it does not inspect the research repository, use the
newly found demo-funds documentation, or rely on unverified Polymarket staging
access.

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

The user selects authenticated Kalshi requests as an engineering policy under
uncertainty. This choice does not resolve the evidence conflict and must not be
described as proof that the endpoint is universally authenticated,
universally public, or optionally authenticated. Kalshi has no anonymous
fallback.

#### Exact operations and environments

Only these operations may be implemented:

- Polymarket production: `GET https://clob.polymarket.com/book?token_id={caller_supplied_token_id}`;
- Kalshi demo: `GET https://external-api.demo.kalshi.co/trade-api/v2/markets/{ticker}/orderbook`;
- Kalshi production: `GET https://external-api.kalshi.com/trade-api/v2/markets/{ticker}/orderbook`.

Polymarket supports production only. Kalshi supports explicit demo and
production environments with environment-bound authentication inputs. No
staging or compatibility origin, optional depth parameter, arbitrary URL,
additional query parameter, other HTTP method, redirect target, or origin
failover is allowed.

Production support means that the bounded implementation must correctly model
and test that exact operation. It is not permission to deploy or make a live
production request. The initial separately authorized Kalshi live trial, if
later approved, will use demo. A Polymarket production trial also requires
separate bounded operational authorization even though its selected operation
is public. A live trial is not part of implementation or ordinary tests.

#### Exact implementation-path and dependency allowance

After activation and a separate implementation prompt, source changes are
limited exactly to:

- `src/invariant_engine/capture/__init__.py`;
- `src/invariant_engine/capture/models.py`;
- `src/invariant_engine/capture/specification.py`;
- `src/invariant_engine/capture/authentication.py`;
- `src/invariant_engine/capture/transport.py`;
- `src/invariant_engine/capture/parsing.py`;
- `src/invariant_engine/capture/batch.py`; and
- `src/invariant_engine/capture/serialization.py`.

Test changes are limited exactly to:

- `tests/capture/conftest.py`;
- `tests/capture/test_specification.py`;
- `tests/capture/test_authentication.py`;
- `tests/capture/test_transport.py`;
- `tests/capture/test_parsing.py`;
- `tests/capture/test_batch.py`;
- `tests/capture/test_serialization.py`; and
- `tests/capture/test_trust_boundaries.py`.

Fixture changes are limited exactly to:

- `fixtures/capture/README.md`; and
- `fixtures/capture/cases.json`.

No existing implementation file, existing test, `pyproject.toml`, or other
path may change. No new runtime or development dependency is authorized. The
implementation must use standard-library transport and a caller-owned signing
interface. If these boundaries prevent sound implementation, stop and report
the concrete problem rather than expanding the allowance.

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

The prospective phrase “exactly one request attempt per target” is amended:
each position receives exactly one logical `TargetAttempt`, while each target
performs at most one HTTP dispatch. A Kalshi signing or integrity failure is a
completed terminal target attempt with zero dispatches. No retry is performed.

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
  response-header, or body-read operation; and
- a 20.0-second transport elapsed budget beginning immediately before the
  engine invokes system name resolution for the one dispatch and covering
  engine-controlled resolution orchestration, connect, TLS, request write,
  response headers, and body reads.

The engine must check the monotonic elapsed budget before and after every
engine-controlled blocking stage and between body reads, and must use the
smaller remaining budget where a standard-library timeout accepts one. The
budget excludes specification validation and caller signer execution. System
DNS calls may outlast the budget because the standard library and operating
system do not guarantee hard cancellation; this limitation must be explicit.
No hard wall-clock completion guarantee is made for DNS or external signer
code.

Response headers are quarantined and limited to at most 100 fields, at most
8,192 ISO-8859-1 octets for any parsed name/value pair, and at most 32,768 such
octets in aggregate. The underlying standard-library maximum accepted header
line remains an additional ceiling, not an expanded capture contract. Invalid
names or values, control characters other than parsing syntax already removed
by the library, obsolete folding, conflicting `Content-Length`, unsupported
transfer framing, or non-identity `Content-Encoding` fail closed.

Unknown and unexpected response headers count toward limits but are otherwise
ignored. Public results may retain only the integer HTTP status, a strictly
parsed nonnegative `Content-Length` when unambiguous, and a normalized
`Content-Type` media type from visible ASCII; raw response headers and header
parameters are not retained or serialized. All received header names and
values are nevertheless scanned by the confidentiality detector before this
allowlisted metadata may be published.

#### Body acquisition, retention, and confidentiality

The maximum response entity body is 1,048,576 bytes. The transport reads in
chunks of at most 65,536 bytes and may read one additional byte solely to
classify oversize input. “Received bytes” means entity-body bytes after HTTP
transfer framing is removed and before any content decoding; only identity
content encoding is supported.

Body acquisition outcome and body retention state are separate closed enums.
The acquisition outcome records what occurred before confidentiality filtering:

- `NOT_STARTED`: no body-read operation began;
- `FAILED_BEFORE_FIRST_BYTE`: a body-read operation began but failed before
  receiving any body byte;
- `COMPLETED`: normal EOF or the exact declared body length was reached within
  the cap, including a normally completed zero-length body;
- `PARTIAL`: acquisition failed after receiving at least one byte and before
  normal completion, without crossing the cap; and
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

An unambiguous `Content-Length` greater than the cap permits an immediate
`BODY_OVERSIZED` result without beginning body acquisition; its retention state
is `ABSENT`, and no body digest exists. Otherwise streaming acquisition applies
the prefix rule above. In both cases no oversized material is parsed or
published as a successful capture.

The valid unsuppressed combinations are exhaustive:

| Acquisition outcome | Acquisition started | Normal completion | Retention | Received length | Retained length and material | Ordinary status before integrity or confidentiality override |
|---|---:|---:|---|---:|---|---|
| `NOT_STARTED` | No | No | `ABSENT` | 0 | 0; body and digest absent | Predispatch failure, header failure, timeout/transport failure before body acquisition, or declared `BODY_OVERSIZED`. |
| `FAILED_BEFORE_FIRST_BYTE` | Yes | No | `ABSENT` | 0 | 0; body and digest absent | `TIMEOUT` or `TLS_OR_TRANSPORT_FAILED`. |
| `COMPLETED` | Yes | Yes | `COMPLETE` | 0 through 1,048,576 | Equal to received length; body present and digest present, including zero length. | `BODY_EMPTY`, `HTTP_STATUS_UNSUPPORTED`, parsing/schema/identifier failure, or `CAPTURED` as applicable. |
| `PARTIAL` | Yes | No | `PARTIAL` | 1 through 1,048,576 | Equal to received length; nonempty prefix and digest present. | `BODY_PARTIAL`. |
| `OVERSIZED` | Yes | No | `OVERSIZED` | 1,048,577 | 1,048,576-byte prefix and digest present. | `BODY_OVERSIZED`. |

Confidentiality detection replaces the retention state in any safely observed
case with `SUPPRESSED` and makes the primary status
`CONFIDENTIALITY_FAILURE`. Header-only detection must stop before body
acquisition and therefore combines `NOT_STARTED`, acquisition-started `No`,
normal-completion `No`, received length 0, retained length 0, no body, and no
digest. Detection in a complete, partial, or oversized body preserves its
original acquisition outcome, acquisition flags, and actual received length,
but requires retained length 0, no body, and no digest. Suppression provenance
may identify only `HEADER` or `BODY`, never the matched key ID, signature, or
matched bytes.

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

All header and body material is quarantined before publication. The exact
confidentiality detector searches for the complete key ID and signature as
raw ASCII byte substrings in every received header name/value and quarantined
candidate body or prefix. It also lexically scans every complete JSON string
token in the quarantined candidate bytes and decodes valid JSON escapes—including `\"`, `\\`,
`\/`, the control escapes, and case-insensitive four-hex-digit `\uXXXX`
sequences with valid surrogate pairing—then searches each decoded string for
the exact key ID or signature. This detects arbitrarily mixed valid JSON
escapes within complete string tokens; malformed or incomplete string tokens
are covered only by the raw-byte search.

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
empty-body, parsing, schema, identifier, and prospective `CAPTURED` statuses,
but remains below `CONFIDENTIALITY_FAILURE`. It must never be converted to
`CAPTURED`. If the attempt identity and acquisition facts are independently
trustworthy—for example, a separately bound material fingerprint detects
mutation after a transport-local complete or partial acquisition—the result
may retain those exact acquisition outcome, flags, byte counts, retention
state, body, and digest facts while its primary status is `INTEGRITY_FAILURE`.

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
raw exceptions, unrestricted headers, suppressed bodies and digests, sockets,
clocks, and all process-local trust state are excluded. Local observer
timestamps are acquisition provenance only; they make no venue-time,
freshness, synchronization, or ordering claim.

#### Acceptance contract

Implementation acceptance requires an independent reviewer to:

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

Implementation acceptance also requires deterministic offline tests covering
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
  body and header bounds, and no redirects, retries, failover, cookies, or
  ambient credentials;
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
- header-only confidentiality detection and complete, partial, and oversized
  bodies suppressed for confidentiality; exact digest scope; raw and mixed
  JSON-escaped key-ID/signature reflection; confidentiality precedence; and
  suppression from representations and serialization;
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

Ordinary tests use only synthetic responses. Offline acceptance establishes
implementation behavior, not successful real signatures, actual credential
environment or permissions, live endpoint availability, or successful
order-book acquisition. A failure-only live result is not proof of successful
capture.

Implementation acceptance remains distinct from activation, operational
validation, and governance closure. An implementation may be accepted against
the offline contract only if its record explicitly leaves live-access claims
unvalidated. Any later claim that authenticated Kalshi acquisition works live
requires a separately authorized successful demo result for the initial trial;
any Polymarket live-success claim requires a separately authorized production
trial. Neither trial is authorized here, and a failure-only result cannot
satisfy a live-success claim.

Required implementation validation must use an identified external Python
3.11-or-newer toolchain with bytecode and cache output disabled or redirected
outside the repository:

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

Repeat the capture suite with `PYTHONHASHSEED=1`, `2`, and `random`. Set an
external `MYPY_CACHE_DIR` and external `PYTHONPYCACHEPREFIX` for commands that
write caches. Include package/import-boundary and repository-artifact checks.

#### Non-goals and stop conditions

Milestone 5 excludes private-key loading, RSA implementation, credential
creation or enumeration, ambient secret discovery, live calls during
implementation or ordinary tests, staging or compatibility origins, market or
token discovery, WebSockets, polling, concurrency, retries, redirects,
failover, replay promotion, cross-venue synchronization, analytics, fees,
relationships, opportunities, strategy evaluation, simulation, risk,
execution, reconciliation, orders, trading, deployment, and Milestone 6 or
later planning or activation.

Stop for unexplained baseline changes, a required path or dependency outside
the exact allowance, missing applicable reviewed evidence, or a contract that
cannot be implemented without an unsupported assumption. Report the concrete
problem and candidate-source question; do not expand scope or import current
external or unreviewed material.

#### Governance state after accepted activation

While this draft is uncommitted or its accepted commit is unverified, no
implementation milestone is active. After the accepted activation commit is
verified by the planner, Milestone 5 is the sole active implementation
milestone, limited to the scope above, and still requires a separate bounded
implementation prompt. Accepted Milestones 1–4 remain closed and protected.
Milestone 6 and every later milestone remain inactive. No implementation
acceptance or governance closure is claimed or written here.

### Milestone 6 — Execution simulation

Model latency, queue assumptions, partial fills, failed legs, cancellations, and residual exposure without sending orders.

### Milestone 7 — Deterministic risk gateway

Add independent limits, stale-data rejection, minimum-edge requirements, exposure controls, strategy enablement, and kill switches.

### Milestone 8 — Restricted venue-local execution

Enable one venue and one validated strategy class with tightly limited capital through the risk gateway.

### Milestone 9 — Cross-venue execution

Add cross-venue execution only after venue-local execution and reconciliation are reliable.

## Evidence dependencies and deferred research

These items identify unresolved evidence and design dependencies.
Reclassification does not resolve an item, authorize assumptions, change
milestone scope, or satisfy acceptance criteria. Excluding a required
capability requires an explicit governance decision.

Dependencies apply only to the markets, operations, and strategies actually
supported; they do not require universal answers. Mutable venue facts require
scoped, dated verification. Failure or refusal alone does not satisfy a
milestone whose accepted purpose requires a working capability. These
classifications do not establish new milestone acceptance criteria. Do not
invent answers to these questions.

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
| A6 | Partial-fill economics; execution simulation. | A supported simulation capability models less than complete fills. | Decide the exact economic accounting across supported partial-fill states without inventing fill behavior. | Unresolved decision. |
| A7 | Safe execution sequencing; multi-leg execution simulation and later execution. | A supported strategy requires multiple non-atomic operations. | Decide which sequences are permitted and how failures, cancellations, exposure, and venue constraints are evaluated. | Unresolved decision. |
| A8 | Cross-venue settlement differences; cross-venue strategy economics, risk, and reconciliation. | A supported strategy spans venues with distinct settlement processes. | Establish the applicable settlement rules, timing, failure states, and reconciliation treatment for the selected markets and operations. | Unresolved decision. |
| A9 | Economic finality and cash availability; settlement, reconciliation, and reusable-capital accounting. | A supported capability relies on a result being economically final or funds being available for reuse. | Decide the exact, venue- and operation-specific evidence for finality and cash availability. | Unresolved decision. |

### B. Venue contracts requiring scoped verification

These mutable venue facts require dated verification for the exact interfaces,
operations, and effective periods used by the selected capability.

| # | Topic and affected capability | Trigger | Required evidence or decision | Status |
|---:|---|---|---|---|
| B1 | Fill-history semantics; reconciliation of supported orders. | The selected capability must retrieve and reconcile fills for its supported order operations. | Verify which fill identifiers, corrections, ordering, and retrieval semantics are needed for that reconciliation, without presuming that any particular venue behavior exists. | Scope-specific verification required. |
| B2 | Current venue schemas; selected capture, execution, or reconciliation interfaces. | A selected capability consumes a venue interface. | Verify the exact request, response, event, versioning, and compatibility schemas used by its supported operations for the applicable effective period. | Scope-specific verification required. |
| B3 | Current venue fee schedules; selected economics, simulation, risk, or execution operations. | A selected capability requires fees for specified venues, markets, roles or sides, operations, and times. | Verify the exact effective fee policies, formulas, scopes, rounding, currency, and provenance applicable to those operations and periods. | Scope-specific verification required. |

### C. Dependencies triggered by a design choice

These dependencies do not choose a design or authorize implementation.

| # | Topic and affected capability | Trigger | Required evidence or decision | Status |
|---:|---|---|---|---|
| C1 | WebSocket gap recovery; streaming market-data capture and state reconstruction. | Streaming market data is selected. | Define the venue- and channel-specific sequence, gap detection, recovery, replay-validity, and fail-closed semantics. | Conditional dependency. |
| C2 | Latency distributions; calibrated latency analysis or simulation. | The design makes calibrated latency claims. | Supply empirical, scope-matched evidence for the claimed distributions. Explicit scenario assumptions must be labeled and are not empirical estimates. | Conditional dependency. |
| C3 | Queue position and fill probability; execution simulation. | The selected simulation design models queue position or fill probability. | Define the selected simulation model and the evidence needed for any empirical or predictive claim; do not silently assume full fills or a queue model. | Conditional dependency. |
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

## Governance after Milestone 4 closure

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

This uncommitted activation draft does not itself authorize or activate
implementation. If it is independently reviewed, committed, accepted, and the
accepted activation commit is verified by the planner, Milestone 5 becomes the
sole active implementation milestone for only the bounded capture scope above;
a separate bounded implementation prompt remains required. Milestone 6 and
every later milestone remain inactive. Any Milestone 1–4 remediation, scope
expansion, other implementation, or later milestone activation requires a
future explicit `PLAN.md` governance transition. Milestone 5 implementation
acceptance and its future deactivation and governance closure remain separate
later decisions.
