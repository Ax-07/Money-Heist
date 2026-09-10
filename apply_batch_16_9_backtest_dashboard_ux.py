from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

BASE_COMMIT = "6d32f5597c0a3e8d86aabe977fc02dff894048a4"
MARKER = "Batch 16.9 — Backtest Dashboard UX"


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one anchor, found {count}. "
            "The working tree may not match the reference commit."
        )
    return text.replace(old, new, 1)


def git_head(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def patch_backend(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"- {path}: already patched")
        return

    text = replace_once(
        text,
        '''class DatasetPreview(FrozenModel):
    dataset_id: str
    version: str
    content_sha256: str
    symbol: str
    timeframe: str
    source: str
    candle_count: int
    start_at: datetime
    end_at: datetime
    is_valid: bool
    gap_count: int
    has_duplicates: bool
    missing_fields: tuple[str, ...]
    suggested_split: SplitInput | None = None
''',
        '''class SplitIndexView(FrozenModel):
    design_start: int = Field(ge=0)
    design_end: int = Field(ge=0)
    validation_start: int = Field(ge=0)
    validation_end: int = Field(ge=0)
    oos_start: int = Field(ge=0)
    oos_end: int = Field(ge=0)


class AgentDescriptorView(FrozenModel):
    agent: str
    role: str
    state: str
    core: bool


class DatasetPreview(FrozenModel):
    dataset_id: str
    version: str
    content_sha256: str
    symbol: str
    timeframe: str
    source: str
    candle_count: int
    start_at: datetime
    end_at: datetime
    is_valid: bool
    gap_count: int
    has_duplicates: bool
    missing_fields: tuple[str, ...]
    suggested_split: SplitInput | None = None
    candle_close_ms: tuple[int, ...] = ()
    suggested_split_indices: SplitIndexView | None = None
''',
        label="DatasetPreview",
    )

    text = replace_once(
        text,
        '''class AgentTraceView(FrozenModel):
    sequence: int
    observed_at: datetime
    role: BacktestPeriodRole
    opportunity_id: str
    agent: str
    phase: str
    title: str
    details: dict[str, Any] = Field(default_factory=dict)
''',
        '''class AgentTraceView(FrozenModel):
    sequence: int
    observed_at: datetime
    role: BacktestPeriodRole
    opportunity_id: str
    agent: str
    phase: str
    title: str
    details: dict[str, Any] = Field(default_factory=dict)
    targets: tuple[str, ...] = ()
''',
        label="AgentTraceView",
    )

    text = replace_once(
        text,
        '''    agent_traces: tuple[AgentTraceView, ...] = ()
    error: str | None = None
''',
        '''    agent_traces: tuple[AgentTraceView, ...] = ()
    active_agents: tuple[str, ...] = ()
    error: str | None = None
''',
        label="CampaignProgressView.active_agents",
    )

    text = replace_once(
        text,
        '''class BacktestCapabilities(FrozenModel):
    modes: tuple[BacktestAIMode, ...]
    live_eval_available: bool
    cache_entries: int
    supported_timeframes: tuple[str, ...]
    paper_only: bool = True
    live_trading: bool = False
    campaign_cancel: bool = True
    campaign_progress: bool = True
    agent_traces: bool = True
''',
        '''class BacktestCapabilities(FrozenModel):
    modes: tuple[BacktestAIMode, ...]
    live_eval_available: bool
    cache_entries: int
    supported_timeframes: tuple[str, ...]
    agents: tuple[AgentDescriptorView, ...] = ()
    paper_only: bool = True
    live_trading: bool = False
    campaign_cancel: bool = True
    campaign_progress: bool = True
    agent_traces: bool = True
    agent_activity: bool = True
''',
        label="BacktestCapabilities",
    )

    text = replace_once(
        text,
        '''    traces: list[AgentTraceView] = field(default_factory=list)
    trace_sequence: int = 0
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
''',
        '''    traces: list[AgentTraceView] = field(default_factory=list)
    trace_sequence: int = 0
    active_agents: set[str] = field(default_factory=set)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
''',
        label="_CampaignRuntime.active_agents",
    )

    text = replace_once(
        text,
        '''class BacktestDashboardError(RuntimeError):
    pass


class DeterministicBacktestMockProvider:
''',
        '''class BacktestDashboardError(RuntimeError):
    pass


# Batch 16.9 — Backtest Dashboard UX
_SCHEMA_AGENT = {
    "ProfessorPlan": "professor",
    "ProfessorFinalDecision": "professor",
    "PalermoReview": "palermo",
    "BerlinAnalysis": "berlin",
    "TokyoAnalysis": "tokyo",
    "NairobiAnalysis": "nairobi",
    "RioAnalysis": "rio",
    "DenverAnalysis": "denver",
}


class ObservableBacktestAIClient:
    def __init__(self, delegate: Any, runtime: _CampaignRuntime) -> None:
        self._delegate = delegate
        self._runtime = runtime

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        agent = _SCHEMA_AGENT.get(request.schema_name)
        if agent is not None:
            self._runtime.active_agents.add(agent)
        try:
            return await self._delegate.complete(request)
        finally:
            if agent is not None:
                self._runtime.active_agents.discard(agent)


class DeterministicBacktestMockProvider:
''',
        label="ObservableBacktestAIClient",
    )

    text = replace_once(
        text,
        '''            executed_order_count=runtime.executed_order_count,
            agent_traces=tuple(runtime.traces[-120:]),
            error=runtime.error,
''',
        '''            executed_order_count=runtime.executed_order_count,
            agent_traces=tuple(runtime.traces[-120:]),
            active_agents=tuple(sorted(runtime.active_agents)),
            error=runtime.error,
''',
        label="_progress_view",
    )

    text = replace_once(
        text,
        '''    def capabilities(self) -> BacktestCapabilities:
        return BacktestCapabilities(
            modes=tuple(BacktestAIMode),
            live_eval_available=bool(os.getenv("OPENAI_API_KEY", "").strip()),
            cache_entries=len(self._cache),
            supported_timeframes=tuple(_TIMEFRAME_SECONDS),
        )
''',
        '''    def capabilities(self) -> BacktestCapabilities:
        entries = (*CORE_AGENT_REGISTRY.list(), *SPECIALIST_AGENT_REGISTRY.list())
        agents = tuple(
            AgentDescriptorView(
                agent=entry.agent_id,
                role=entry.role.value,
                state=entry.state.value,
                core=entry.core,
            )
            for entry in entries
        )
        return BacktestCapabilities(
            modes=tuple(BacktestAIMode),
            live_eval_available=bool(os.getenv("OPENAI_API_KEY", "").strip()),
            cache_entries=len(self._cache),
            supported_timeframes=tuple(_TIMEFRAME_SECONDS),
            agents=agents,
        )
''',
        label="capabilities agents",
    )

    text = replace_once(
        text,
        '''        preview = DatasetPreview(
            dataset_id=dataset.dataset_id,
            version=dataset.version,
            content_sha256=dataset.content_sha256,
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            source=dataset.source,
            candle_count=dataset.candle_count,
            start_at=dataset.start_at,
            end_at=dataset.end_at,
            is_valid=bool(imported.quality.is_valid),
            gap_count=int(imported.quality.gap_count),
            has_duplicates=bool(imported.quality.has_duplicates),
            missing_fields=tuple(imported.quality.missing_fields),
            suggested_split=self._suggest_split(imported.candles),
        )
''',
        '''        suggested_indices = self._suggest_split_indices(imported.candles)
        preview = DatasetPreview(
            dataset_id=dataset.dataset_id,
            version=dataset.version,
            content_sha256=dataset.content_sha256,
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            source=dataset.source,
            candle_count=dataset.candle_count,
            start_at=dataset.start_at,
            end_at=dataset.end_at,
            is_valid=bool(imported.quality.is_valid),
            gap_count=int(imported.quality.gap_count),
            has_duplicates=bool(imported.quality.has_duplicates),
            missing_fields=tuple(imported.quality.missing_fields),
            suggested_split=self._split_from_indices(imported.candles, suggested_indices),
            candle_close_ms=tuple(
                int(candle.close_time.timestamp() * 1000)
                for candle in imported.candles
            ),
            suggested_split_indices=suggested_indices,
        )
''',
        label="preview candle axis",
    )

    text = replace_once(
        text,
        '''    @staticmethod
    def _suggest_split(candles: tuple[Any, ...]) -> SplitInput | None:
        if len(candles) < 6:
            return None
        design_end_index = max(1, int(len(candles) * 0.60)) - 1
        validation_end_index = max(design_end_index + 1, int(len(candles) * 0.80)) - 1
        validation_start_index = design_end_index + 1
        oos_start_index = validation_end_index + 1
        if oos_start_index >= len(candles):
            return None
        return SplitInput(
            design_start=candles[0].close_time,
            design_end=candles[design_end_index].close_time,
            validation_start=candles[validation_start_index].close_time,
            validation_end=candles[validation_end_index].close_time,
            oos_start=candles[oos_start_index].close_time,
            oos_end=candles[-1].close_time,
        )
''',
        '''    @staticmethod
    def _suggest_split_indices(candles: tuple[Any, ...]) -> SplitIndexView | None:
        if len(candles) < 6:
            return None
        design_end_index = max(1, int(len(candles) * 0.60)) - 1
        validation_end_index = max(design_end_index + 1, int(len(candles) * 0.80)) - 1
        validation_start_index = design_end_index + 1
        oos_start_index = validation_end_index + 1
        if oos_start_index >= len(candles):
            return None
        return SplitIndexView(
            design_start=0,
            design_end=design_end_index,
            validation_start=validation_start_index,
            validation_end=validation_end_index,
            oos_start=oos_start_index,
            oos_end=len(candles) - 1,
        )

    @staticmethod
    def _split_from_indices(
        candles: tuple[Any, ...],
        indices: SplitIndexView | None,
    ) -> SplitInput | None:
        if indices is None:
            return None
        return SplitInput(
            design_start=candles[indices.design_start].close_time,
            design_end=candles[indices.design_end].close_time,
            validation_start=candles[indices.validation_start].close_time,
            validation_end=candles[indices.validation_end].close_time,
            oos_start=candles[indices.oos_start].close_time,
            oos_end=candles[indices.oos_end].close_time,
        )

    @classmethod
    def _suggest_split(cls, candles: tuple[Any, ...]) -> SplitInput | None:
        return cls._split_from_indices(candles, cls._suggest_split_indices(candles))
''',
        label="split index helpers",
    )

    text = replace_once(
        text,
        '''        backtest_client = BacktestAIClient.from_run(
            run,
            cache=self._cache,
            mock_client=mock_client if run.config.ai_mode is BacktestAIMode.MOCK else None,
            live_client=live_client,
        )
        gateway = AIGateway(
            router=router,
            clients={provider_name: backtest_client},
''',
        '''        backtest_client = BacktestAIClient.from_run(
            run,
            cache=self._cache,
            mock_client=mock_client if run.config.ai_mode is BacktestAIMode.MOCK else None,
            live_client=live_client,
        )
        observable_client = (
            ObservableBacktestAIClient(backtest_client, runtime)
            if runtime is not None
            else backtest_client
        )
        gateway = AIGateway(
            router=router,
            clients={provider_name: observable_client},
''',
        label="observable AI wrapper",
    )

    text = replace_once(
        text,
        '''        def add(agent: str, phase: str, title: str, value: Any) -> None:
            if value is None:
                return
''',
        '''        def add(
            agent: str,
            phase: str,
            title: str,
            value: Any,
            *,
            targets: tuple[str, ...] = (),
        ) -> None:
            if value is None:
                return
''',
        label="trace add signature",
    )

    text = replace_once(
        text,
        '''                    phase=phase,
                    title=title,
                    details=details,
                )
''',
        '''                    phase=phase,
                    title=title,
                    details=details,
                    targets=targets,
                )
''',
        label="trace targets payload",
    )

    text = replace_once(
        text,
        '''            add(
                "professor",
                "PLAN",
                f"{getattr(plan, 'decision', 'PLAN')} · {selected}",
                plan,
            )
''',
        '''            add(
                "professor",
                "PLAN",
                f"{getattr(plan, 'decision', 'PLAN')} · {selected}",
                plan,
                targets=tuple(getattr(plan, "selected_agents", ())),
            )
''',
        label="Professor PLAN targets",
    )

    text = replace_once(
        text,
        '''            add(
                specialist.agent_id,
                "ANALYSIS",
                f"{stance}{suffix}".strip(" ·"),
                analysis,
            )
''',
        '''            add(
                specialist.agent_id,
                "ANALYSIS",
                f"{stance}{suffix}".strip(" ·"),
                analysis,
                targets=("professor",),
            )
''',
        label="specialist targets",
    )

    text = replace_once(
        text,
        '''            add(
                "palermo",
                "RED_TEAM",
                f"{getattr(review, 'verdict', 'REVIEW')} · sévérité "
                f"{getattr(review, 'severity', '—')}",
                review,
            )

        decision = getattr(orchestration, "professor_decision", None)
        if decision is not None:
            add(
                "professor",
                "FINAL",
                f"{decision.direction} · confiance {decision.confidence:.2f}",
                decision,
            )

        risk_record = getattr(pipeline_result, "risk_record", None)
''',
        '''            add(
                "palermo",
                "RED_TEAM",
                f"{getattr(review, 'verdict', 'REVIEW')} · sévérité "
                f"{getattr(review, 'severity', '—')}",
                review,
                targets=("professor",),
            )

        risk_record = getattr(pipeline_result, "risk_record", None)
        decision = getattr(orchestration, "professor_decision", None)
        if decision is not None:
            add(
                "professor",
                "FINAL",
                f"{decision.direction} · confiance {decision.confidence:.2f}",
                decision,
                targets=("risk_engine",) if risk_record is not None else (),
            )

''',
        label="Palermo/final targets",
    )

    text = replace_once(
        text,
        '''    "BacktestCapabilities",
    "BacktestDashboardError",
''',
        '''    "AgentDescriptorView",
    "BacktestCapabilities",
    "BacktestDashboardError",
''',
        label="__all__ AgentDescriptorView",
    )
    text = replace_once(
        text,
        '''    "DatasetPreview",
    "DeterministicBacktestMockProvider",
''',
        '''    "DatasetPreview",
    "DeterministicBacktestMockProvider",
    "ObservableBacktestAIClient",
''',
        label="__all__ ObservableBacktestAIClient",
    )
    text = replace_once(
        text,
        '''    "RiskInput",
    "SplitInput",
''',
        '''    "RiskInput",
    "SplitIndexView",
    "SplitInput",
''',
        label="__all__ SplitIndexView",
    )

    path.write_text(text, encoding="utf-8")
    print(f"- patched {path}")


def patch_html(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if 'id="split-editor"' in text:
        print(f"- {path}: already patched")
        return

    text = replace_once(
        text,
        '''        <div class="grid three">
          <label>DESIGN début<input id="design-start" type="datetime-local" step="1" required></label>
          <label>DESIGN fin<input id="design-end" type="datetime-local" step="1" required></label>
          <span></span>
          <label>VALIDATION début<input id="validation-start" type="datetime-local" step="1" required></label>
          <label>VALIDATION fin<input id="validation-end" type="datetime-local" step="1" required></label>
          <span></span>
          <label>OOS début<input id="oos-start" type="datetime-local" step="1" required></label>
          <label>OOS fin<input id="oos-end" type="datetime-local" step="1" required></label>
        </div>
''',
        '''        <div id="split-editor" class="split-editor is-disabled">
          <div class="split-toolbar">
            <div>
              <span class="muted">Plage réellement disponible</span>
              <strong id="dataset-range-label">Prévisualise un dataset pour activer la timeline.</strong>
            </div>
            <div class="split-actions">
              <button type="button" id="split-full" class="secondary">Tout le dataset</button>
              <button type="button" id="split-reset" class="secondary">Réinitialiser 60 / 20 / 20</button>
            </div>
          </div>
          <div class="split-timeline" aria-label="Répartition DESIGN VALIDATION OOS">
            <div id="segment-before" class="split-segment unused"></div>
            <div id="segment-design" class="split-segment design"><span>DESIGN</span></div>
            <div id="segment-validation" class="split-segment validation"><span>VALIDATION</span></div>
            <div id="segment-oos" class="split-segment oos"><span>OOS</span></div>
            <div id="segment-after" class="split-segment unused"></div>
          </div>
          <div class="split-control-grid">
            <label>Début de la plage
              <input id="split-start" type="range" min="0" max="1" value="0" disabled>
              <span id="split-start-value" class="range-value">—</span>
            </label>
            <label>Fin DESIGN
              <input id="split-design-end" type="range" min="0" max="1" value="0" disabled>
              <span id="split-design-end-value" class="range-value">—</span>
            </label>
            <label>Fin VALIDATION
              <input id="split-validation-end" type="range" min="0" max="1" value="0" disabled>
              <span id="split-validation-end-value" class="range-value">—</span>
            </label>
            <label>Fin de la plage OOS
              <input id="split-end" type="range" min="0" max="1" value="1" disabled>
              <span id="split-end-value" class="range-value">—</span>
            </label>
          </div>
          <div class="split-summary">
            <article class="split-card design">
              <span>DESIGN</span><strong id="design-bars">—</strong><div id="design-dates">—</div>
            </article>
            <article class="split-card validation">
              <span>VALIDATION</span><strong id="validation-bars">—</strong><div id="validation-dates">—</div>
            </article>
            <article class="split-card oos">
              <span>OOS</span><strong id="oos-bars">—</strong><div id="oos-dates">—</div>
            </article>
          </div>
        </div>
''',
        label="period selector HTML",
    )

    text = replace_once(
        text,
        '''      <div id="agent-traces" class="agent-traces empty">
        Aucune trace agent pour le moment.
      </div>
''',
        '''      <div class="crew-legend">
        <span><i class="legend-dot live"></i> appel en cours</span>
        <span><i class="legend-dot recent"></i> événement audité récent</span>
        <span><i class="legend-dot idle"></i> disponible / inactif</span>
      </div>
      <div id="crew-stage" class="crew-stage">
        <svg id="crew-links" class="crew-links" aria-hidden="true">
          <defs>
            <marker id="flow-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
              <path d="M0,0 L0,6 L6,3 z"></path>
            </marker>
          </defs>
        </svg>
        <div id="agent-cards" class="agent-card-grid"></div>
      </div>
      <details class="trace-journal" open>
        <summary>Journal structuré audité</summary>
        <div id="agent-traces" class="agent-traces empty">
          Aucune trace agent pour le moment.
        </div>
      </details>
''',
        label="crew stage HTML",
    )

    path.write_text(text, encoding="utf-8")
    print(f"- patched {path}")


def patch_js(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "let splitSelection = null;" in text:
        print(f"- {path}: already patched")
        return

    text = replace_once(
        text,
        '''let activeCampaignId = null;
let pollTimer = null;
''',
        '''let activeCampaignId = null;
let pollTimer = null;
let splitSelection = null;
let suggestedSplitSelection = null;
let agentDescriptors = [];
let lastTraceSequence = 0;
let traceAnimationChain = Promise.resolve();
''',
        label="JS state",
    )

    text = replace_once(
        text,
        '''function isoLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function utcFromLocal(id) {
  const value = $(id).value;
  if (!value) throw new Error(`${id} est requis`);
  return new Date(value).toISOString();
}
''',
        '''function formatCandle(ms) {
  if (ms === undefined || ms === null) return "—";
  return new Date(ms).toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "medium",
  });
}
''',
        label="datetime helpers",
    )

    text = replace_once(
        text,
        '''function setSplit(split) {
  if (!split) return;
  $("design-start").value = isoLocal(split.design_start);
  $("design-end").value = isoLocal(split.design_end);
  $("validation-start").value = isoLocal(split.validation_start);
  $("validation-end").value = isoLocal(split.validation_end);
  $("oos-start").value = isoLocal(split.oos_start);
  $("oos-end").value = isoLocal(split.oos_end);
}

function renderPreview(data) {
''',
        r'''function splitPeriods() {
  if (!splitSelection) return null;
  const s = splitSelection;
  return {
    design: { start: s.start, end: s.designEnd, count: s.designEnd - s.start + 1 },
    validation: {
      start: s.designEnd + 1,
      end: s.validationEnd,
      count: s.validationEnd - s.designEnd,
    },
    oos: {
      start: s.validationEnd + 1,
      end: s.end,
      count: s.end - s.validationEnd,
    },
  };
}

function normalizeSplitSelection() {
  if (!datasetPreview || !splitSelection) return;
  const max = datasetPreview.candle_count - 1;
  const s = splitSelection;
  s.start = Math.max(0, Math.min(Number(s.start), max - 2));
  s.designEnd = Math.max(s.start, Math.min(Number(s.designEnd), max - 2));
  s.validationEnd = Math.max(
    s.designEnd + 1,
    Math.min(Number(s.validationEnd), max - 1),
  );
  s.end = Math.max(s.validationEnd + 1, Math.min(Number(s.end), max));
}

function setRangeBounds() {
  if (!datasetPreview || !splitSelection) return;
  const max = datasetPreview.candle_count - 1;
  const s = splitSelection;
  const configure = (id, min, upper, value) => {
    const input = $(id);
    input.min = String(min);
    input.max = String(Math.max(min, upper));
    input.value = String(value);
    input.disabled = false;
  };
  configure("split-start", 0, s.designEnd, s.start);
  configure("split-design-end", s.start, s.validationEnd - 1, s.designEnd);
  configure("split-validation-end", s.designEnd + 1, s.end - 1, s.validationEnd);
  configure("split-end", s.validationEnd + 1, max, s.end);
}

function positionSegment(id, start, end, count) {
  const el = $(id);
  if (end < start) {
    el.style.width = "0%";
    return;
  }
  const left = start / count * 100;
  const right = (end + 1) / count * 100;
  el.style.left = `${left}%`;
  el.style.width = `${Math.max(0, right - left)}%`;
}

function renderSplitSelection() {
  if (!datasetPreview || !splitSelection) return;
  normalizeSplitSelection();
  setRangeBounds();
  const axis = datasetPreview.candle_close_ms || [];
  const periods = splitPeriods();
  const count = datasetPreview.candle_count;
  const s = splitSelection;

  $("dataset-range-label").textContent =
    `${formatCandle(axis[0])} → ${formatCandle(axis[count - 1])} · ${count} bougies`;
  $("split-start-value").textContent = `#${s.start + 1} · ${formatCandle(axis[s.start])}`;
  $("split-design-end-value").textContent =
    `#${s.designEnd + 1} · ${formatCandle(axis[s.designEnd])}`;
  $("split-validation-end-value").textContent =
    `#${s.validationEnd + 1} · ${formatCandle(axis[s.validationEnd])}`;
  $("split-end-value").textContent = `#${s.end + 1} · ${formatCandle(axis[s.end])}`;

  $("design-bars").textContent = `${periods.design.count} bougies`;
  $("validation-bars").textContent = `${periods.validation.count} bougies`;
  $("oos-bars").textContent = `${periods.oos.count} bougies`;
  $("design-dates").textContent =
    `${formatCandle(axis[periods.design.start])} → ${formatCandle(axis[periods.design.end])}`;
  $("validation-dates").textContent =
    `${formatCandle(axis[periods.validation.start])} → ${formatCandle(axis[periods.validation.end])}`;
  $("oos-dates").textContent =
    `${formatCandle(axis[periods.oos.start])} → ${formatCandle(axis[periods.oos.end])}`;

  positionSegment("segment-before", 0, s.start - 1, count);
  positionSegment("segment-design", periods.design.start, periods.design.end, count);
  positionSegment("segment-validation", periods.validation.start, periods.validation.end, count);
  positionSegment("segment-oos", periods.oos.start, periods.oos.end, count);
  positionSegment("segment-after", s.end + 1, count - 1, count);
}

function initializeSplitSelector(preview) {
  const suggested = preview.suggested_split_indices;
  const editor = $("split-editor");
  if (!suggested || !preview.candle_close_ms?.length || preview.candle_count < 3) {
    splitSelection = null;
    suggestedSplitSelection = null;
    editor.classList.add("is-disabled");
    return;
  }
  suggestedSplitSelection = {
    start: suggested.design_start,
    designEnd: suggested.design_end,
    validationEnd: suggested.validation_end,
    end: suggested.oos_end,
  };
  splitSelection = { ...suggestedSplitSelection };
  editor.classList.remove("is-disabled");
  renderSplitSelection();
}

function splitPayload() {
  if (!datasetPreview || !splitSelection) {
    throw new Error("Prévisualise le dataset avant de choisir les périodes.");
  }
  const axis = datasetPreview.candle_close_ms;
  const periods = splitPeriods();
  const at = (index) => new Date(axis[index]).toISOString();
  return {
    design_start: at(periods.design.start),
    design_end: at(periods.design.end),
    validation_start: at(periods.validation.start),
    validation_end: at(periods.validation.end),
    oos_start: at(periods.oos.start),
    oos_end: at(periods.oos.end),
  };
}

function renderPreview(data) {
''',
        label="split selector JS",
    )

    text = replace_once(
        text,
        '''  setSplit(data.suggested_split);
}
''',
        '''  initializeSplitSelector(data);
}
''',
        label="renderPreview split init",
    )

    text = replace_once(
        text,
        '''    split: {
      design_start: utcFromLocal("design-start"),
      design_end: utcFromLocal("design-end"),
      validation_start: utcFromLocal("validation-start"),
      validation_end: utcFromLocal("validation-end"),
      oos_start: utcFromLocal("oos-start"),
      oos_end: utcFromLocal("oos-end"),
    },
''',
        '''    split: splitPayload(),
''',
        label="campaign split payload",
    )

    text = replace_once(
        text,
        '''function renderAgentTraces(traces) {
''',
        r'''const AGENT_ORDER = {
  professor: 0,
  berlin: 10,
  tokyo: 11,
  nairobi: 12,
  rio: 13,
  denver: 14,
  palermo: 20,
  lisbon: 21,
  risk_engine: 30,
};

const ROLE_LABELS = {
  orchestration: "Orchestration",
  red_team: "Red Team",
  ai_economics: "Économie IA",
  trend_regime: "Trend / Regime",
  momentum: "Momentum",
  market_structure: "Structure / Liquidité",
  derivatives_positioning: "Dérivés / Sentiment",
  historical_statistics: "Quant / Statistiques",
  DETERMINISTIC_RISK: "Service déterministe",
};

function renderCrew(descriptors) {
  agentDescriptors = [...(descriptors || [])];
  if (!agentDescriptors.some((item) => item.agent === "risk_engine")) {
    agentDescriptors.push({
      agent: "risk_engine",
      role: "DETERMINISTIC_RISK",
      state: "SYSTEM",
      core: true,
    });
  }
  agentDescriptors.sort(
    (a, b) => (AGENT_ORDER[a.agent] ?? 100) - (AGENT_ORDER[b.agent] ?? 100),
  );
  $("agent-cards").innerHTML = agentDescriptors.map((item) => {
    const service = item.agent === "risk_engine" ? " service" : "";
    return `<article id="agent-card-${esc(item.agent)}" class="agent-card${service}" data-agent="${esc(item.agent)}">`
      + `<div class="agent-card-head"><span class="agent-name">${esc(item.agent)}</span>`
      + `<span class="agent-registry-state">${esc(item.state)}</span></div>`
      + `<div class="agent-role">${esc(ROLE_LABELS[item.role] || item.role)}</div>`
      + `<div class="agent-runtime-state">IDLE</div>`
      + `<div class="agent-last-message">Aucun événement dans cette campagne.</div>`
      + `</article>`;
  }).join("");
}

function setActiveAgents(activeAgents) {
  const active = new Set(activeAgents || []);
  for (const item of agentDescriptors) {
    const card = $(`agent-card-${item.agent}`);
    if (!card) continue;
    const isActive = active.has(item.agent);
    card.classList.toggle("is-active", isActive);
    const state = card.querySelector(".agent-runtime-state");
    if (isActive) state.textContent = "WORKING";
    else if (state.textContent === "WORKING") state.textContent = "IDLE";
  }
}

function updateAgentCard(trace) {
  const card = $(`agent-card-${trace.agent}`);
  if (!card) return;
  card.querySelector(".agent-last-message").textContent = trace.title || trace.phase;
  const state = card.querySelector(".agent-runtime-state");
  if (!card.classList.contains("is-active")) {
    state.textContent = trace.phase === "FAILED" ? "FAILED" : "DONE";
  }
}

function animateCommunication(sourceAgent, targetAgent) {
  const stage = $("crew-stage");
  const svg = $("crew-links");
  const source = $(`agent-card-${sourceAgent}`);
  const target = $(`agent-card-${targetAgent}`);
  if (!stage || !svg || !source || !target) return;

  const stageRect = stage.getBoundingClientRect();
  const a = source.getBoundingClientRect();
  const b = target.getBoundingClientRect();
  const x1 = a.left + a.width / 2 - stageRect.left;
  const y1 = a.top + a.height / 2 - stageRect.top;
  const x2 = b.left + b.width / 2 - stageRect.left;
  const y2 = b.top + b.height / 2 - stageRect.top;
  const bend = Math.max(18, Math.abs(y2 - y1) * 0.32);
  const midY = (y1 + y2) / 2;

  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", `M ${x1} ${y1} C ${x1} ${midY - bend}, ${x2} ${midY + bend}, ${x2} ${y2}`);
  path.setAttribute("class", "communication-path");
  path.setAttribute("marker-end", "url(#flow-arrow)");
  svg.appendChild(path);
  setTimeout(() => path.remove(), 950);
}

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function playTraceAnimation(trace) {
  updateAgentCard(trace);
  const card = $(`agent-card-${trace.agent}`);
  if (card) card.classList.add("is-recent");
  for (const target of trace.targets || []) {
    animateCommunication(trace.agent, target);
  }
  await delay(360);
  if (card) card.classList.remove("is-recent");
}

function enqueueTraceAnimations(traces) {
  const fresh = [...(traces || [])]
    .filter((trace) => Number(trace.sequence) > lastTraceSequence)
    .sort((a, b) => Number(a.sequence) - Number(b.sequence));
  for (const trace of fresh) {
    traceAnimationChain = traceAnimationChain.then(() => playTraceAnimation(trace));
  }
  if (fresh.length) lastTraceSequence = Number(fresh.at(-1).sequence);
}

function renderAgentTraces(traces) {
''',
        label="crew visualization JS",
    )

    text = replace_once(
        text,
        '''  renderAgentTraces(data.agent_traces || []);
}
''',
        '''  setActiveAgents(data.active_agents || []);
  enqueueTraceAnimations(data.agent_traces || []);
  renderAgentTraces(data.agent_traces || []);
}
''',
        label="renderProgress crew",
    )

    text = replace_once(
        text,
        '''  renderAgentTraces([]);
''',
        '''  lastTraceSequence = 0;
  traceAnimationChain = Promise.resolve();
  renderAgentTraces([]);
  setActiveAgents([]);
  for (const item of agentDescriptors) {
    const card = $(`agent-card-${item.agent}`);
    if (!card) continue;
    card.classList.remove("is-active", "is-recent");
    card.querySelector(".agent-runtime-state").textContent = "IDLE";
    card.querySelector(".agent-last-message").textContent =
      "Aucun événement dans cette campagne.";
  }
''',
        label="campaign crew reset",
    )

    text = replace_once(
        text,
        '''  $("cache-count").textContent = `${data.cache_entries} entrée(s) cache`;
}
''',
        '''  $("cache-count").textContent = `${data.cache_entries} entrée(s) cache`;
  renderCrew(data.agents || []);
}
''',
        label="capabilities crew",
    )

    text = replace_once(
        text,
        '''$("stop-button").addEventListener("click", () => stopCampaign().catch(showError));
''',
        r'''function onSplitInput(id, key) {
  $(id).addEventListener("input", () => {
    if (!splitSelection) return;
    splitSelection[key] = Number($(id).value);
    renderSplitSelection();
  });
}

onSplitInput("split-start", "start");
onSplitInput("split-design-end", "designEnd");
onSplitInput("split-validation-end", "validationEnd");
onSplitInput("split-end", "end");

$("split-full").addEventListener("click", () => {
  if (!datasetPreview || !splitSelection) return;
  splitSelection.start = 0;
  splitSelection.end = datasetPreview.candle_count - 1;
  renderSplitSelection();
});

$("split-reset").addEventListener("click", () => {
  if (!suggestedSplitSelection) return;
  splitSelection = { ...suggestedSplitSelection };
  renderSplitSelection();
});

$("stop-button").addEventListener("click", () => stopCampaign().catch(showError));
''',
        label="split event listeners",
    )

    text = replace_once(
        text,
        '''$("csv-file").addEventListener("change", () => { csvText = ""; datasetPreview = null; });
''',
        '''$("csv-file").addEventListener("change", () => {
  csvText = "";
  datasetPreview = null;
  splitSelection = null;
  suggestedSplitSelection = null;
  $("split-editor").classList.add("is-disabled");
  for (const id of ["split-start", "split-design-end", "split-validation-end", "split-end"]) {
    $(id).disabled = true;
  }
});
''',
        label="CSV split reset",
    )

    path.write_text(text, encoding="utf-8")
    print(f"- patched {path}")


def patch_css(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "Batch 16.9 — dataset-driven split timeline" in text:
        print(f"- {path}: already patched")
        return

    css = r'''

/* Batch 16.9 — dataset-driven split timeline & crew graph */
.split-editor {
  margin-top: 14px; padding: 14px; border: 1px solid var(--border);
  border-radius: 14px; background: #101013;
}
.split-editor.is-disabled { opacity: .55; pointer-events: none; }
.split-toolbar { display: flex; align-items: flex-end; justify-content: space-between; gap: 14px; }
.split-toolbar > div:first-child { display: grid; gap: 4px; }
.split-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.split-timeline {
  position: relative; height: 42px; margin-top: 16px; overflow: hidden;
  border: 1px solid var(--border); border-radius: 12px; background: #09090b;
}
.split-segment {
  position: absolute; top: 0; bottom: 0; display: grid; place-items: center;
  min-width: 0; overflow: hidden; border-right: 1px solid rgba(255,255,255,.08);
  transition: left .08s linear, width .08s linear;
}
.split-segment span {
  padding: 4px 7px; font-size: .65rem; font-weight: 900;
  letter-spacing: .08em; white-space: nowrap;
}
.split-segment.unused { background: repeating-linear-gradient(135deg, #121216 0 8px, #17171c 8px 16px); }
.split-segment.design { background: rgba(228,59,59,.46); }
.split-segment.validation { background: rgba(225,184,90,.43); }
.split-segment.oos { background: rgba(102,201,154,.40); }
.split-control-grid {
  display: grid; grid-template-columns: repeat(2, minmax(0,1fr));
  gap: 12px 16px; margin-top: 16px;
}
.split-control-grid input[type="range"] { width: 100%; padding: 0; accent-color: var(--paper); }
.range-value {
  min-height: 1.2rem; color: var(--text);
  font: .68rem/1.35 ui-monospace, SFMono-Regular, Consolas, monospace;
}
.split-summary {
  display: grid; grid-template-columns: repeat(3, minmax(0,1fr));
  gap: 10px; margin-top: 14px;
}
.split-card {
  min-width: 0; padding: 12px; border: 1px solid var(--border);
  border-radius: 11px; background: #0d0d10;
}
.split-card span { display: block; font-size: .66rem; font-weight: 900; letter-spacing: .1em; }
.split-card strong { display: block; margin: 5px 0; font-size: 1.05rem; }
.split-card div { color: var(--muted); font-size: .7rem; line-height: 1.4; }
.split-card.design { border-color: rgba(228,59,59,.45); }
.split-card.validation { border-color: rgba(225,184,90,.45); }
.split-card.oos { border-color: rgba(102,201,154,.45); }

.crew-legend {
  display: flex; flex-wrap: wrap; gap: 12px; margin: 13px 0 6px;
  color: var(--muted); font-size: .7rem;
}
.crew-legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--border); }
.legend-dot.live { background: var(--paper); box-shadow: 0 0 12px rgba(225,184,90,.8); }
.legend-dot.recent { background: var(--accent); }
.legend-dot.idle { background: #686872; }
.crew-stage {
  position: relative; min-height: 230px; margin-top: 10px; padding: 10px; overflow: hidden;
  border: 1px solid var(--border); border-radius: 14px;
  background: radial-gradient(circle at 50% 0%, rgba(228,59,59,.08), transparent 42%), #0e0e11;
}
.crew-links {
  position: absolute; inset: 0; z-index: 1; width: 100%; height: 100%;
  pointer-events: none; overflow: visible;
}
#flow-arrow path { fill: var(--paper); }
.agent-card-grid {
  position: relative; z-index: 2; display: grid;
  grid-template-columns: repeat(5, minmax(135px,1fr)); gap: 10px;
}
.agent-card {
  min-height: 118px; padding: 11px; border: 1px solid var(--border);
  border-radius: 12px; background: rgba(16,16,19,.96);
  transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
}
.agent-card.service { border-style: double; border-color: rgba(102,201,154,.42); }
.agent-card-head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.agent-name { font-size: .8rem; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }
.agent-registry-state {
  padding: 3px 6px; border: 1px solid var(--border); border-radius: 999px;
  color: var(--muted); font-size: .58rem; font-weight: 800;
}
.agent-role { margin-top: 5px; color: var(--muted); font-size: .66rem; }
.agent-runtime-state {
  margin-top: 11px; color: var(--paper); font-size: .64rem;
  font-weight: 900; letter-spacing: .08em;
}
.agent-last-message { margin-top: 5px; color: var(--text); font-size: .68rem; line-height: 1.35; }
.agent-card.is-active {
  border-color: var(--paper);
  box-shadow: 0 0 0 1px rgba(225,184,90,.26), 0 0 28px rgba(225,184,90,.17);
  animation: agent-pulse 1.05s ease-in-out infinite;
}
.agent-card.is-recent {
  border-color: var(--accent); box-shadow: 0 0 24px rgba(228,59,59,.17);
  transform: translateY(-2px);
}
.communication-path {
  fill: none; stroke: var(--paper); stroke-width: 2; stroke-linecap: round;
  stroke-dasharray: 8 10; filter: drop-shadow(0 0 4px rgba(225,184,90,.65));
  animation: communication-flow .9s linear forwards;
}
.trace-journal { margin-top: 14px; border-top: 1px solid var(--border); padding-top: 12px; }
.trace-journal > summary { cursor: pointer; color: var(--paper); font-size: .75rem; font-weight: 800; }

@keyframes agent-pulse {
  50% {
    transform: translateY(-2px);
    box-shadow: 0 0 0 3px rgba(225,184,90,.08), 0 0 36px rgba(225,184,90,.26);
  }
}
@keyframes communication-flow {
  from { stroke-dashoffset: 42; opacity: .15; }
  20% { opacity: 1; }
  to { stroke-dashoffset: 0; opacity: 0; }
}
@media (max-width: 1180px) {
  .agent-card-grid { grid-template-columns: repeat(3, minmax(135px,1fr)); }
}
@media (max-width: 760px) {
  .split-toolbar { align-items: stretch; flex-direction: column; }
  .split-control-grid, .split-summary { grid-template-columns: 1fr; }
  .agent-card-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
}
@media (max-width: 480px) { .agent-card-grid { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) {
  .agent-card, .communication-path, .split-segment {
    animation: none !important; transition: none !important;
  }
}
'''
    path.write_text(text.rstrip() + css + "\n", encoding="utf-8")
    print(f"- patched {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Batch 16.9 Backtest Dashboard UX")
    parser.add_argument("--root", default=".", help="Money-Heist repository root")
    parser.add_argument(
        "--allow-other-head",
        action="store_true",
        help="Allow another HEAD if all source anchors remain compatible",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    required = [
        root / "app/dashboard/backtest.py",
        root / "app/dashboard/static/backtest.html",
        root / "app/dashboard/static/backtest.js",
        root / "app/dashboard/static/backtest.css",
        root / "tests/dashboard/test_backtest_ux.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Money-Heist root / extracted batch incomplete; missing:\n- " + "\n- ".join(missing))

    head = git_head(root)
    if head and head != BASE_COMMIT and not args.allow_other_head:
        raise SystemExit(
            f"Refusing to patch HEAD {head}. Expected {BASE_COMMIT}.\n"
            "Use --allow-other-head only if later commits are intentionally present."
        )

    patch_backend(root / "app/dashboard/backtest.py")
    patch_html(root / "app/dashboard/static/backtest.html")
    patch_js(root / "app/dashboard/static/backtest.js")
    patch_css(root / "app/dashboard/static/backtest.css")

    print("\nBatch 16.9 applied.")
    print("Validate with:")
    print("  uv run pytest -q tests/dashboard/test_backtest_ux.py")
    print("  uv run pytest -q tests/dashboard")
    print("  uv run pytest -q")
    print("\nNo LIVE execution component was modified.")


if __name__ == "__main__":
    main()
