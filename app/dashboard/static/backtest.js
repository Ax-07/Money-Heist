const $ = (id) => document.getElementById(id);
const endpoint = "/api/dashboard/backtest";
let csvText = "";
let datasetPreview = null;
let activeCampaignId = null;
let pollTimer = null;
let splitSelection = null;
let suggestedSplitSelection = null;
let agentDescriptors = [];
let lastTraceSequence = 0;
let traceAnimationChain = Promise.resolve();
let mockAgentCoverage = false;

const esc = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function formatCandle(ms) {
  if (ms === undefined || ms === null) return "—";
  return new Date(ms).toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "medium",
  });
}

function numberOrNull(id) {
  const raw = $(id).value.trim();
  return raw === "" ? null : raw;
}

async function readCsv() {
  const file = $("csv-file").files[0];
  if (!file) throw new Error("Sélectionne un fichier CSV OHLCV.");
  csvText = await file.text();
  if (!csvText.trim()) throw new Error("Le CSV est vide.");
  return csvText;
}

function datasetPayload() {
  return {
    csv_text: csvText,
    symbol: $("symbol").value.trim(),
    timeframe: $("timeframe").value,
    source: $("source").value.trim(),
    candle_interval_seconds: numberOrNull("interval-seconds"),
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    cache: "no-store",
    ...options,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) { /* keep HTTP status */ }
    throw new Error(detail);
  }
  return response;
}

function splitPeriods() {
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
  datasetPreview = data;
  const box = $("dataset-preview");
  box.className = `preview ${data.is_valid ? "good" : "bad"}`;
  box.innerHTML = `<strong>${esc(data.dataset_id)}</strong><br>`
    + `${esc(data.candle_count)} bougies · ${esc(data.start_at)} → ${esc(data.end_at)}<br>`
    + `SHA-256 ${esc(data.content_sha256)}<br>`
    + `Qualité: ${data.is_valid ? "VALID" : "INVALID"} · gaps=${esc(data.gap_count)}`;
  initializeSplitSelector(data);
}

async function preview() {
  clearError();
  try {
    await readCsv();
    const response = await api(`${endpoint}/dataset/preview`, {
      method: "POST",
      body: JSON.stringify(datasetPayload()),
    });
    renderPreview(await response.json());
  } catch (error) {
    showError(error);
  }
}

function campaignPayload() {
  if (!datasetPreview) throw new Error("Prévisualise et valide d'abord le dataset.");
  if (!datasetPreview.is_valid) throw new Error("Le dataset n'est pas valide.");
  return {
    dataset: datasetPayload(),
    split: splitPayload(),
    risk: {
      risk_profile_id: "dashboard_balanced_dev",
      risk_version: "dashboard-balanced-dev-v1",
      max_risk_per_trade_pct: $("risk-trade").value,
      max_daily_loss_pct: $("daily-loss").value,
      max_drawdown_pct: $("risk-drawdown").value,
      max_portfolio_risk_pct: $("portfolio-risk").value,
      max_positions: Number($("max-positions").value),
      max_leverage: $("risk-leverage").value,
      max_correlated_exposure_pct: $("correlated-risk").value,
      min_expected_rr: numberOrNull("min-rr"),
    },
    market: {
      qty_step: $("qty-step").value,
      min_qty: $("min-qty").value,
      min_notional: $("min-notional").value,
      max_qty: numberOrNull("max-qty"),
      max_leverage: numberOrNull("market-leverage"),
    },
    ai: {
      mode: $("ai-mode").value,
      hard_budget_eur: $("ai-budget").value,
      model_id: $("model-id").value.trim(),
      input_per_million_eur: $("input-price").value,
      output_per_million_eur: $("output-price").value,
      cached_input_per_million_eur: numberOrNull("cached-price"),
      mock_agent_coverage: mockAgentCoverage && $("ai-mode").value === "MOCK",
    },
    execution: {
      initial_balance: $("initial-balance").value,
      maker_fee_bps: $("maker-fee").value,
      taker_fee_bps: $("taker-fee").value,
      market_slippage_bps: $("slippage").value,
      code_version: $("code-version").value.trim(),
      execution_model_version: $("execution-version").value.trim(),
      random_seed: Number($("random-seed").value),
    },
    walk_forward: {
      enabled: $("wf-enabled").checked,
      design_bars: Number($("wf-design").value),
      validation_bars: Number($("wf-validation").value),
      oos_bars: Number($("wf-oos").value),
      step_bars: Number($("wf-step").value),
    },
    system_id: "balanced_v1",
  };
}

