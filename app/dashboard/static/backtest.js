const $ = (id) => document.getElementById(id);
const endpoint = "/api/dashboard/backtest";
let csvText = "";
let datasetPreview = null;

const esc = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function isoLocal(value) {
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

function setSplit(split) {
  if (!split) return;
  $("design-start").value = isoLocal(split.design_start);
  $("design-end").value = isoLocal(split.design_end);
  $("validation-start").value = isoLocal(split.validation_start);
  $("validation-end").value = isoLocal(split.validation_end);
  $("oos-start").value = isoLocal(split.oos_start);
  $("oos-end").value = isoLocal(split.oos_end);
}

function renderPreview(data) {
  datasetPreview = data;
  const box = $("dataset-preview");
  box.className = `preview ${data.is_valid ? "good" : "bad"}`;
  box.innerHTML = `<strong>${esc(data.dataset_id)}</strong><br>`
    + `${esc(data.candle_count)} bougies · ${esc(data.start_at)} → ${esc(data.end_at)}<br>`
    + `SHA-256 ${esc(data.content_sha256)}<br>`
    + `Qualité: ${data.is_valid ? "VALID" : "INVALID"} · gaps=${esc(data.gap_count)}`;
  setSplit(data.suggested_split);
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
    split: {
      design_start: utcFromLocal("design-start"),
      design_end: utcFromLocal("design-end"),
      validation_start: utcFromLocal("validation-start"),
      validation_end: utcFromLocal("validation-end"),
      oos_start: utcFromLocal("oos-start"),
      oos_end: utcFromLocal("oos-end"),
    },
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
  $("run-button").disabled = true;
  $("run-status").textContent = "RUNNING";
  try {
    if (!csvText) await readCsv();
    const response = await api(`${endpoint}/runs`, {
      method: "POST",
      body: JSON.stringify(campaignPayload()),
    });
    renderResults(await response.json());
    await refreshCapabilities();
    await refreshHistory();
  } catch (error) {
    $("run-status").textContent = "FAILED";
    showError(error);
  } finally {
    $("run-button").disabled = false;
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

$("preview-button").addEventListener("click", preview);
$("campaign-form").addEventListener("submit", runCampaign);
$("refresh-history").addEventListener("click", () => refreshHistory().catch(showError));
$("cache-export").addEventListener("click", () => exportCache().catch(showError));
$("cache-import").addEventListener("change", (event) =>
  importCache(event.target.files[0]).catch(showError));
$("csv-file").addEventListener("change", () => { csvText = ""; datasetPreview = null; });
$("ai-mode").addEventListener("change", () => {
  if ($("ai-mode").value === "MOCK" && !$("model-id").value.trim()) {
    $("model-id").value = "mock-backtest-v1";
  }
});

Promise.all([refreshCapabilities(), refreshHistory()]).catch(showError);
