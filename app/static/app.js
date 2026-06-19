const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const messages = document.querySelector("#messages");
const healthStatus = document.querySelector("#healthStatus");
const runtimeMode = document.querySelector("#runtimeMode");
const bedrockToggle = document.querySelector("#bedrockToggle");
const serviceSelect = document.querySelector("#serviceSelect");
const activePackName = document.querySelector("#activePackName");
const activePackSummary = document.querySelector("#activePackSummary");

let servicePacks = [];

function appendMessage(role, text, meta = "") {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  if (meta) {
    const metaNode = document.createElement("div");
    metaNode.className = "message-meta";
    metaNode.textContent = meta;
    node.appendChild(metaNode);
  }
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  node.appendChild(paragraph);
  messages.appendChild(node);
  messages.scrollTop = messages.scrollHeight;
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    if (!response.ok) {
      throw new Error("Health check failed");
    }
    healthStatus.textContent = "API online";
    healthStatus.classList.add("ok");
  } catch (error) {
    healthStatus.textContent = "API offline";
    healthStatus.classList.add("error");
  }
}

async function checkRuntime() {
  try {
    const response = await fetch("/api/runtime");
    if (!response.ok) {
      throw new Error("Runtime check failed");
    }
    const runtime = await response.json();
    const label = runtime.bedrock_enabled ? "Bedrock grounded" : "Service-pack fallback";
    runtimeMode.textContent = `Mode: ${label}`;
    bedrockToggle.checked = runtime.bedrock_enabled;
    bedrockToggle.disabled = !runtime.bedrock_enabled;
    runtimeMode.title = runtime.bedrock_model_id
      ? `${runtime.bedrock_model_id} in ${runtime.bedrock_region}`
      : "Deterministic approved ECS/Fargate service-pack responses";
  } catch (error) {
    runtimeMode.textContent = "Mode: unavailable";
    bedrockToggle.disabled = true;
  }
}

function updateActivePack() {
  const selected = servicePacks.find((pack) => pack.id === serviceSelect.value);
  if (!selected) {
    activePackName.textContent = "Auto detect";
    activePackSummary.textContent = "Ask naturally and the advisor will choose the closest AWS service pack.";
    return;
  }
  activePackName.textContent = selected.name;
  activePackSummary.textContent = selected.summary;
}

async function loadServicePacks() {
  try {
    const response = await fetch("/api/service-packs");
    if (!response.ok) {
      throw new Error("Service pack load failed");
    }
    servicePacks = await response.json();
    servicePacks.forEach((pack) => {
      const option = document.createElement("option");
      option.value = pack.id;
      option.textContent = pack.name;
      serviceSelect.appendChild(option);
    });
    serviceSelect.value = "ecs-fargate";
    updateActivePack();
  } catch (error) {
    activePackName.textContent = "Service packs unavailable";
    activePackSummary.textContent = "The advisor API did not return service-pack metadata.";
  }
}

async function sendMessage(text) {
  const trimmed = text.trim();
  if (!trimmed) {
    return;
  }

  appendMessage("user", trimmed);
  input.value = "";
  form.querySelector("button").disabled = true;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: trimmed,
        service_id: serviceSelect.value || null,
        use_bedrock: bedrockToggle.checked
      })
    });

    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }

    const payload = await response.json();
    if (!serviceSelect.value && payload.service_id) {
      serviceSelect.value = payload.service_id;
      updateActivePack();
    }
    const sourceLabel = payload.response_source === "bedrock_grounded" ? "Bedrock grounded" : "Service pack";
    const reason = payload.explainability?.selected_service_reason || "Service selected by advisor.";
    const meta = [
      sourceLabel,
      payload.service_name,
      payload.intent,
      `${payload.latency_ms} ms`,
      `${payload.total_tokens} tokens`,
      `cost $${Number(payload.estimated_cost_usd).toFixed(4)}`,
      `request ${payload.request_id}`,
      reason
    ].join(" | ");
    appendMessage("assistant", payload.answer, meta);
  } catch (error) {
    appendMessage("system", "The advisor API did not respond. Check the backend logs and try again.");
  } finally {
    form.querySelector("button").disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    sendMessage(button.dataset.prompt);
  });
});

serviceSelect.addEventListener("change", updateActivePack);

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(input.value);
  }
});

checkHealth();
checkRuntime();
loadServicePacks();