function metric(metric) {
  if (!metric || metric.value === null) return `${esc(metric?.status || "UNAVAILABLE")}`;
  return esc(metric.value);
}

function periodCard(period) {
  return `<div class="period"><h3>${esc(period.role)}</h3>`
    + `<div class="run-id">${esc(period.run_id)}</div>`
    + `<div class="metric-grid">`
    + `<div class="metric"><span>Trading Net</span><strong>${metric(period.trading_net)}</strong></div>`
    + `<div class="metric"><span>Economic Net</span><strong>${metric(period.economic_net)}</strong></div>`
    + `<div class="metric"><span>Max DD %</span><strong>${metric(period.max_drawdown_pct)}</strong></div>`
    + `<div class="metric"><span>Profit Factor</span><strong>${metric(period.profit_factor)}</strong></div>`
    + `<div class="metric"><span>Expectancy</span><strong>${metric(period.expectancy)}</strong></div>`
    + `<div class="metric"><span>Win rate</span><strong>${metric(period.win_rate)}</strong></div>`
    + `<div class="metric"><span>Trades fermés</span><strong>${esc(period.closed_trades)}</strong></div>`
    + `<div class="metric"><span>Coût IA €</span><strong>${esc(period.ai_cost_eur)}</strong></div>`
    + `</div></div>`;
}

function equityChart(points) {
  if (!points?.length) return "";
  const width = 640;
  const height = 180;
  const values = points.map((p) => Number(p.equity));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 0.0000001);
  const coords = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : index * width / (values.length - 1);
    const y = height - 12 - ((value - min) / span) * (height - 24);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `<svg class="chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">`
    + `<polyline points="${coords}" fill="none" stroke="currentColor" stroke-width="2" />`
    + `</svg><div class="muted">Equity OOS: ${esc(min)} → ${esc(max)}</div>`;
}


const AGENT_ORDER = {
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
  const el = $("agent-traces");
  if (!traces?.length) {
    el.className = "agent-traces empty";
    el.textContent = "Aucune trace agent pour le moment.";
    return;
  }
  el.className = "agent-traces";
  el.innerHTML = [...traces].reverse().map((trace) => {
    const when = trace.observed_at
      ? new Date(trace.observed_at).toLocaleString("fr-FR")
      : "—";
    const details = esc(JSON.stringify(trace.details ?? {}, null, 2));
    return `<article class="agent-trace">`
      + `<div class="agent-trace-head"><span>${esc(trace.role)} · ${esc(trace.agent)} · ${esc(trace.phase)}</span>`
      + `<span>${esc(when)}</span></div>`
      + `<strong>${esc(trace.title)}</strong>`
      + `<details><summary>Voir la sortie structurée</summary><pre>${details}</pre></details>`
      + `</article>`;
  }).join("");
}

function renderProgress(data) {
  const panel = $("progress-panel");
  panel.classList.remove("hidden");
  $("campaign-progress").value = Number(data.percent ?? 0);
  $("progress-label").textContent = `${Number(data.percent ?? 0).toFixed(1)} %`;
  $("run-status").textContent = data.status;
  $("stop-button").disabled = !data.can_cancel;

  const role = data.current_role ? ` · ${data.current_role}` : "";
  const at = data.current_observed_at
    ? ` · ${new Date(data.current_observed_at).toLocaleString("fr-FR")}`
    : "";
  $("progress-detail").textContent =
    `${data.phase}${role}${at} · travail ${data.work_done}/${data.total_work}`
    + ` · opportunités ${data.opportunity_count} · ordres ${data.executed_order_count}`
    + (data.message ? ` · ${data.message}` : "");

  setActiveAgents(data.active_agents || []);
  enqueueTraceAnimations(data.agent_traces || []);
  renderAgentTraces(data.agent_traces || []);
}

