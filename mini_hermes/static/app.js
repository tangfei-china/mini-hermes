const form = document.querySelector("#runForm");
const messageInput = document.querySelector("#messageInput");
const fakeMode = document.querySelector("#fakeMode");
const conversation = document.querySelector("#conversation");
const timeline = document.querySelector("#timeline");
const detailTitle = document.querySelector("#detailTitle");
const detailJson = document.querySelector("#detailJson");
const selectedStatus = document.querySelector("#selectedStatus");
const runMeta = document.querySelector("#runMeta");
const sendButton = document.querySelector("#sendButton");
const clearButton = document.querySelector("#clearButton");
const sessionMeta = document.querySelector("#sessionMeta");

let events = [];
let selectedStep = null;
let sessionId = localStorage.getItem("miniHermesSessionId") || createSessionId();

function createSessionId() {
  const id = crypto.randomUUID();
  localStorage.setItem("miniHermesSessionId", id);
  return id;
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function labelFor(type) {
  return {
    user_message: "User Message",
    build_api_kwargs: "Build API Args",
    model_response: "Model Response",
    tool_call: "Tool Call",
    tool_result: "Tool Result",
    empty_response_retry: "Empty Response Retry",
    streaming_fallback: "Streaming Fallback",
    final_response: "Final Response",
  }[type] || type;
}

function statusFor(event) {
  if (event.type === "final_response" && !event.data?.content) return "warning";
  if (event.type === "final_response") return "success";
  if (event.type === "streaming_fallback") return "warning";
  if (event.type === "tool_result" && event.data?.content?.includes("\"error\"")) return "error";
  return "success";
}

function messageBubble(role, text, tone = "") {
  const item = document.createElement("article");
  const normalizedRole = role.toLowerCase();
  item.className = `message ${normalizedRole} ${tone}`;
  item.innerHTML = `
    <div class="message-avatar" aria-hidden="true">${role === "You" ? "Y" : role.slice(0, 1)}</div>
    <div class="message-body">
      <div class="message-role">${role}</div>
      <div class="message-text"></div>
    </div>
  `;
  item.querySelector(".message-text").textContent = text;
  return item;
}

function appendToolCard(assistantBubble, event, toolCards) {
  const body = assistantBubble.querySelector(".message-body");
  const card = document.createElement("div");
  const id = event.data?.id || "";
  card.className = "tool-card running";
  card.innerHTML = `
    <span class="tool-icon">&lt;/&gt;</span>
    <span class="tool-name"></span>
    <span class="tool-state">running</span>
  `;
  card.querySelector(".tool-name").textContent = toolLabel(event);
  body.insertBefore(card, assistantBubble.querySelector(".message-text"));
  if (id) toolCards.set(id, card);
}

function finishToolCard(event, toolCards) {
  const id = event.data?.tool_call_id || "";
  const card = toolCards.get(id);
  if (!card) return;
  const failed = event.data?.content?.includes("\"error\"");
  card.className = `tool-card ${failed ? "failed" : "done"}`;
  card.querySelector(".tool-state").textContent = failed ? "error" : "success";
}

function toolLabel(event) {
  const name = event.data?.name || "tool";
  let args = {};
  try {
    args = JSON.parse(event.data?.arguments || "{}");
  } catch {
    return name;
  }
  if (name === "read_file" && args.path) return `Read ${args.path}`;
  if (name === "list_files" && args.path) return `List ${args.path}`;
  if (name === "run_shell" && args.command) return `Run ${args.command}`;
  return name;
}

function renderTimeline() {
  timeline.className = "timeline";
  timeline.innerHTML = "";
  if (!events.length) {
    timeline.className = "timeline empty-state";
    timeline.textContent = "Send a message to inspect the agent loop.";
    return;
  }

  events.forEach((event) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `timeline-row ${selectedStep === event.step ? "selected" : ""}`;
    row.innerHTML = `
      <span class="step-number">${event.step}</span>
      <span class="step-main">
        <span class="step-title">${labelFor(event.type)}</span>
        <span class="step-subtitle">${subtitleFor(event)}</span>
      </span>
      <span class="status ${statusFor(event)}">${statusFor(event)}</span>
    `;
    row.addEventListener("click", () => selectStep(event.step));
    timeline.appendChild(row);
  });
}

