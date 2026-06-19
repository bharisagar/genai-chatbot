const serviceSelect = document.querySelector("#dashboardServiceSelect");
const dayRangeSelect = document.querySelector("#dayRangeSelect");
const dashboardHealth = document.querySelector("#dashboardHealth");
const dashboardTitle = document.querySelector("#dashboardTitle");
const dashboardSubtitle = document.querySelector("#dashboardSubtitle");
const metricRequests = document.querySelector("#metricRequests");
const metricRequestsHint = document.querySelector("#metricRequestsHint");
const metricSuccessRate = document.querySelector("#metricSuccessRate");
const metricSuccessHint = document.querySelector("#metricSuccessHint");
const metricLatency = document.querySelector("#metricLatency");
const metricP95 = document.querySelector("#metricP95");
const metricP95Hint = document.querySelector("#metricP95Hint");
const metricTokens = document.querySelector("#metricTokens");
const metricCost = document.querySelector("#metricCost");
const metricSlo = document.querySelector("#metricSlo");
const metricBudget = document.querySelector("#metricBudget");
const serviceBreakdown = document.querySelector("#serviceBreakdown");
const intentBreakdown = document.querySelector("#intentBreakdown");
const evidenceTable = document.querySelector("#evidenceTable");
const alertList = document.querySelector("#alertList");
const eventDetail = document.querySelector("#eventDetail");
const dailyChart = document.querySelector("#dailyChart");
const chartContext = dailyChart.getContext("2d");

let servicePacks = [];
let latestDaily = [];

function selectedServiceId() {
  return serviceSelect.value || "";
}

function selectedServiceName() {
  const selected = servicePacks.find((pack) => pack.id === selectedServiceId());
  return selected ? selected.name : "All services";
}

function queryParams(extra = {}) {
  const params = new URLSearchParams();
  const serviceId = selectedServiceId();
  const days = dayRangeSelect.value;
  if (serviceId) {
    params.set("service_id", serviceId);
  }
  if (days) {
    params.set("days", days);
  }
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, value);
    }
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function formatMoney(value) {
  return `$${Number(value || 0).toFixed(4)}`;
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    if (!response.ok) {
      throw new Error("Health check failed");
    }
    dashboardHealth.textContent = "API online";
    dashboardHealth.classList.add("ok");
    dashboardHealth.classList.remove("error");
  } catch (error) {
    dashboardHealth.textContent = "API offline";
    dashboardHealth.classList.add("error");
    dashboardHealth.classList.remove("ok");
  }
}

async function loadServicePacks() {
  const response = await fetch("/api/service-packs");
  if (!response.ok) {
    throw new Error("Service packs unavailable");
  }
  servicePacks = await response.json();
  servicePacks.forEach((pack) => {
    const option = document.createElement("option");
    option.value = pack.id;
    option.textContent = pack.name;
    serviceSelect.appendChild(option);
  });
}

function updateTitle() {
  const name = selectedServiceName();
  dashboardTitle.textContent = `${name} observability`;
  dashboardSubtitle.textContent = selectedServiceId()
    ? "Dashboard is filtered to the selected service pack. Requests, graph, and evidence show only that resource lens."
    : "Dashboard is showing all chatbot service-pack activity across AWS resources.";
}

function renderSummary(summary) {
  metricRequests.textContent = formatNumber(summary.request_count);
  metricRequestsHint.textContent = `${formatNumber(summary.error_count)} errors`;
  metricSuccessRate.textContent = formatPercent(summary.success_rate);
  metricSuccessHint.textContent = `${formatNumber(summary.success_count)} successful`;
  metricLatency.textContent = `${summary.avg_latency_ms} ms`;
  metricP95.textContent = `${summary.latency_p95_ms} ms`;
  metricP95Hint.textContent = `Target ${summary.slo?.latency_p95_target_ms || 1000} ms`;
  metricTokens.textContent = formatNumber(summary.total_tokens);
  metricCost.textContent = formatMoney(summary.estimated_cost_usd);
  const sloStatus = summary.slo?.status || "no_data";
  metricSlo.textContent = sloStatus.replace("_", " ");
  metricSlo.className = `slo-${sloStatus.replace("_", "-")}`;
  metricBudget.textContent = `Error budget ${formatPercent(summary.slo?.error_budget_remaining || 0)}`;
  renderBreakdown(serviceBreakdown, summary.by_service, "No service data yet");
  renderBreakdown(intentBreakdown, summary.by_intent, "No intent data yet");
}

