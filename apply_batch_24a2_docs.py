from __future__ import annotations

from pathlib import Path

MARKER = "<!-- BATCH_24A2_RICH_INDICATORS -->"

SECTIONS = {
    "docs/02_ARCHITECTURE.md": (
        "\n### Batch 24A.2 — Rich Indicators (observation-only)\n\n"
        "`app/analytics/indicators` adds a versioned, deterministic, causal indicator "
        "registry beside — not inside — the production Feature Engine. It consumes only "
        "canonical closed candles already exposed by Money Heist historical MTF contracts. "
        "No decision path imports this package. Analytics indicator identities affect "
        "Analytics fingerprints only.\n"
    ),
    "docs/08_API_ET_MODELES_DE_DONNEES.md": (
        "\n### Batch 24A.2 — Analytics Indicator contracts\n\n"
        "24A.2 adds typed `IndicatorValue` and `AnalyticsIndicatorSnapshot` contracts. The "
        "snapshot preserves symbol, timeframe, `as_of`, `source_cursor_fingerprint`, "
        "registry version/fingerprint, warmup/availability states and a deterministic "
        "snapshot fingerprint. It is embedded in the 24A.1 `AnalyticsSnapshot` under the "
        "typed `indicators` component.\n"
    ),
    "docs/09_ROADMAP_DEVELOPPEMENT.md": (
        "\n### Batch 24A.2 — Rich Indicators & Parity Catalogue\n\n"
        "24A.2 installs the observation-only rich indicator catalogue and explicit semantic "
        "parity catalogue. Technical Events (24A.3), causal structure/ZigZag (24A.4), "
        "patterns and forward-outcome research remain out of scope.\n"
    ),
    "docs/10_DECISIONS_ET_CHANGELOG.md": (
        "\n### Décision Batch 24A.2 — séparation Feature Engine / Analytics Indicators\n\n"
        "Le Feature Engine de production reste inchangé. Analytics possède un registre "
        "indépendant, versionné et fingerprinté. Les divergences ADX (initialisation) et "
        "Volume Ratio (inclusion/exclusion de la bougie courante) sont intentionnelles, "
        "testées et documentées. Une évolution du registre change l'identité Analytics mais "
        "pas l'identité business du backtest.\n"
    ),
    "docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md": (
        "\n### Batch 24A.2 — projection indicateurs au replay\n\n"
        "Le moteur Analytics Indicators consomme les bougies closes du "
        "`HistoricalMultiTimeframeCursor` / `HistoricalMultiTimeframeSlice`; il ne resample "
        "pas et n'ingère aucune donnée lui-même. À T, seules les bougies dont "
        "`close_time <= as_of` peuvent contribuer. Le `source_cursor_fingerprint` est "
        "conservé dans le snapshot Indicators.\n"
    ),
    "CHANGELOG_BATCH.md": (
        "\n## Batch 24A.2 — Rich Indicators & Parity Catalogue\n\n"
        "- registre d'indicateurs Analytics riche, versionné et fingerprinté ;\n"
        "- snapshots Indicators typés avec warmup/availability explicites ;\n"
        "- causalité/prefix invariance ;\n"
        "- parité vérifiée EMA/RSI/MACD/ATR/Bollinger ;\n"
        "- divergences ADX et Volume Ratio explicites ;\n"
        "- MFI/CMF/OBV/VWAP/StochRSI/Donchian et rolling ranges ;\n"
        "- aucune modification du Feature Engine ni du pipeline de décision/trading.\n"
    ),
}


def append_once(path: Path, section: str) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return
    path.write_text(
        text.rstrip() + "\n\n" + MARKER + "\n" + section.strip() + "\n", encoding="utf-8"
    )


def main() -> None:
    root = Path(__file__).resolve().parent
    for relative, section in SECTIONS.items():
        append_once(root / relative, section)
        print(f"updated: {relative}")


if __name__ == "__main__":
    main()
