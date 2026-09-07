const endpoint = "/api/dashboard/overview";

const esc = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function metricValue(metric) {
  if (!metric || metric.availability === "UNAVAILABLE") return '<span class="unavailable">Indisponible</span>';
  if (metric.availability === "UNBOUNDED") return '<span class="partial">Non borné</span>';
  if (metric.value === null || metric.value === undefined) return '<span class="unavailable">Indisponible</span>';
  const unit = metric.unit === "EUR" ? " €" : metric.unit === "x" ? "×" : "";
  return `${esc(metric.value)}${unit}`;
}

function accountValue(account, key, suffix = "") {
  if (!account || account.availability === "UNAVAILABLE" || account[key] === null || account[key] === undefined) return '<span class="unavailable">Indisponible</span>';
  return `${esc(account[key])}${suffix}`;
}

function detailRows(items, formatter, emptyText) {
  if (!items?.length) return `<div class="tiny muted">${esc(emptyText)}</div>`;
  return `<div class="detail-list">${items.slice(-8).reverse().map(formatter).join("")}</div>`;
}

function systemCard(system) {
  const metrics = system.batch10?.metrics || {};
  const positionText = system.positions_availability === "AVAILABLE" ? `${system.positions.length} ouverte(s)` : "Indisponible";
  const orderText = system.orders_availability === "AVAILABLE" ? `${system.orders.length} ordre(s) / ${system.fills.length} fill(s)` : "Indisponible";
  const aiText = system.ai_usage?.availability === "UNAVAILABLE"
    ? '<span class="unavailable">Indisponible</span>'
    : `${esc(system.ai_usage.total_cost_eur ?? 0)} € · ${esc(system.ai_usage.record_count)} appel(s)`;
  const metricRows = Object.values(metrics).map(m => `<div class="detail-row"><span>${esc(m.name)}</span><span class="mono">${metricValue(m)}</span></div>`).join("");
  const counterfactualRows = detailRows(system.batch10?.counterfactuals || [], c => `<div class="detail-row"><span>CONTREFACTUEL · ${esc(c.label)}</span><span class="mono">${c.hypothetical_pnl === null ? "Indisponible" : esc(c.hypothetical_pnl)}</span></div>`, "Aucun résultat contrefactuel exposé.");
  return `<article class="system-card">
    <header>
      <div><p class="label">${esc(system.family)}</p><h3>${esc(system.display_name)}${system.aliases.length ? ` / ${esc(system.aliases.join(" / "))}` : ""}</h3><div class="system-id">${esc(system.system_id)}</div></div>
      <div><span class="badge badge-shadow">${esc(system.mode)}</span></div>
    </header>
    <div class="body">
      <div class="metric-grid">
        <div class="metric"><span class="name">Capital initial PAPER</span><span class="value">${accountValue(system.account, "initial_balance")}</span></div>
        <div class="metric"><span class="name">Cash PAPER</span><span class="value">${accountValue(system.account, "cash_balance")}</span></div>
        <div class="metric"><span class="name">Equity PAPER</span><span class="value">${accountValue(system.account, "equity")}</span></div>
        <div class="metric"><span class="name">Trading Net</span><span class="value">${metricValue(metrics.trading_net)}</span></div>
        <div class="metric"><span class="name">Economic Net</span><span class="value">${metricValue(metrics.economic_net)}</span></div>
        <div class="metric"><span class="name">SelfFundingRatio</span><span class="value">${metricValue(metrics.self_funding_ratio)}</span></div>
        <div class="metric"><span class="name">Coût IA observé</span><span class="value">${aiText}</span></div>
        <div class="metric"><span class="name">Drawdown</span><span class="value">${metricValue(metrics.max_drawdown_abs)}</span></div>
      </div>
      <div class="subline"><span>Statut pipeline</span><strong>${esc(system.latest_decision?.pipeline_status || "Aucune décision")}</strong></div>
      <div class="subline"><span>Positions</span><strong>${esc(positionText)}</strong></div>
      <div class="subline"><span>Ordres / fills</span><strong>${esc(orderText)}</strong></div>
      <div class="subline"><span>Évaluation Batch 10</span><strong>${esc(system.batch10.status)}</strong></div>
      <div class="subline"><span>Provenance</span><strong>SHADOW · PAPER</strong></div>
      <div class="detail-stack">
        <details class="read-detail"><summary>Positions ouvertes</summary>${detailRows(system.positions, p => `<div class="detail-row"><span>${esc(p.symbol)} · ${esc(p.side || "—")}</span><span class="mono">${esc(p.quantity)} @ ${esc(p.average_entry)}</span></div>`, system.positions_availability === "UNAVAILABLE" ? "Indisponible" : "Aucune position ouverte.")}</details>
        <details class="read-detail"><summary>Ordres PAPER</summary>${detailRows(system.orders, o => `<div class="detail-row"><span>${esc(o.status)} · ${esc(o.side)} ${esc(o.symbol)}</span><span class="mono">${esc(o.filled_quantity)}/${esc(o.requested_quantity)}</span></div>`, system.orders_availability === "UNAVAILABLE" ? "Indisponible" : "Aucun ordre.")}</details>
        <details class="read-detail"><summary>Fills PAPER</summary>${detailRows(system.fills, f => `<div class="detail-row"><span>${esc(f.fill_id)} · ${esc(f.liquidity)}</span><span class="mono">${esc(f.quantity)} @ ${esc(f.price)} · fee ${esc(f.fee)}</span></div>`, system.fills_availability === "UNAVAILABLE" ? "Indisponible" : "Aucun fill.")}</details>
        <details class="read-detail"><summary>Métriques Batch 10</summary><div class="detail-list">${metricRows || '<div class="tiny muted">Indisponible</div>'}</div></details>
        <details class="read-detail"><summary>Contrefactuels (simulation uniquement)</summary>${counterfactualRows}</details>
      </div>
    </div>
  </article>`;
}

