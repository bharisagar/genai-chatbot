const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const messages = document.querySelector("#messages");
const healthStatus = document.querySelector("#healthStatus");

function appendMessage(role, text) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
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
        service_id: "ecs-fargate"
      })
    });

    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }

    const payload = await response.json();
    appendMessage("assistant", payload.answer);
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