function renderBreakdown(container, values, emptyText) {
  const entries = Object.entries(values || {}).sort((a, b) => b[1] - a[1]);
  container.innerHTML = "";
  if (!entries.length) {
    container.innerHTML = `<div class="empty-state">${emptyText}</div>`;
    return;
  }
  const max = Math.max(...entries.map((entry) => entry[1]), 1);
  entries.forEach(([label, count]) => {
    const row = document.createElement("div");
    row.className = "breakdown-row";
    const percent = Math.max(5, Math.round((count / max) * 100));
    row.innerHTML = `
      <div class="breakdown-line">
        <span>${label}</span>
        <strong>${formatNumber(count)}</strong>
      </div>
      <div class="bar-track"><div class="bar-fill" style="width:${percent}%"></div></div>
    `;
    container.appendChild(row);
  });
}

function renderEvidence(events) {
  evidenceTable.innerHTML = "";
  if (!events.length) {
    evidenceTable.innerHTML = '<div class="empty-state">No evidence captured for this filter yet.</div>';
    return;
  }
  events.forEach((event) => {
    const row = document.createElement("div");
    row.className = "evidence-row";
    row.dataset.requestId = event.request_id;
    const reason = event.explainability?.selected_service_reason || "No selection reason captured.";
    const intent = event.explainability?.selected_intent_reason || "No intent reason captured.";
    row.innerHTML = `
      <div>
        <span>Service</span>
        <strong>${event.service_name || event.service_id}</strong>
      </div>
      <div>
        <span>Intent</span>
        <strong>${event.intent}</strong>
      </div>
      <div>
        <span>Why this action</span>
        <p>${reason} ${intent}</p>
      </div>
      <div>
        <span>Tokens</span>
        <strong>${formatNumber(event.total_tokens)}</strong>
      </div>
      <div>
        <span>Inspect</span>
        <button class="inspect-button" type="button">Open</button>
      </div>
    `;
    row.addEventListener("click", () => inspectEvent(event.request_id));
    evidenceTable.appendChild(row);
  });
}

function renderAlerts(alerts) {
  alertList.innerHTML = "";
  alerts.forEach((alert) => {
    const item = document.createElement("div");
    item.className = `alert-item ${alert.severity}`;
    item.innerHTML = `
      <strong>${alert.title}</strong>
      <p>${alert.detail}</p>
    `;
    alertList.appendChild(item);
  });
}

function renderEventDetail(event) {
  const context = event.explainability?.approved_context || {};
  const sections = context.dashboard_sections || [];
  eventDetail.innerHTML = `
    <div class="detail-block">
      <strong>${event.request_id}</strong>
      <p>${event.service_name} | ${event.intent} | ${event.response_source}</p>
    </div>
    <div class="detail-block">
      <strong>Decision path</strong>
      <p>${event.explainability?.selected_service_reason || "No service reason captured."}</p>
      <p>${event.explainability?.selected_intent_reason || "No intent reason captured."}</p>
      <p>${event.explainability?.action_taken || "No action captured."}</p>
    </div>
    <div class="detail-block">
      <strong>Operational signals</strong>
      <p>Latency ${event.latency_ms} ms | Tokens ${formatNumber(event.total_tokens)} | Cost ${formatMoney(event.estimated_cost_usd)}</p>
      <p>Message hash ${event.message_hash} | Confidence ${event.confidence}</p>
    </div>
    <div class="detail-block">
      <strong>Approved context</strong>
      <ul class="detail-list">
        ${sections.map((section) => `<li>${section}</li>`).join("")}
      </ul>
    </div>
  `;
}

async function inspectEvent(requestId) {
  const response = await fetch(`/api/observability/events/${requestId}`);
  if (!response.ok) {
    eventDetail.innerHTML = '<div class="empty-state">Event detail is no longer available.</div>';
    return;
  }
  renderEventDetail(await response.json());
}