function renderOpportunities(opportunities) {
  const el = document.getElementById("opportunities");
  if (!opportunities?.length) { el.innerHTML = '<p class="empty">Aucune opportunité SHADOW observée.</p>'; return; }
  el.innerHTML = opportunities.slice(-30).reverse().map(o => `<div class="opportunity">
    <div><strong>${esc(o.symbol)} · ${esc(o.timeframe)}</strong><div class="tiny muted">${esc(o.system_id)}</div></div>
    <div><strong>Priorité ${o.priority_score === null ? "—" : esc(o.priority_score)}</strong><div class="tiny muted">scanner, aucune direction</div></div>
    <div><strong>SHADOW / PAPER</strong><div class="tiny muted">${esc(o.opportunity_id)}</div></div>
    <div><strong>${esc((o.triggers || []).join(", ") || "Aucun trigger exposé")}</strong><div class="tiny muted">snapshot ${esc(o.source_snapshot_id)}</div></div>
  </div>`).join("");
}

function renderComparison(comparison) {
  const el = document.getElementById("comparison");
  const metrics = Object.values(comparison?.metrics || {});
  if (!metrics.length) { el.innerHTML = '<p class="empty">Comparaison indisponible.</p>'; return; }
  const systems = Object.keys(metrics[0].values || {});
  el.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Métrique</th>${systems.map(s => `<th>${esc(s.replace("shadow_", ""))}</th>`).join("")}<th>Disponibilité</th></tr></thead><tbody>
    ${metrics.map(m => `<tr><td>${esc(m.metric)}</td>${systems.map(s => `<td>${m.values[s] === null ? '<span class="unavailable">Indisponible</span>' : esc(m.values[s])}</td>`).join("")}<td>${esc(m.availability)}</td></tr>`).join("")}
  </tbody></table></div><p class="tiny muted">Observation uniquement : aucune promotion ni modification du risque n'est produite par cette comparaison.</p>`;
}

function renderDecisions(decisions) {
  const el = document.getElementById("decisions");
  if (!decisions?.length) { el.innerHTML = '<p class="empty">Aucune décision SHADOW observée.</p>'; return; }
  el.innerHTML = decisions.slice(-30).reverse().map(d => {
    const cls = esc(d.pipeline_status.toLowerCase());
    const direction = d.professor?.direction || "—";
    const proposal = d.proposal ? `${d.proposal.side} ${d.proposal.symbol}` : "Aucune proposition";
    const risk = d.risk ? `${d.risk.status} · ${d.risk.reason_codes.join(", ") || "aucun reason code"}` : "Risk Engine non appelé / indisponible";
    return `<div class="decision"><div class="decision-head"><strong>${esc(d.system_id)}</strong><span class="status ${cls}">${esc(d.pipeline_status)}</span></div><div class="tiny muted">${esc(d.opportunity_id)}</div><div class="tiny muted">Professor : ${esc(direction)} · ${esc(proposal)}</div><div class="reason-codes">${esc(risk)}</div>${d.failure_message ? `<div class="reason-codes">Erreur : ${esc(d.failure_message)}</div>` : ""}</div>`;
  }).join("");
}

function renderEvents(events) {
  const el = document.getElementById("events");
  document.getElementById("event-count").textContent = `${events.length} événement(s)`;
  if (!events.length) { el.innerHTML = '<p class="empty">Aucun événement d’audit ou sécurité projeté.</p>'; return; }
  el.innerHTML = events.slice(-80).reverse().map(e => `<div class="event"><strong class="severity-${esc(e.severity.toLowerCase())}">${esc(e.severity)}</strong><span>${esc(e.kind)}</span><div><strong>${esc(e.code || e.stage || e.source)}</strong><div class="tiny muted">${esc(e.message || e.status || "")}</div></div><span class="time">${esc(new Date(e.created_at).toLocaleString("fr-FR"))}</span></div>`).join("");
}

async function refresh() {
  try {
    const response = await fetch(endpoint, { method: "GET", headers: { "Accept": "application/json" }, cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    document.getElementById("system-state").textContent = data.system_state;
    document.getElementById("generated-at").textContent = `snapshot ${new Date(data.generated_at).toLocaleString("fr-FR")}`;
    document.getElementById("systems").innerHTML = data.systems.map(systemCard).join("");
    renderOpportunities(data.opportunities || []);
    renderComparison(data.comparison);
    renderDecisions(data.decisions || []);
    renderEvents(data.events || []);
  } catch (error) {
    document.getElementById("system-state").textContent = "DASHBOARD_UNAVAILABLE";
    document.getElementById("systems").innerHTML = `<div class="panel empty">Impossible de lire le read model : ${esc(error.message)}</div>`;
  }
}

refresh();
setInterval(refresh, 10000);