function stopPolling() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function finishCampaignUi() {
  activeCampaignId = null;
  $("run-button").disabled = false;
  $("stop-button").disabled = true;
}

async function pollCampaign(campaignId) {
  const response = await api(
    `${endpoint}/runs/${encodeURIComponent(campaignId)}/progress`
  );
  const data = await response.json();
  renderProgress(data);

  if (data.status === "COMPLETED") {
    stopPolling();
    const resultResponse = await api(
      `${endpoint}/runs/${encodeURIComponent(campaignId)}`
    );
    renderResults(await resultResponse.json());
    finishCampaignUi();
    await refreshCapabilities();
    await refreshHistory();
    return;
  }

  if (data.status === "CANCELLED") {
    stopPolling();
    finishCampaignUi();
    $("results").className = "empty";
    $("results").textContent = "Campagne annulée. Aucun résultat final n'a été publié.";
    return;
  }

  if (data.status === "FAILED") {
    stopPolling();
    finishCampaignUi();
    showError(new Error(data.error || "La campagne a échoué."));
    return;
  }

  pollTimer = setTimeout(
    () => pollCampaign(campaignId).catch((error) => {
      stopPolling();
      finishCampaignUi();
      showError(error);
    }),
    600,
  );
}

async function stopCampaign() {
  if (!activeCampaignId) return;
  $("stop-button").disabled = true;
  const response = await api(
    `${endpoint}/runs/${encodeURIComponent(activeCampaignId)}/cancel`,
    { method: "POST" },
  );
  renderProgress(await response.json());
}

function renderResults(data) {
  $("run-status").textContent = data.status;
  const exports = data.exports.map((name) =>
    `<a href="${endpoint}/runs/${encodeURIComponent(data.campaign_id)}/exports/${encodeURIComponent(name)}">${esc(name)}</a>`
  ).join("");
  const wf = data.walk_forward_oos?.length
    ? `<div class="period"><h3>Walk-forward OOS</h3>${data.walk_forward_oos.map((item) =>
        `<div class="metric"><span>Fenêtre ${esc(item.window_index)} · ${esc(item.closed_trades)} trades</span>`
        + `<strong>Net ${esc(item.trading_net ?? "—")} · DD ${esc(item.max_drawdown_pct ?? "—")}</strong></div>`
      ).join("")}</div>` : "";
  $("results").className = "";
  $("results").innerHTML = `<div class="preview good"><strong>${esc(data.dataset.dataset_id)}</strong><br>`
    + `Mode IA ${esc(data.ai_mode)} · campagne ${esc(data.campaign_id)}</div>`
    + periodCard(data.design) + periodCard(data.validation) + periodCard(data.oos)
    + equityChart(data.oos_equity) + wf
    + `<div class="period"><h3>Exports</h3><div class="exports">${exports}</div></div>`;
}

async function runCampaign(event) {
  event.preventDefault();
  clearError();
  stopPolling();
  $("run-button").disabled = true;
  $("run-status").textContent = "QUEUED";
  $("results").className = "empty";
  $("results").textContent = "Campagne en cours…";
  lastTraceSequence = 0;
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

  try {
    if (!csvText) await readCsv();
    const response = await api(`${endpoint}/runs`, {
      method: "POST",
      body: JSON.stringify(campaignPayload()),
    });
    const progress = await response.json();
    activeCampaignId = progress.campaign_id;
    renderProgress(progress);
    await pollCampaign(activeCampaignId);
  } catch (error) {
    finishCampaignUi();
    $("run-status").textContent = "FAILED";
    showError(error);
  }
}

