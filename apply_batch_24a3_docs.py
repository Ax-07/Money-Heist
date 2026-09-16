from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

SECTIONS = {
    "docs/02_ARCHITECTURE.md": """
<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Batch 24A.3 — Technical Events

L'Analytics Lab possède désormais une couche `app.analytics.events` strictement
observation-only :

```text
Canonical closed candles
→ Analytics Indicators
→ Technical Events
→ AnalyticsSnapshot / Decision Intelligence future
```

`TechnicalEventEngine` consomme uniquement deux `AnalyticsIndicatorSnapshot` consécutifs.
Il ne recalcule aucun indicateur, ne lit pas le Scanner et ne possède aucune autorité de
trading. Les événements portent `event_at` et `available_at`; pour 24A.3 ils sont égaux au
close/as-of de la snapshot courante. Les chemins Scanner/Decision/Agents/Risk/PAPER/LIVE
restent indépendants et ne doivent pas importer `app.analytics.events`.
""",
    "docs/08_API_ET_MODELES_DE_DONNEES.md": """
<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Addendum Batch 24A.3 — TechnicalEventObservation

Contrats Analytics ajoutés : `TechnicalEventDefinition`, `TechnicalEventEvidence` et
`TechnicalEventObservation`. Une observation contient une identité déterministe, le run
Analytics, type/famille/direction descriptive, symbole/timeframe, `event_at`,
`available_at`, fingerprints source/cursor, evidence T-1/T, version de définition et
`event_fingerprint`. Les événements sont sérialisables et n'ont aucune sémantique
`LONG`/`SHORT`.
""",
    "docs/09_ROADMAP_DEVELOPPEMENT.md": """
<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Batch 24A.3 — Technical Events — livré dans l'Analytics Lab

Après 24A.1 (foundation/isolation) et 24A.2 (rich indicators), 24A.3 ajoute le registry
versionné de Technical Events, la détection causale T-1/T, les IDs/fingerprints stables,
l'evidence et l'intégration `AnalyticsSnapshot`. Le prochain sous-batch Analytics prévu
reste 24A.4 — Causal Structure & ZigZag; aucun pivot/pattern/context n'est implémenté ici.
""",
    "docs/10_DECISIONS_ET_CHANGELOG.md": """
<!-- BATCH_24A3_TECHNICAL_EVENTS -->
### 2026-09-16 — Batch 24A.3 Technical Events

**ACCEPTED** — Les Technical Events sont des observations Analytics descriptives et non
des signaux de trading. Leur source unique est `AnalyticsIndicatorSnapshot`; le moteur est
stateless T-1/T, causal, déterministe et isolé du Scanner/Decision/Risk/PAPER/LIVE. Les
seuils canoniques V1 sont versionnés dans le registry (RSI 30/50/70, ADX 25, MFI 20/80,
volume ratio 1.5). Les changements matériels de registry modifient l'identité Analytics,
jamais l'identité business du `BacktestRun`.
""",
    "docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md": """
<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Addendum Batch 24A.3 — événements Analytics pendant le replay

Les Technical Events peuvent être reconstruits causalement à partir des snapshots
Indicators visibles à T-1/T. La propriété attendue reste :

```text
Events(full_dataset, as_of=T) == Events(dataset_truncated_at_T, as_of=T)
```

Les événements Analytics participent à l'identité/fingerprint Analytics, mais ni au
`BacktestRun.run_id` ni au business fingerprint. Une candle future malformée ne doit pas
modifier un événement déjà disponible à T et une candle higher-timeframe non close ne doit
produire aucun événement de ce timeframe.
""",
    "docs/ANALYTICS_INDICATOR_PARITY.md": """
<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Extension 24A.3 — Indicators vers Technical Events

Les Technical Events réutilisent exclusivement les sorties du registry Indicators 24A.2.
`PRICE_CROSS_*_EMA_200` utilise `ema_200_distance_pct`, Bollinger utilise
`bb_position_20_2`, Donchian utilise `distance_to_high_20_pct` /
`distance_to_low_20_pct`, et `VOLUME_SPIKE_20` utilise `volume_ratio_20`.

Cette taxonomie est indépendante des Scanner Triggers. Une proximité conceptuelle
(`VOLUME_SPIKE_20` vs `VOLUME_EXPANSION`, ADX vs `TREND_STRENGTH`, Donchian vs
`RANGE_BREAK`) n'implique ni identité d'objet, ni seuil, ni timing, ni parité métier.

Par rapport à `btc_analytics_v1` p4.v1, la parité est conceptuelle : Money Heist ajoute les
retours Bollinger, transforme Donchian en transition de clôture non répétée et ne donne
aucun accès aux candles brutes à l'Event Engine.
""",
    "CHANGELOG_BATCH.md": """
<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Batch 24A.3 — Technical Events

- registry Analytics Technical Events versionné/fingerprinté ;
- 35 événements descriptifs trend/momentum/volatility/trend-strength/volume/structure ;
- détection causale stateless T-1/T avec warmup et égalités explicites ;
- IDs/fingerprints/evidence déterministes ;
- intégration `AnalyticsSnapshot` et identité Analytics ;
- prefix invariance, future malformed isolation, MTF closed-candle semantics et import guards ;
- aucune modification fonctionnelle Scanner/DecisionContext/Agents/Risk/PAPER/LIVE.
""",
}


def append_once(path: Path, section: str) -> bool:
    marker = section.strip().splitlines()[0]
    current = path.read_text(encoding="utf-8")
    if marker in current:
        return False
    path.write_text(current.rstrip() + "\n\n" + section.strip() + "\n", encoding="utf-8")
    return True


def main() -> None:
    changed = []
    for relative, section in SECTIONS.items():
        path = ROOT / relative
        if not path.exists():
            raise SystemExit(f"missing expected documentation file: {relative}")
        if append_once(path, section):
            changed.append(relative)
    print("Batch 24A.3 documentation updated:")
    for item in changed:
        print(f"- {item}")
    if not changed:
        print("- no changes (already applied)")


if __name__ == "__main__":
    main()
