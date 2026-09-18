from __future__ import annotations

from pathlib import Path

ROADMAP = Path("docs/09_ROADMAP_DEVELOPPEMENT.md")
MARKER = "<!-- BATCH_24D2_SCANNER_FILTERING_QUALITY_RESEARCH -->"
ADDENDUM = f"""
\n{MARKER}
## État Batch 24D — Decision Quality Research

```text
24D.1 — Research Foundation & Outcome Join         DONE
24D.2 — Scanner Filtering Quality Research         CURRENT
24D.3 — Funnel Decision Quality Research           NEXT
24D.4 — Research Reports & Evidence Explorer       PLANNED
```

24D.2 construit une projection descriptive et déterministe à partir de
`DecisionQualityResearchBundle.scanner_records`. Le Scanner reste directionless : les Forward
Outcomes décrivent le mouvement futur du prix et ne constituent ni un P&L hypothétique, ni un
label de trade raté, ni une recommandation de threshold. Les dimensions v1 sont
`CLASSIFICATION`, `SCORE`, `SCORE_MARGIN`, `TRIGGER` et `MARKET_REGIME`; les contrasts restent
strictement descriptifs. Persistance, API de rapports et Evidence Explorer restent réservés à
24D.4.
"""


def main() -> None:
    text = ROADMAP.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"{ROADMAP}: addendum 24D.2 already present")
        return
    if "Batch 24D — Decision Quality Research" not in text:
        raise SystemExit(
            "Refusing to patch roadmap: expected Batch 24D context is missing. "
            "Verify the exact 3bbba90 baseline first."
        )
    ROADMAP.write_text(text.rstrip() + ADDENDUM + "\n", encoding="utf-8")
    print(f"Updated {ROADMAP} with Batch 24D.2 roadmap state")


if __name__ == "__main__":
    main()
