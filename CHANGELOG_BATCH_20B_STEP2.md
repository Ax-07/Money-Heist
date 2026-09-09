# Changelog — Batch 20b Step 2

## Added

- deterministic Task Force composition provenance;
- source-bundle SHA-256 fingerprinting;
- full-registry fingerprinting;
- capability-profile fingerprinting;
- multidimensional Batch 18 reputation-evidence fingerprinting;
- recomposition-based stale detection;
- explicit stale reason codes;
- provenance/result binding checks;
- 12 focused tests.

## Safety invariants

- no AgentRegistry mutation;
- no automatic AgentState mutation;
- no execution authority;
- no Risk Engine authority;
- no broker or exchange authority;
- no LIVE authority;
- no aggregate reputation score;
- no inferred production threshold.
