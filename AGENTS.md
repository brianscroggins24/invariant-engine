# Agent instructions

- `PLAN.md` defines the approved roadmap and governance state. No implementation milestone is currently active.
- Milestone 3 — Historical opportunity economics was independently reviewed and accepted on 2026-08-16 at implementation commit `ecab60460ca0139beea4e289d0511af3e80aa1a9`.
- Milestone 4 and every later milestone remain explicitly inactive.
- Milestone 1 is completed and accepted. Its replayable market foundation must not regress.
- Milestone 2.1 is completed and accepted. Its deterministic relationship foundation must not regress.
- Milestone 2.2 is completed and accepted at implementation commit `d7a6dc5aec6a7fb9c24400a269aae4231bbf8572`.
- Milestone 2.3 was completed and accepted on 2026-08-15 at implementation commit `2bdcd2dc6124f8e794ac6e5252f90e3bbb57e22c`.
- Preserve all accepted Milestone 1, 2.1, 2.2, 2.3, and 3 guarantees: local, historical, read-only, fixture-driven, deterministic, network-free, non-actionable behavior; exact `Decimal` arithmetic; venue-native models and identifiers; exact ordered provenance; stable versioned serialization; fail-closed handling; and process-local trust boundaries.
- The discovery boundaries delivered by Milestone 2.2 are permanent: discovery is optional, local, read-only, fixture-driven, provider-neutral, recorded-response, untrusted, deterministic outside recorded bytes, replaceable, disableable, strictly parsed, fail-closed, provenance-rich, and network-free.
- The existing deterministic validator remains the sole `RelationshipCertificate` producer. Discovery may not review, attest semantic review or state-space completeness, certify, compile, evaluate, create an opportunity, or authorize action.
- Only validator-produced `RelationshipCertificate` objects may be compiled. `RelationshipCandidate` and `RelationshipCertificateDraft` objects cannot be compiled. Only trusted compiler-produced constraints may enter evaluation or opportunity economics.
- Preserve trusted observation construction and exact Milestone 2.3 timestamp synchronization. Constraint evaluation remains non-actionable.
- A constraint violation is not an opportunity. An `OpportunityCandidate` is not historically supported, executable, an order, a recommendation, or an authorization; it is explicitly non-actionable. Aggregate strategy validation remains Milestone 4 work.
- The ordered trust lifecycle is:

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
      → later strategy validation
      → later execution simulation
      → later deterministic risk authorization
  ```

- The accepted Milestone 3 delivery deterministically evaluates the economics of one synchronized historical constraint violation at a time. Its boundaries are permanent regression requirements: all behavior remains local, historical, read-only, fixture-driven, deterministic, network-free, and non-actionable.
- `src/invariant_engine/opportunities/`, `tests/opportunities/`, `fixtures/opportunities/`, and the delivered recognition change in `tests/relationships/test_relationships.py` are historical Milestone 3 delivered paths. They confer no current implementation authority or continuing path exception.
- Any further engine implementation, including Milestone 3 remediation or Milestone 4 work, must stop until a future explicit `PLAN.md` governance transition grants authority.
- Opportunity economics must begin from a validator-produced certificate, its corresponding trusted compiler-produced constraint, exact venue-native historical snapshots, an explicit positive counterfactual quantity, and an immutable, versioned, time-scoped fee policy with complete semantics and ordered provenance.
- A supplied `ConstraintEvaluation` is insufficient authority. The evaluator must independently validate certificate integrity, reconstruct and exactly verify the expected constraint and its material content, construct fresh trusted observations, rerun the accepted Milestone 2.3 evaluator, and continue only for a genuine `VIOLATED` result.
- `SATISFIED`, `INDETERMINATE`, `UNAVAILABLE`, malformed, and untrusted upstream inputs must never produce a candidate.
- Only buy-only underpricing for complement below its equality bound, exhaustive set below its lower bound, and exclusive-and-exhaustive partition below its equality bound may produce candidates. All other directions—including implication, equivalence, subset or superset, mutually-exclusive overpricing, above-bound partition, mixed buy/sell, selling, shorting, inventory, collateral, borrowing, and complement conversion—must return a structured unsupported-trade-direction result.
- For a caller-supplied positive quantity, consume ordered asks deterministically, use direct Polymarket asks and accepted venue-native YES/NO conventions to derive Kalshi asks, retain venue-native identifiers, use exact `Decimal` arithmetic, and calculate required quantity, ordered depth slices, cost, and VWAP for every required leg. Complete canonical validation of both native book sides, complete observed depth, exact ordered provenance, and exact Milestone 2.3 timestamp synchronization are mandatory.
- Supplied depth is not complete market capacity. Maximum observed capacity may be reported only as a diagnostic fact. Do not optimize size or recommend capital.
- Missing, malformed, crossed, stale, unsynchronized, replay-invalid, or insufficient data must fail closed.
- Fee policies are explicit immutable data, never executable callbacks, current configuration, inferred venue defaults, or a silent zero-fee assumption. Each policy must specify venue, policy/version ID, effective interval, role or side, formula parameters, calculation scope, rounding scope, currency, rounding quantum, and ordered provenance.
- A fee policy outside its effective interval, with incomplete or unsupported semantics, or dependent on invented rounding or fill grouping must fail closed. Mutable category, market, series, or event configuration must not be hardcoded.
- Report gross edge, fees or defensible fee bounds, and a net-edge interval. A candidate may exist only when worst-case net edge is strictly positive.
- Residual exposure is limited to deterministic single-leg complete-failure stress: all other required buy legs fill, one required leg receives zero fill, and payoff and PnL ranges are calculated across every certified feasible payoff state. Fill probability, queue position, latency models, partial-fill simulation, cancellation behavior, multi-failure simulation, and order sequencing remain unauthorized.
- `OpportunityEconomicsEvaluation` statuses include `VALIDATED`, `NO_NET_EDGE`, `INSUFFICIENT_DEPTH`, `UNSUPPORTED_TRADE_DIRECTION`, and `UNAVAILABLE`. Only `VALIDATED` may produce an `OpportunityCandidate`.
- An `OpportunityCandidate` must be evaluator-produced; bind every material input and result; have deterministic identity, ordering, and serialization; preserve ordered provenance; fail trust validation after material mutation; not transfer process-local trust through copy, reconstruction, pickle, or JSON; exclude runtime trust state from stable serialization; and state explicitly that it is non-actionable.
- Preserve venue-native semantics and exact ordered raw provenance. Use `Decimal` for all financial, payout, threshold, ratio, quantity, price, cost, fee, edge, and constraint values; never fabricate missing fields or venue behavior.
- Missing evidence, unsupported semantics, invalid objects, unavailable observations, and inconsistent state must produce explicit unavailable, indeterminate, unsupported, or failure results, never invented behavior.
- No conditional relationships, scalar payouts, generalized solvers, integer programming, or marginal-polytope projection may be introduced.
- The accepted Milestone 3 boundary permanently excludes live ingestion; network calls; authentication or credentials; wallets or signing; orders, routes, submissions, or cancellations; risk authorization; capital allocation; recommended sizing; aggregate opportunity frequency or persistence statistics; portfolio performance or drawdown analysis; fill probability; queue or latency models; execution simulation; partial-fill economics; current fee discovery; new relationship-discovery behavior; or changes to certificate, relationship, constraint, or Milestone 2.3 evaluation semantics.
- Future execution code must remain behind an independent deterministic risk gateway.
- Any future authorized tests must preserve Milestones 1, 2.1, 2.2, 2.3, and 3 behavior, including determinism, provenance, precision, venue separation, type-state boundaries, no-network behavior, certificate-boundary protection, compiler-only trusted constraints, trusted observations, exact timestamp synchronization, and evaluator-only process-local `OpportunityCandidate` trust.
- Current venue fee schedules, complete fill-history semantics, asynchronous cross-venue observations, inventory and collateral requirements, borrowing and short-sale mechanics, complement conversion, queue position, fill probability, latency distributions, partial-fill economics, execution sequencing, and capital-transfer constraints remain explicitly unresolved.
- No implementation milestone is active. Scope expansion or any further engine implementation requires another explicit `PLAN.md` governance transition; Milestone 4 and every later milestone remain inactive.
