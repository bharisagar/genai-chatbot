const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const messages = document.querySelector("#messages");
const healthStatus = document.querySelector("#healthStatus");
const runtimeMode = document.querySelector("#runtimeMode");
const bedrockToggle = document.querySelector("#bedrockToggle");

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
        service_id: "ecs-fargate",
        use_bedrock: bedrockToggle.checked
      })
    });

    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }

    const payload = await response.json();
    const sourceLabel = payload.response_source === "bedrock_grounded" ? "Bedrock grounded" : "Service pack";
    appendMessage("assistant", payload.answer, `${sourceLabel} | ${payload.intent}`);
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

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(input.value);
  }
});

checkHealth();
checkRuntime();
