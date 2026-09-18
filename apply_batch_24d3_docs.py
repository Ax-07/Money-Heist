from pathlib import Path

ROADMAP = Path("docs/09_ROADMAP_DEVELOPPEMENT.md")
MARKER = "<!-- BATCH_24D3_FUNNEL_DECISION_QUALITY_RESEARCH -->"
BLOCK = f"""

{MARKER}
## État Batch 24D — Decision Quality Research

```text
24D.1 — Research Foundation & Outcome Join         DONE
24D.2 — Scanner Filtering Quality Research         DONE
24D.3 — Funnel Decision Quality Research           CURRENT
24D.4 — Research Reports & Evidence Explorer       NEXT
```

24D.3 joint `DecisionQualityResearchBundle.candidate_records` aux faits canoniques 24B.4
`FunnelStageAnalyticsAttributionSet`. Les stages antérieurs à FINAL restent directionless ; FINAL,
TradeProposal, Risk et PAPER peuvent publier des mouvements futurs alignés uniquement lorsqu'une
direction LONG/SHORT était déjà causalement disponible. Ces métriques ne sont pas un P&L de trade.
Le lot reste read-only, déterministe, sans tuning, persistance, endpoint ni frontend.
"""

text = ROADMAP.read_text(encoding="utf-8")
if MARKER not in text:
    ROADMAP.write_text(text.rstrip() + BLOCK + "\n", encoding="utf-8")
    print(f"updated: {ROADMAP}")
else:
    print(f"already present: {ROADMAP}")
