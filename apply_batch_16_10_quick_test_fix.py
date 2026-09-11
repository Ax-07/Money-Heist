from __future__ import annotations

import argparse
import re
from pathlib import Path


NEW_FUNCTION = r'''// Batch 16.10 — Quick test preset
function applyQuickTestSplit() {
  if (!datasetPreview || !datasetPreview.candle_count || !splitSelection) {
    throw new Error("Prévisualise d'abord le dataset avant d'utiliser Test rapide.");
  }

  const available = datasetPreview.candle_count;
  const warmupBars = 35;
  const targetTestBars = 100;
  const minimumTestBars = 6;

  if (available < warmupBars + minimumTestBars) {
    throw new Error(
      `Test rapide nécessite au moins ${warmupBars + minimumTestBars} bougies `
      + `(${warmupBars} warm-up + ${minimumTestBars} test).`,
    );
  }

  // Smoke test multi-agents :
  // - les 35 premières bougies servent de warm-up aux features ;
  // - puis on teste au maximum 100 bougies ;
  // - DESIGN / VALIDATION / OOS = 60 / 20 / 20.
  // La fenêtre est volontairement placée près du début du dataset afin que le
  // HistoricalReplayRunner n'ait pas à parcourir inutilement tout l'historique.
  const start = warmupBars;
  const testBars = Math.min(targetTestBars, available - start);

  const designBars = Math.max(1, Math.floor(testBars * 0.60));
  const validationBoundaryBars = Math.max(
    designBars + 1,
    Math.floor(testBars * 0.80),
  );

  splitSelection = {
    start,
    designEnd: start + designBars - 1,
    validationEnd: start + validationBoundaryBars - 1,
    end: start + testBars - 1,
  };
  renderSplitSelection();
}
'''


def patch_js(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    if "const warmupBars = 35;" in text and "const targetTestBars = 100;" in text:
        print(f"- {path}: already patched")
        return

    pattern = re.compile(
        r"// Batch 16\.10 — Quick test preset\n"
        r"function applyQuickTestSplit\(\) \{\n"
        r".*?"
        r"\n\}\n",
        re.DOTALL,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(
            f"applyQuickTestSplit: expected exactly one function, found {len(matches)}. "
            "This patch expects Batch 16.10 v2."
        )

    text = pattern.sub(NEW_FUNCTION, text, count=1)
    path.write_text(text, encoding="utf-8")
    print(f"- patched {path}")


def patch_test(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    if 'assert "const targetTestBars = 100" in js' in text:
        print(f"- {path}: already patched")
        return

    old = (
        '    assert "Math.min(720, available)" in js\n'
        '    assert "Math.floor(testBars * 0.60)" in js\n'
        '    assert "Math.floor(testBars * 0.80)" in js\n'
        '    assert "designEnd: start + designBars - 1" in js\n'
        '    assert "validationEnd: start + validationBoundaryBars - 1" in js\n'
        '    assert "end: available - 1" in js\n'
    )
    new = (
        '    assert "const warmupBars = 35" in js\n'
        '    assert "const targetTestBars = 100" in js\n'
        '    assert "Math.min(targetTestBars, available - start)" in js\n'
        '    assert "Math.floor(testBars * 0.60)" in js\n'
        '    assert "Math.floor(testBars * 0.80)" in js\n'
        '    assert "designEnd: start + designBars - 1" in js\n'
        '    assert "validationEnd: start + validationBoundaryBars - 1" in js\n'
        '    assert "end: start + testBars - 1" in js\n'
    )

    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"quick test assertions: expected exactly one anchor, found {count}."
        )

    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"- patched {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix Batch 16.10 quick-test preset for agent communication smoke tests"
    )
    parser.add_argument("--root", default=".", help="Money-Heist repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    js_path = root / "app/dashboard/static/backtest.js"
    test_path = root / "tests/dashboard/test_backtest_defaults.py"

    missing = [str(p) for p in (js_path, test_path) if not p.is_file()]
    if missing:
        raise SystemExit("Missing required files:\n- " + "\n- ".join(missing))

    patch_js(js_path)
    patch_test(test_path)

    print("\nQuick-test patch applied.")
    print("Preset:")
    print("  warm-up     = 35 bars")
    print("  DESIGN      = 60 bars")
    print("  VALIDATION  = 20 bars")
    print("  OOS         = 20 bars")
    print("  total test  = 100 bars max")
    print("\nValidate with:")
    print("  uv run pytest -q tests/dashboard/test_backtest_defaults.py")
    print("  uv run pytest -q tests/dashboard")
    print("  uv run pytest -q")
    print("\nNo backend, Risk Engine, PaperBroker or LIVE component was modified.")


if __name__ == "__main__":
    main()
