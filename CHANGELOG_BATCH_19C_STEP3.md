# Changelog — Batch 19c Step 3

## Added

- immutable `RecruitmentCandidateEvidencePackage`;
- compact `RecruitmentEvidencePackageLineage`;
- deterministic package fingerprint with self-integrity validation;
- full prerequisite recomputation before package creation;
- full candidate-spec drift detection against the frozen campaign;
- frozen success-criteria snapshot without evaluating it;
- explicit simulated Historical Replay/PAPER provenance;
- boundary tests excluding Agent Registry, Risk Engine and LIVE authority.

## Safety / authority

This step does not score success criteria, does not issue a recruitment recommendation, does not mutate `AgentRegistry`, does not modify the deterministic Risk Engine, and does not grant LIVE authority.