function resizeCanvas() {
  const pixelRatio = window.devicePixelRatio || 1;
  const rect = dailyChart.getBoundingClientRect();
  dailyChart.width = Math.max(600, Math.floor(rect.width * pixelRatio));
  dailyChart.height = Math.floor(300 * pixelRatio);
  chartContext.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
}

function drawDailyChart(rows) {
  latestDaily = rows;
  resizeCanvas();
  const width = dailyChart.getBoundingClientRect().width;
  const height = 300;
  const padding = { top: 20, right: 20, bottom: 42, left: 46 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const maxValue = Math.max(
    1,
    ...rows.map((row) => Math.max(row.request_count, row.error_count, row.total_tokens / 100))
  );

  chartContext.clearRect(0, 0, width, height);
  chartContext.fillStyle = "#ffffff";
  chartContext.fillRect(0, 0, width, height);

  chartContext.strokeStyle = "#d8e0eb";
  chartContext.lineWidth = 1;
  chartContext.fillStyle = "#65758b";
  chartContext.font = "12px Inter, system-ui, sans-serif";

  for (let i = 0; i <= 4; i += 1) {
    const y = padding.top + (chartHeight / 4) * i;
    chartContext.beginPath();
    chartContext.moveTo(padding.left, y);
    chartContext.lineTo(width - padding.right, y);
    chartContext.stroke();
    const value = Math.round(maxValue - (maxValue / 4) * i);
    chartContext.fillText(value.toString(), 10, y + 4);
  }

  const slot = chartWidth / Math.max(rows.length, 1);
  const barWidth = Math.min(34, slot * 0.44);
  rows.forEach((row, index) => {
    const x = padding.left + slot * index + (slot - barWidth) / 2;
    const requestHeight = (row.request_count / maxValue) * chartHeight;
    const errorHeight = (row.error_count / maxValue) * chartHeight;
    const baseY = padding.top + chartHeight;

    chartContext.fillStyle = "#1d4ed8";
    chartContext.fillRect(x, baseY - requestHeight, barWidth, requestHeight);

    if (row.error_count > 0) {
      chartContext.fillStyle = "#b91c1c";
      chartContext.fillRect(x + barWidth * 0.58, baseY - errorHeight, barWidth * 0.42, errorHeight);
    }

    const label = row.date.slice(5);
    chartContext.fillStyle = "#65758b";
    chartContext.save();
    chartContext.translate(x + barWidth / 2, height - 18);
    chartContext.rotate(-0.45);
    chartContext.fillText(label, 0, 0);
    chartContext.restore();
  });
}

async function refreshDashboard() {
  updateTitle();
  const [summaryResponse, dailyResponse, recentResponse, alertsResponse] = await Promise.all([
    fetch(`/api/observability/summary${queryParams()}`),
    fetch(`/api/observability/daily${queryParams()}`),
    fetch(`/api/observability/recent${queryParams({ limit: 8 })}`),
    fetch(`/api/observability/alerts${queryParams()}`)
  ]);

  if (!summaryResponse.ok || !dailyResponse.ok || !recentResponse.ok || !alertsResponse.ok) {
    throw new Error("Dashboard data unavailable");
  }

  renderSummary(await summaryResponse.json());
  drawDailyChart(await dailyResponse.json());
  renderEvidence(await recentResponse.json());
  renderAlerts(await alertsResponse.json());
}

async function boot() {
  await checkHealth();
  await loadServicePacks();
  await refreshDashboard();
}

serviceSelect.addEventListener("change", refreshDashboard);
dayRangeSelect.addEventListener("change", refreshDashboard);
window.addEventListener("resize", () => drawDailyChart(latestDaily));

boot().catch(() => {
  dashboardHealth.textContent = "Dashboard unavailable";
  dashboardHealth.classList.add("error");
});

setInterval(() => {
  checkHealth();
  refreshDashboard().catch(() => {
    dashboardHealth.textContent = "Dashboard unavailable";
    dashboardHealth.classList.add("error");
  });
}, 30000);
