# Milestone 2.2 discovery fixtures

These are local test artifacts with schema `discovery-fixture-v1`. They are
synthetic, not real market rules, not current venue authority, not semantic
review, not certification, and not production model benchmarks. Their provider,
model, prompt, cost, latency, and similarity fields are recorded metadata only.

`valid_cross_venue.json` demonstrates ordered Polymarket and Kalshi provenance,
venue-native identities, exact recorded input/output bytes, and a binary-unit
complement proposal. The fixture source computes and retains the SHA-256 of the
complete fixture artifact and of every recorded input/output byte string.

The labeled scenario catalog covers valid proposals, malformed JSON and
structured content, missing fields, unsupported versions, duplicate keys,
non-standard constants, invalid Unicode surrogates, non-JSON framing
whitespace, unknown/conditional/scalar proposals, ambiguous and conflicting
evidence, abstention, rejection, duplicates, bounded retry exhaustion,
evidence-span failures, cross-venue identity copying, repeated-run
determinism, disablement, prefilters, and measurement-only evaluation. These
labels describe test data only; they are not acceptance thresholds or semantic
judgments.