function subtitleFor(event) {
  if (event.type === "tool_call") return event.data?.name || "";
  if (event.type === "build_api_kwargs") return `iteration ${event.data?.iteration}`;
  if (event.type === "model_response") return `iteration ${event.data?.iteration}`;
  if (event.type === "empty_response_retry") return `attempt ${event.data?.attempt}/${event.data?.max_attempts}`;
  if (event.type === "streaming_fallback") return "using non-stream fallback";
  return "";
}

function selectStep(step) {
  selectedStep = step;
  const event = events.find((item) => item.step === step);
  if (!event) return;
  detailTitle.textContent = `${event.step}. ${labelFor(event.type)}`;
  selectedStatus.textContent = statusFor(event);
  selectedStatus.className = `status ${statusFor(event)}`;
  detailJson.textContent = pretty(event);
  renderTimeline();
}

async function runAgent(message, fake) {
  const started = performance.now();
  sendButton.disabled = true;
  sendButton.textContent = "Running";
  runMeta.textContent = "Streaming...";
  events = [];
  selectedStep = null;
  renderTimeline();
  conversation.appendChild(messageBubble("You", message));
  const assistantBubble = messageBubble("Assistant", "");
  const toolCards = new Map();
  conversation.appendChild(assistantBubble);
  const assistantText = assistantBubble.querySelector(".message-text");
  detailTitle.textContent = "Running";
  detailJson.textContent = "{}";

  const params = new URLSearchParams({
    session_id: sessionId,
    message,
    fake: fake ? "1" : "0",
  });
  const source = new EventSource(`/api/stream?${params.toString()}`);

  source.addEventListener("trace", (event) => {
    const traceEvent = JSON.parse(event.data);
    events.push(traceEvent);
    renderTimeline();
    selectStep(traceEvent.step);
    if (traceEvent.type === "tool_call") {
      appendToolCard(assistantBubble, traceEvent, toolCards);
    }
    if (traceEvent.type === "tool_result") {
      finishToolCard(traceEvent, toolCards);
    }
  });

  source.addEventListener("delta", (event) => {
    const payload = JSON.parse(event.data);
    assistantText.textContent += payload.text || "";
    conversation.scrollTop = conversation.scrollHeight;
  });

  source.addEventListener("done", (event) => {
    const payload = JSON.parse(event.data);
    assistantText.textContent = payload.final || "(model returned an empty final response)";
    if (payload.events?.length) {
      events = payload.events;
      renderTimeline();
      selectStep(events.length);
    }
    runMeta.textContent = `${events.length} steps · ${Math.round(performance.now() - started)}ms · ${payload.fake ? "fake" : payload.model}`;
    source.close();
    sendButton.disabled = false;
    sendButton.textContent = "Send";
  });

  source.addEventListener("run_error", (event) => {
    if (event.data) {
      const payload = JSON.parse(event.data);
      assistantBubble.classList.add("error");
      assistantText.textContent = cleanError(payload.error || "Stream failed");
    }
    runMeta.textContent = "Failed";
    source.close();
    sendButton.disabled = false;
    sendButton.textContent = "Send";
  });

  source.onerror = () => {
    if (sendButton.disabled) {
      runMeta.textContent = "Connection closed";
      sendButton.disabled = false;
      sendButton.textContent = "Send";
    }
    source.close();
  };
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;
  runAgent(message, fakeMode.checked);
  messageInput.value = "";
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  if (!sendButton.disabled) {
    form.requestSubmit();
  }
});

clearButton.addEventListener("click", () => {
  sessionId = createSessionId();
  events = [];
  selectedStep = null;
  conversation.innerHTML = "";
  detailTitle.textContent = "Select a step";
  detailJson.textContent = "{}";
  selectedStatus.textContent = "idle";
  selectedStatus.className = "status muted";
  runMeta.textContent = "No run yet";
  sessionMeta.textContent = `Session ${sessionId.slice(0, 8)}`;
  renderTimeline();
});

function cleanError(errorText) {
  const text = String(errorText || "").trim();
  const lowered = text.toLowerCase();
  if (lowered.includes("<!doctype html") || lowered.includes("<html")) {
    if (lowered.includes("unable to connect")) {
      return "模型服务返回了 HTML 错误页：Unable to connect。请检查上游服务或代理连接。";
    }
    return "模型服务返回了 HTML 错误页，不是有效的模型响应。请检查上游服务或代理。";
  }
  return text;
}

sessionMeta.textContent = `Session ${sessionId.slice(0, 8)}`;
renderTimeline();