function showError(error) {
  const box = $("error-box");
  box.classList.remove("hidden");
  box.textContent = error.message || String(error);
}
function clearError() {
  $("error-box").classList.add("hidden");
  $("error-box").textContent = "";
}

async function refreshCapabilities() {
  const response = await api(`${endpoint}/capabilities`);
  const data = await response.json();
  $("live-eval-state").textContent = data.live_eval_available
    ? "LIVE_EVAL backend prêt" : "LIVE_EVAL sans clé backend";
  $("cache-count").textContent = `${data.cache_entries} entrée(s) cache`;
  renderCrew(data.agents || []);
}

async function refreshHistory() {
  const response = await api(`${endpoint}/runs`);
  const rows = await response.json();
  const el = $("history");
  if (!rows.length) {
    el.className = "empty";
    el.textContent = "Aucune campagne dans cette session.";
    return;
  }
  el.className = "";
  el.innerHTML = rows.map((row) => `<div class="history-item">`
    + `<span>${esc(new Date(row.created_at).toLocaleString("fr-FR"))}</span>`
    + `<code>${esc(row.campaign_id)}</code><span>${esc(row.ai_mode)}</span>`
    + `<span>OOS net ${esc(row.oos.trading_net.value ?? "—")}</span></div>`).join("");
}

async function exportCache() {
  const response = await fetch(`${endpoint}/ai-cache`, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "backtest-ai-cache.json";
  link.click();
  URL.revokeObjectURL(url);
}

async function importCache(file) {
  if (!file) return;
  const payload = await file.text();
  await api(`${endpoint}/ai-cache`, {
    method: "POST",
    body: JSON.stringify({ payload }),
  });
  await refreshCapabilities();
}

function onSplitInput(id, key) {
  $(id).addEventListener("input", () => {
    if (!splitSelection) return;
    mockAgentCoverage = false;
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
  mockAgentCoverage = false;
  splitSelection.start = 0;
  splitSelection.end = datasetPreview.candle_count - 1;
  renderSplitSelection();
});

$("split-reset").addEventListener("click", () => {
  if (!suggestedSplitSelection) return;
  mockAgentCoverage = false;
  splitSelection = { ...suggestedSplitSelection };
  renderSplitSelection();
});

$("stop-button").addEventListener("click", () => stopCampaign().catch(showError));
$("preview-button").addEventListener("click", preview);
$("campaign-form").addEventListener("submit", runCampaign);
$("refresh-history").addEventListener("click", () => refreshHistory().catch(showError));
$("cache-export").addEventListener("click", () => exportCache().catch(showError));
$("cache-import").addEventListener("change", (event) =>
  importCache(event.target.files[0]).catch(showError));
// Batch 16.10 — Dataset-aware defaults
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


// Batch 16.10 — Quick test preset
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
  mockAgentCoverage = true;
  renderSplitSelection();
}

$("symbol").addEventListener("change", () => {
  applyMarketPreset($("symbol").value.trim());
});

$("split-quick-test").addEventListener("click", () => {
  try {
    applyQuickTestSplit();
  } catch (error) {
    showError(error);
  }
});

$("csv-file").addEventListener("change", () => {
  csvText = "";
  datasetPreview = null;
  splitSelection = null;
  suggestedSplitSelection = null;
  mockAgentCoverage = false;
  $("split-editor").classList.add("is-disabled");
  for (const id of ["split-start", "split-design-end", "split-validation-end", "split-end"]) {
    $(id).disabled = true;
  }
  applyDatasetDefaultsFromFile($("csv-file").files?.[0]);
});
$("ai-mode").addEventListener("change", () => {
  if ($("ai-mode").value !== "MOCK") mockAgentCoverage = false;
  if ($("ai-mode").value === "MOCK" && !$("model-id").value.trim()) {
    $("model-id").value = "mock-backtest-v1";
  }
});

Promise.all([refreshCapabilities(), refreshHistory()]).catch(showError);
