from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one anchor, found {count}. "
            "This patch expects Batch 16.10 Quick Test Fix."
        )
    return text.replace(old, new, 1)


def patch_backend(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False

    if "DeterministicAdvancedSpecialistMockProvider" not in text:
        anchor = "from app.services.backtest.runner import HistoricalReplayCancelledError\n"
        replacement = (
            "from app.services.backtest.advanced_mock import "
            "DeterministicAdvancedSpecialistMockProvider\n"
            + anchor
        )
        text = replace_once(text, anchor, replacement, label="advanced mock import")
        changed = True

    if "mock_agent_coverage: bool = False" not in text:
        anchor = "    cached_input_per_million_eur: Decimal | None = None\n"
        replacement = anchor + "    mock_agent_coverage: bool = False\n"
        text = replace_once(text, anchor, replacement, label="AIInput coverage field")
        changed = True

        old_validator = (
            '        if self.mode is BacktestAIMode.LIVE_EVAL:\n'
            '            if self.input_per_million_eur == 0 and self.output_per_million_eur == 0:\n'
            '                raise ValueError("LIVE_EVAL requires explicit non-zero model pricing")\n'
            '            if self.model_id.startswith("mock-"):\n'
            '                raise ValueError("LIVE_EVAL requires an explicit real model_id")\n'
            '        return self\n'
        )
        new_validator = (
            '        if self.mode is BacktestAIMode.LIVE_EVAL:\n'
            '            if self.input_per_million_eur == 0 and self.output_per_million_eur == 0:\n'
            '                raise ValueError("LIVE_EVAL requires explicit non-zero model pricing")\n'
            '            if self.model_id.startswith("mock-"):\n'
            '                raise ValueError("LIVE_EVAL requires an explicit real model_id")\n'
            '        if self.mock_agent_coverage and self.mode is not BacktestAIMode.MOCK:\n'
            '            raise ValueError("mock_agent_coverage is available only in MOCK mode")\n'
            '        return self\n'
        )
        text = replace_once(
            text,
            old_validator,
            new_validator,
            label="AIInput coverage validation",
        )

    if "class DeterministicAgentCoverageMockProvider:" not in text:
        anchor = "\n\nclass BacktestDashboardService:\n"
        coverage_class = r'''

class DeterministicAgentCoverageMockProvider:
    # Dashboard-only deterministic MOCK coverage wrapper.

    provider_name = "mock"

    def __init__(self, fallback: Any) -> None:
        self._fallback = fallback
        self._plan_index = 0

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        response = await self._fallback.complete(request)
        if request.schema_name != "ProfessorPlan":
            return response

        try:
            context = json.loads(request.input_text)
        except json.JSONDecodeError:
            return response
        if not isinstance(context, dict):
            return response

        raw_available = context.get("available_agents")
        if not isinstance(raw_available, list):
            return response

        available = sorted(
            {
                str(agent_id)
                for agent_id in raw_available
                if isinstance(agent_id, str) and agent_id.strip()
            }
        )
        if not available:
            return response

        crews = [[agent_id] for agent_id in available]
        crews.extend(
            [available[left], available[right]]
            for left in range(len(available))
            for right in range(left + 1, len(available))
        )
        selected = crews[self._plan_index % len(crews)]
        self._plan_index += 1

        try:
            payload = json.loads(response.output_text)
        except json.JSONDecodeError:
            return response
        if not isinstance(payload, dict):
            return response

        payload.update(
            {
                "decision": "MINI_CREW",
                "selected_agents": selected,
                "rationale": [
                    "dashboard deterministic MOCK agent coverage smoke test",
                    "selection restricted to orchestration available_agents",
                ],
                "request_more_analysis": False,
            }
        )
        return ProviderResponse(
            provider_request_id=response.provider_request_id,
            model_id=response.model_id,
            output_text=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            usage=response.usage,
            latency_ms=response.latency_ms,
        )
'''
        text = replace_once(
            text,
            anchor,
            coverage_class + anchor,
            label="coverage provider class",
        )
        changed = True

    old_mock = (
        "        mock_client = DeterministicBacktestMockProvider()\n"
        "        live_client = None\n"
    )
    new_mock = (
        "        mock_client: Any = DeterministicBacktestMockProvider()\n"
        "        if run.config.ai_mode is BacktestAIMode.MOCK and ai.mock_agent_coverage:\n"
        "            mock_client = DeterministicAgentCoverageMockProvider(\n"
        "                DeterministicAdvancedSpecialistMockProvider(mock_client)\n"
        "            )\n"
        "        live_client = None\n"
    )
    if old_mock in text:
        text = replace_once(text, old_mock, new_mock, label="coverage mock wiring")
        changed = True
    elif "ai.mock_agent_coverage" not in text:
        raise RuntimeError("coverage mock wiring anchor not found")

    if '"DeterministicAgentCoverageMockProvider",' not in text:
        anchor = '    "DeterministicBacktestMockProvider",\n'
        replacement = anchor + '    "DeterministicAgentCoverageMockProvider",\n'
        text = replace_once(text, anchor, replacement, label="coverage __all__")
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
        print(f"- patched {path}")
    else:
        print(f"- {path}: already patched")


def patch_js(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False

    if "let mockAgentCoverage = false;" not in text:
        anchor = "let traceAnimationChain = Promise.resolve();\n"
        text = replace_once(
            text,
            anchor,
            anchor + "let mockAgentCoverage = false;\n",
            label="coverage JS state",
        )
        changed = True

    if "mock_agent_coverage:" not in text:
        anchor = '      cached_input_per_million_eur: numberOrNull("cached-price"),\n'
        replacement = (
            anchor
            + '      mock_agent_coverage: mockAgentCoverage && $("ai-mode").value === "MOCK",\n'
        )
        text = replace_once(text, anchor, replacement, label="coverage payload")
        changed = True

    if "mockAgentCoverage = true;" not in text:
        old = (
            "  splitSelection = {\n"
            "    start,\n"
            "    designEnd: start + designBars - 1,\n"
            "    validationEnd: start + validationBoundaryBars - 1,\n"
            "    end: start + testBars - 1,\n"
            "  };\n"
            "  renderSplitSelection();\n"
        )
        new = (
            "  splitSelection = {\n"
            "    start,\n"
            "    designEnd: start + designBars - 1,\n"
            "    validationEnd: start + validationBoundaryBars - 1,\n"
            "    end: start + testBars - 1,\n"
            "  };\n"
            "  mockAgentCoverage = true;\n"
            "  renderSplitSelection();\n"
        )
        text = replace_once(text, old, new, label="quick test enables coverage")
        changed = True

    if "mockAgentCoverage = false;\n    splitSelection[key]" not in text:
        old = (
            "    if (!splitSelection) return;\n"
            "    splitSelection[key] = Number($(id).value);\n"
        )
        new = (
            "    if (!splitSelection) return;\n"
            "    mockAgentCoverage = false;\n"
            "    splitSelection[key] = Number($(id).value);\n"
        )
        text = replace_once(text, old, new, label="manual split disables coverage")
        changed = True

    if "mockAgentCoverage = false;\n  splitSelection.start = 0;" not in text:
        old = (
            "  if (!datasetPreview || !splitSelection) return;\n"
            "  splitSelection.start = 0;\n"
        )
        new = (
            "  if (!datasetPreview || !splitSelection) return;\n"
            "  mockAgentCoverage = false;\n"
            "  splitSelection.start = 0;\n"
        )
        text = replace_once(text, old, new, label="full split disables coverage")
        changed = True

    if "mockAgentCoverage = false;\n  splitSelection = { ...suggestedSplitSelection };" not in text:
        old = (
            "  if (!suggestedSplitSelection) return;\n"
            "  splitSelection = { ...suggestedSplitSelection };\n"
        )
        new = (
            "  if (!suggestedSplitSelection) return;\n"
            "  mockAgentCoverage = false;\n"
            "  splitSelection = { ...suggestedSplitSelection };\n"
        )
        text = replace_once(text, old, new, label="reset split disables coverage")
        changed = True

    expected_csv = (
        "  datasetPreview = null;\n"
        "  splitSelection = null;\n"
        "  suggestedSplitSelection = null;\n"
        "  mockAgentCoverage = false;\n"
    )
    if expected_csv not in text:
        old = (
            "  datasetPreview = null;\n"
            "  splitSelection = null;\n"
            "  suggestedSplitSelection = null;\n"
        )
        text = replace_once(
            text,
            old,
            expected_csv,
            label="file change disables coverage",
        )
        changed = True

    if 'if ($("ai-mode").value !== "MOCK") mockAgentCoverage = false;' not in text:
        old = (
            '$("ai-mode").addEventListener("change", () => {\n'
            '  if ($("ai-mode").value === "MOCK" && !$("model-id").value.trim()) {\n'
        )
        new = (
            '$("ai-mode").addEventListener("change", () => {\n'
            '  if ($("ai-mode").value !== "MOCK") mockAgentCoverage = false;\n'
            '  if ($("ai-mode").value === "MOCK" && !$("model-id").value.trim()) {\n'
        )
        text = replace_once(
            text,
            old,
            new,
            label="AI mode disables coverage outside MOCK",
        )
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
        print(f"- patched {path}")
    else:
        print(f"- {path}: already patched")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Batch 16.10 MOCK agent coverage smoke-test patch"
    )
    parser.add_argument("--root", default=".", help="Money-Heist repository root")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    required = [
        root / "app/dashboard/backtest.py",
        root / "app/dashboard/static/backtest.js",
        root / "tests/dashboard/test_backtest_agent_coverage.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(
            "Extract the ZIP at the repository root first. Missing:\n- "
            + "\n- ".join(missing)
        )

    patch_backend(root / "app/dashboard/backtest.py")
    patch_js(root / "app/dashboard/static/backtest.js")

    print("\nMOCK agent coverage patch applied.")
    print("Test rapide + MOCK now rotates through eligible specialists and 2-agent crews.")
    print("Rio/Denver remain gated by their real specialist-context eligibility.")
    print("\nValidate with:")
    print("  uv run pytest -q tests/dashboard/test_backtest_agent_coverage.py")
    print("  uv run pytest -q tests/dashboard")
    print("  uv run pytest -q")
    print("\nNormal MOCK, CACHED, LIVE_EVAL, Risk Engine and PaperBroker semantics are unchanged.")


if __name__ == "__main__":
    main()
