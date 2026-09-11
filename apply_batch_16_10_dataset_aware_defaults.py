from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "Batch 16.10 — Dataset-aware defaults"
QUICK_MARKER = "Batch 16.10 — Quick test preset"


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one anchor, found {count}. "
            "Apply this batch after Batch 16.9."
        )
    return text.replace(old, new, 1)


def patch_html(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False

    if MARKER not in text:
        text = replace_once(
            text,
            '<input id="symbol" value="BTC/EUR" required>',
            '<input id="symbol" value="BTC/USDC" required>',
            label="default symbol",
        )
        text = replace_once(
            text,
            '''              <option>1m</option><option selected>5m</option><option>15m</option>
              <option>30m</option><option>1h</option><option>4h</option><option>1d</option>''',
            '''              <option>1m</option><option>5m</option><option>15m</option>
              <option>30m</option><option selected>1h</option><option>4h</option><option>1d</option>''',
            label="default timeframe",
        )
        text = replace_once(
            text,
            '<input id="source" value="dashboard_csv" required>',
            '<input id="source" value="binance_spot_csv" required>',
            label="default source",
        )
        text = replace_once(
            text,
            '''        <p class="notice">
          Ces valeurs doivent venir de la configuration ou des métadonnées exchange.
          Elles ne sont volontairement pas inventées par le Dashboard.
        </p>
        <div class="grid four">
          <label>qty_step<input id="qty-step" type="number" step="any" placeholder="ex. 0.00000001" required></label>
          <label>min_qty<input id="min-qty" type="number" step="any" required></label>
          <label>min_notional €<input id="min-notional" type="number" step="any" required></label>
          <label>max_qty (optionnel)<input id="max-qty" type="number" step="any"></label>
          <label>max_leverage<input id="market-leverage" type="number" step="0.1" value="1"></label>
        </div>''',
            '''        <p class="notice">
          <strong id="market-preset-state">Preset Binance Spot BTC/USDC · 2026-09-11</strong><br>
          Les contraintes sont préremplies pour faciliter le backtest. Elles restent éditables
          et doivent être revérifiées contre les métadonnées exchange avant tout usage officiel.
        </p>
        <div class="grid four">
          <label>qty_step BTC<input id="qty-step" type="number" step="any" value="0.00001" required></label>
          <label>min_qty BTC<input id="min-qty" type="number" step="any" value="0.00001" required></label>
          <label>min_notional <span id="min-notional-unit">USDC</span><input id="min-notional" type="number" step="any" value="5" required></label>
          <label>max_qty BTC<input id="max-qty" type="number" step="any" value="9000"></label>
          <label>max_leverage<input id="market-leverage" type="number" step="0.1" value="1"></label>
        </div>''',
            label="market constraints preset",
        )
        text = text.replace(
            '<form id="campaign-form" class="panel form-panel">',
            f'<!-- {MARKER} -->\n      <form id="campaign-form" class="panel form-panel">',
            1,
        )
        changed = True

    if 'id="split-quick-test"' not in text:
        text = replace_once(
            text,
            '''            <div class="split-actions">
              <button type="button" id="split-full" class="secondary">Tout le dataset</button>
              <button type="button" id="split-reset" class="secondary">Réinitialiser 60 / 20 / 20</button>
            </div>''',
            '''            <div class="split-actions">
              <button type="button" id="split-quick-test" class="secondary">Test rapide</button>
              <button type="button" id="split-full" class="secondary">Tout le dataset</button>
              <button type="button" id="split-reset" class="secondary">Réinitialiser 60 / 20 / 20</button>
            </div>''',
            label="quick test button",
        )
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
        print(f"- patched {path}")
    else:
        print(f"- {path}: already patched")


def patch_js(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False

    if "const MARKET_PRESETS" not in text:
        original_handler = '''$("csv-file").addEventListener("change", () => {
  csvText = "";
  datasetPreview = null;
  splitSelection = null;
  suggestedSplitSelection = null;
  $("split-editor").classList.add("is-disabled");
  for (const id of ["split-start", "split-design-end", "split-validation-end", "split-end"]) {
    $(id).disabled = true;
  }
});
'''
        defaults_block = r'''// Batch 16.10 — Dataset-aware defaults
const MARKET_PRESETS = {
  "BTC/USDC": {
    label: "Binance Spot BTC/USDC · 2026-09-11",
    source: "binance_spot_csv",
    qtyStep: "0.00001",
    minQty: "0.00001",
    minNotional: "5",
    maxQty: "9000",
    maxLeverage: "1",
  },
};

function normalizeDatasetFilename(filename) {
  return String(filename || "")
    .toUpperCase()
    .replace(/\.[^.]+$/, "")
    .replace(/[^A-Z0-9]+/g, "_");
}

function detectDatasetIdentity(filename) {
  const normalized = normalizeDatasetFilename(filename);
  let symbol = null;
  let timeframe = null;
  let source = null;

  if (
    normalized.includes("BTCUSDC")
    || normalized.includes("BTC_USDC")
    || normalized.includes("BTC_USD_C")
  ) {
    symbol = "BTC/USDC";
  }

  if (
    /(^|_)1H($|_)/.test(normalized)
    || /(^|_)H1($|_)/.test(normalized)
    || /(^|_)60M($|_)/.test(normalized)
  ) {
    timeframe = "1h";
  } else if (/(^|_)4H($|_)/.test(normalized) || /(^|_)H4($|_)/.test(normalized)) {
    timeframe = "4h";
  } else if (/(^|_)15M($|_)/.test(normalized)) {
    timeframe = "15m";
  } else if (/(^|_)5M($|_)/.test(normalized)) {
    timeframe = "5m";
  } else if (/(^|_)1M($|_)/.test(normalized)) {
    timeframe = "1m";
  }

  if (normalized.includes("BINANCE")) {
    source = "binance_spot_csv";
  }
  return { symbol, timeframe, source };
}

function quoteAsset(symbol) {
  const parts = String(symbol || "").split("/");
  return parts.length === 2 ? parts[1] : "quote";
}

function applyMarketPreset(symbol, { forceSource = false } = {}) {
  const preset = MARKET_PRESETS[symbol];
  $("min-notional-unit").textContent = quoteAsset(symbol);

  if (!preset) {
    $("market-preset-state").textContent =
      `Aucun preset versionné pour ${symbol || "ce symbole"} — vérification manuelle requise`;
    return;
  }

  $("qty-step").value = preset.qtyStep;
  $("min-qty").value = preset.minQty;
  $("min-notional").value = preset.minNotional;
  $("max-qty").value = preset.maxQty;
  $("market-leverage").value = preset.maxLeverage;
  $("market-preset-state").textContent = `Preset ${preset.label}`;

  if (forceSource && preset.source) {
    $("source").value = preset.source;
  }
}

function applyDatasetDefaultsFromFile(file) {
  if (!file) return;
  const detected = detectDatasetIdentity(file.name);

  if (detected.symbol) {
    $("symbol").value = detected.symbol;
    applyMarketPreset(detected.symbol, { forceSource: true });
  }
  if (detected.timeframe) {
    $("timeframe").value = detected.timeframe;
  }
  if (detected.source) {
    $("source").value = detected.source;
  }
}

$("symbol").addEventListener("change", () => {
  applyMarketPreset($("symbol").value.trim());
});

$("csv-file").addEventListener("change", () => {
  csvText = "";
  datasetPreview = null;
  splitSelection = null;
  suggestedSplitSelection = null;
  $("split-editor").classList.add("is-disabled");
  for (const id of ["split-start", "split-design-end", "split-validation-end", "split-end"]) {
    $(id).disabled = true;
  }
  applyDatasetDefaultsFromFile($("csv-file").files?.[0]);
});
'''
        text = replace_once(
            text,
            original_handler,
            defaults_block,
            label="dataset-aware defaults JS",
        )
        changed = True

    if "function applyQuickTestSplit()" not in text:
        quick_function = r'''
// Batch 16.10 — Quick test preset
function applyQuickTestSplit() {
  if (!datasetPreview || !datasetPreview.candle_count || !splitSelection) {
    throw new Error("Prévisualise d'abord le dataset avant d'utiliser Test rapide.");
  }

  const available = datasetPreview.candle_count;
  if (available < 6) {
    throw new Error("Le dataset doit contenir au moins 6 bougies pour DESIGN / VALIDATION / OOS.");
  }

  // 720 bars = 30 jours sur BTC/USDC en 1h.
  // Si le dataset est plus court, toute sa plage est utilisée.
  const testBars = Math.min(720, available);
  const start = available - testBars;
  const designBars = Math.max(1, Math.floor(testBars * 0.60));
  const validationBoundaryBars = Math.max(
    designBars + 1,
    Math.floor(testBars * 0.80),
  );

  splitSelection = {
    start,
    designEnd: start + designBars - 1,
    validationEnd: start + validationBoundaryBars - 1,
    end: available - 1,
  };
  renderSplitSelection();
}
'''
        anchor = '''$("symbol").addEventListener("change", () => {
  applyMarketPreset($("symbol").value.trim());
});
'''
        text = replace_once(
            text,
            anchor,
            quick_function + "\n" + anchor,
            label="quick test function",
        )
        changed = True

    if '$("split-quick-test").addEventListener("click"' not in text:
        listener = r'''
$("split-quick-test").addEventListener("click", () => {
  try {
    applyQuickTestSplit();
  } catch (error) {
    showError(error);
  }
});
'''
        anchor = '''$("symbol").addEventListener("change", () => {
  applyMarketPreset($("symbol").value.trim());
});
'''
        text = replace_once(
            text,
            anchor,
            anchor + listener,
            label="quick test listener",
        )
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
        print(f"- patched {path}")
    else:
        print(f"- {path}: already patched")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Batch 16.10 dataset-aware defaults + one-click quick test"
    )
    parser.add_argument("--root", default=".", help="Money-Heist repository root")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    required = [
        root / "app/dashboard/static/backtest.html",
        root / "app/dashboard/static/backtest.js",
        root / "tests/dashboard/test_backtest_defaults.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(
            "Extract the Batch 16.10 v2 ZIP at the repository root first. Missing:\n- "
            + "\n- ".join(missing)
        )

    patch_html(root / "app/dashboard/static/backtest.html")
    patch_js(root / "app/dashboard/static/backtest.js")

    print("\nBatch 16.10 v2 applied.")
    print("Validate with:")
    print("  uv run pytest -q tests/dashboard/test_backtest_defaults.py")
    print("  uv run pytest -q tests/dashboard")
    print("  uv run pytest -q")
    print("\nThe Test rapide button only edits the timeline; it never starts a campaign.")


if __name__ == "__main__":
    main()
