const form = document.querySelector("#runForm");
const chatTab = document.querySelector("#chatTab");
const skillsTab = document.querySelector("#skillsTab");
const chatView = document.querySelector("#chatView");
const skillsView = document.querySelector("#skillsView");
const messageInput = document.querySelector("#messageInput");
const fakeMode = document.querySelector("#fakeMode");
const conversation = document.querySelector("#conversation");
const timeline = document.querySelector("#timeline");
const runMeta = document.querySelector("#runMeta");
const sendButton = document.querySelector("#sendButton");
const clearButton = document.querySelector("#clearButton");
const sessionMeta = document.querySelector("#sessionMeta");
const sessionList = document.querySelector("#sessionList");
const sessionCount = document.querySelector("#sessionCount");
const activeSkills = document.querySelector("#activeSkills");
const skillsMeta = document.querySelector("#skillsMeta");
const skillsToggle = document.querySelector("#skillsToggle");
const skillsSection = document.querySelector(".skills-section");
const skillsListPanel = document.querySelector("#skillsListPanel");
const newSkillButton = document.querySelector("#newSkillButton");
const reloadSkillsButton = document.querySelector("#reloadSkillsButton");
const skillUploadInput = document.querySelector("#skillUploadInput");
const skillEditor = document.querySelector("#skillEditor");
const skillEditorTitle = document.querySelector("#skillEditorTitle");
const skillEditorSubtitle = document.querySelector("#skillEditorSubtitle");
const saveSkillButton = document.querySelector("#saveSkillButton");
const deleteSkillButton = document.querySelector("#deleteSkillButton");
const skillSaveStatus = document.querySelector("#skillSaveStatus");
const timelineToggle = document.querySelector("#timelineToggle");
const timelineSection = document.querySelector(".timeline-section");

let events = [];
let selectedStep = null;
let selectedSkills = [];
let sessionId = localStorage.getItem("miniHermesSessionId") || createSessionId();
let skillsCollapsed = localStorage.getItem("miniHermesSkillsCollapsed") === "1";
let timelineCollapsed = localStorage.getItem("miniHermesTimelineCollapsed") === "1";
let skillsCatalog = [];
let selectedSkillSlug = "";
let selectedSkillCanDelete = false;
let sessionsCatalog = [];

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
    skills_loaded: "Skills Loaded",
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

function formatDuration(ms) {
  if (ms === undefined || ms === null || ms === "") return "—";
  const value = Number(ms);
  if (!Number.isFinite(value)) return "—";
  if (value < 1000) return `${Math.max(0, Math.round(value))}ms`;
  const seconds = value / 1000;
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

function formatOffset(ms) {
  if (ms === undefined || ms === null || ms === "") return "—";
  return `+${formatDuration(ms)}`;
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderInlineMarkdown(text) {
  const codePlaceholders = [];
  let html = escapeHtml(text).replace(/`([^`]+)`/g, (_match, code) => {
    const token = `\u0000CODE${codePlaceholders.length}\u0000`;
    codePlaceholders.push(`<code>${code}</code>`);
    return token;
  });
  html = html
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  codePlaceholders.forEach((codeHtml, index) => {
    html = html.replace(`\u0000CODE${index}\u0000`, codeHtml);
  });
  return html;
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").split(/\r?\n/);
  const html = [];
  let paragraph = [];
  let inList = false;
  let inCodeBlock = false;
  let codeLines = [];

  const closeParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (!inList) return;
    html.push("</ul>");
    inList = false;
  };
  const closeCodeBlock = () => {
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    codeLines = [];
    inCodeBlock = false;
  };

  for (const line of lines) {
    if (/^```/.test(line.trim())) {
      if (inCodeBlock) {
        closeCodeBlock();
      } else {
        closeParagraph();
        closeList();
        inCodeBlock = true;
        codeLines = [];
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    const listMatch = line.match(/^\s*[-*]\s+(.+)$/);
    if (listMatch) {
      closeParagraph();
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${renderInlineMarkdown(listMatch[1])}</li>`);
      continue;
    }

    if (!line.trim()) {
      closeParagraph();
      closeList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      closeParagraph();
      closeList();
      const level = headingMatch[1].length;
      html.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      continue;
    }

    closeList();
    paragraph.push(line.trim());
  }

  if (inCodeBlock) closeCodeBlock();
  closeParagraph();
  closeList();
  return html.join("");
}

function setMessageText(element, text, markdown = false) {
  element.__rawText = String(text || "");
  if (markdown) {
    element.innerHTML = renderMarkdown(element.__rawText);
    return;
  }
  element.textContent = element.__rawText;
}

function appendMessageText(element, text, markdown = false) {
  setMessageText(element, `${element.__rawText || ""}${text || ""}`, markdown);
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat("en-US").format(number);
}

function formatTokenSpeed(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "";
  return `${number.toFixed(1)} tokens/s`;
}

function formatContextUsage(usage) {
  const total = Number(usage?.total_tokens);
  const window = Number(usage?.context_window);
  if (!Number.isFinite(total) || !Number.isFinite(window) || window <= 0) return "";
  const percent = Number(usage?.context_percent);
  const percentText = Number.isFinite(percent) ? ` · ${percent.toFixed(1)}%` : "";
  return `context ${formatNumber(total)} / ${formatNumber(window)}${percentText}`;
}

function formatUsage(usage) {
  if (!usage) return "";
  const parts = [
    `input ${formatNumber(usage.input_tokens)}`,
    `output ${formatNumber(usage.output_tokens)}`,
    `total ${formatNumber(usage.total_tokens)}`,
  ];
  const context = formatContextUsage(usage);
  if (context) parts.push(context);
  const speed = formatTokenSpeed(usage.tokens_per_second);
  if (speed) parts.push(speed);
  if (usage.source === "estimated") parts.push("estimated");
  return parts.join(" · ");
}

function setMessageUsage(messageElement, usage) {
  const usageElement = messageElement.querySelector(".message-usage");
  if (!usageElement) return;
  const text = formatUsage(usage);
  usageElement.textContent = text;
  usageElement.hidden = !text;
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "readonly");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

function setCopyButton(messageElement, text) {
  const button = messageElement.querySelector(".message-copy");
  if (!button) return;
  const rawText = String(text || "");
  button.hidden = !rawText;
  button.textContent = "Copy";
  button.onclick = async () => {
    if (!rawText) return;
    try {
      await copyText(rawText);
      button.textContent = "Copied";
      setTimeout(() => {
        button.textContent = "Copy";
      }, 1200);
    } catch (error) {
      button.textContent = "Copy failed";
      setTimeout(() => {
        button.textContent = "Copy";
      }, 1600);
    }
  };
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
      <div class="message-footer">
        <div class="message-usage" hidden></div>
        <button class="message-copy" type="button" hidden>Copy</button>
      </div>
    </div>
  `;
  setMessageText(item.querySelector(".message-text"), text, normalizedRole === "assistant" && tone !== "error");
  if (normalizedRole === "assistant" && text && tone !== "error") {
    setCopyButton(item, text);
  }
  return item;
}

function formatAge(timestamp) {
  if (!timestamp) return "";
  const seconds = Math.max(0, (Date.now() / 1000) - Number(timestamp));
  if (seconds < 60) return "now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function renderSessions(sessions) {
  sessionsCatalog = sessions || [];
  sessionCount.textContent = `${sessionsCatalog.length} session${sessionsCatalog.length === 1 ? "" : "s"}`;
  sessionList.innerHTML = "";
  if (!sessionsCatalog.length) {
    sessionList.className = "session-list empty-state";
    sessionList.textContent = "Previous chats will appear here.";
    return;
  }

  sessionList.className = "session-list";
  for (const session of sessionsCatalog) {
    const item = document.createElement("article");
    item.className = `session-item ${session.id === sessionId ? "active" : ""}`;
    item.innerHTML = `
      <button class="session-main" type="button">
        <span class="session-title"></span>
        <span class="session-preview"></span>
        <span class="session-details"></span>
      </button>
      <button class="session-delete" type="button" title="Delete session">×</button>
    `;
    item.querySelector(".session-title").textContent = session.title || session.id;
    item.querySelector(".session-preview").textContent = session.preview || "";
    item.querySelector(".session-details").textContent = `${session.message_count || 0} msgs · ${formatAge(session.updated_at)}${session.fake ? " · fake" : ""}`;
    item.querySelector(".session-main").addEventListener("click", () => loadSession(session.id));
    item.querySelector(".session-delete").addEventListener("click", (event) => {
      event.stopPropagation();
      deleteSession(session.id);
    });
    sessionList.appendChild(item);
  }
}

async function loadSessions() {
  try {
    const response = await fetch("/api/sessions", { cache: "no-store" });
    const payload = await response.json();
    renderSessions(payload.sessions || []);
  } catch {
    renderSessions([]);
  }
}

function restoreConversation(session) {
  sessionId = session.id;
  localStorage.setItem("miniHermesSessionId", sessionId);
  sessionMeta.textContent = `Session ${sessionId.slice(0, 8)}`;
  conversation.innerHTML = "";
  for (const message of session.messages || []) {
    if (message.role === "user") {
      conversation.appendChild(messageBubble("You", message.content || ""));
    }
    if (message.role === "assistant" && message.content) {
      conversation.appendChild(messageBubble("Assistant", message.content || ""));
    }
  }
  events = [];
  selectedStep = null;
  runMeta.textContent = "Resumed";
  renderTimeline();
  renderSessions(sessionsCatalog);
  conversation.scrollTop = conversation.scrollHeight;
}

async function loadSession(id) {
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(id)}`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to load session");
    restoreConversation(payload.session);
  } catch (error) {
    runMeta.textContent = cleanError(error.message || "Failed to load session");
  }
}

async function deleteSession(id) {
  if (!confirm("Delete this session?")) return;
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(id)}`, { method: "POST" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to delete session");
    if (id === sessionId) {
      startNewChat();
    }
    await loadSessions();
  } catch (error) {
    runMeta.textContent = cleanError(error.message || "Failed to delete session");
  }
}

function appendSkillCard(assistantBubble, event) {
  const body = assistantBubble.querySelector(".message-body");
  const skills = event.data?.skills || [];
  const missing = event.data?.missing || [];
  if (!skills.length && !missing.length) return;

  const card = document.createElement("div");
  card.className = `skill-card ${missing.length ? "warning" : "active"}`;
  const skillNames = skills.map((skill) => skill.name).join(", ") || "No matching skills";
  card.innerHTML = `
    <span class="skill-icon">S</span>
    <span class="skill-name"></span>
    <span class="skill-state"></span>
  `;
  card.querySelector(".skill-name").textContent = skillNames;
  card.querySelector(".skill-state").textContent = missing.length ? `missing: ${missing.join(", ")}` : "auto loaded";
  body.insertBefore(card, assistantBubble.querySelector(".message-text"));
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
    const item = document.createElement("article");
    item.className = `timeline-item ${selectedStep === event.step ? "selected" : ""}`;
    item.innerHTML = `
      <button class="timeline-row" type="button" aria-expanded="${selectedStep === event.step}">
        <span class="step-number">${event.step}</span>
        <span class="step-main">
          <span class="step-title">${labelFor(event.type)}</span>
          <span class="step-subtitle">${subtitleFor(event)}</span>
        </span>
        <span class="step-meta">
          <span class="time-chip offset-time" title="Step start time since this run began">
            <span class="time-label">start</span>
            <span class="time-value">${formatOffset(event.offset_ms)}</span>
          </span>
          <span class="time-chip duration" title="Time spent inside this step">
            <span class="time-label">took</span>
            <span class="time-value">${formatDuration(event.duration_ms)}</span>
          </span>
          <span class="status ${statusFor(event)}">${statusFor(event)}</span>
        </span>
      </button>
    `;
    item.querySelector(".timeline-row").addEventListener("click", () => selectStep(event.step));
    if (selectedStep === event.step) {
      const detail = document.createElement("pre");
      detail.className = "timeline-detail";
      detail.textContent = pretty(event);
      item.appendChild(detail);
    }
    timeline.appendChild(item);
  });
}

function subtitleFor(event) {
  if (event.type === "skills_loaded") {
    const skills = event.data?.skills || [];
    const missing = event.data?.missing || [];
    if (skills.length) return skills.map((skill) => skill.slug).join(", ");
    if (missing.length) return `missing ${missing.join(", ")}`;
  }
  if (event.type === "tool_call") return event.data?.name || "";
  if (event.type === "build_api_kwargs") return `iteration ${event.data?.iteration}`;
  if (event.type === "model_response") return `iteration ${event.data?.iteration}`;
  if (event.type === "empty_response_retry") return `attempt ${event.data?.attempt}/${event.data?.max_attempts}`;
  if (event.type === "streaming_fallback") return "using non-stream fallback";
  return "";
}

function selectStep(step) {
  selectedStep = selectedStep === step ? null : step;
  renderTimeline();
}

function renderActiveSkills(skills, missing = []) {
  selectedSkills = skills || [];
  activeSkills.innerHTML = "";

  if (!selectedSkills.length && !missing.length) {
    activeSkills.className = "active-skills empty-state";
    activeSkills.textContent = "No skills auto-loaded for this run yet.";
    skillsMeta.textContent = "Auto mode";
    return;
  }

  activeSkills.className = "active-skills";
  selectedSkills.forEach((skill) => {
    const item = document.createElement("article");
    item.className = "active-skill";
    item.innerHTML = `
      <div class="active-skill-name"></div>
      <div class="active-skill-description"></div>
      <div class="active-skill-path"></div>
    `;
    item.querySelector(".active-skill-name").textContent = skill.name || skill.slug;
    item.querySelector(".active-skill-description").textContent = skill.description || "";
    item.querySelector(".active-skill-path").textContent = skill.path || "";
    activeSkills.appendChild(item);
  });

  missing.forEach((name) => {
    const item = document.createElement("article");
    item.className = "active-skill missing";
    item.innerHTML = `
      <div class="active-skill-name"></div>
      <div class="active-skill-description">Skill was requested but not found.</div>
    `;
    item.querySelector(".active-skill-name").textContent = name;
    activeSkills.appendChild(item);
  });

  const loadedCount = selectedSkills.length;
  const missingCount = missing.length;
  skillsMeta.textContent = `${loadedCount} active${missingCount ? ` · ${missingCount} missing` : ""}`;
}

function renderSkillsCollapse() {
  skillsSection.classList.toggle("collapsed", skillsCollapsed);
  skillsToggle.setAttribute("aria-expanded", String(!skillsCollapsed));
  skillsToggle.querySelector(".toggle-icon").classList.toggle("collapsed", skillsCollapsed);
}

function renderTimelineCollapse() {
  timelineSection.classList.toggle("collapsed", timelineCollapsed);
  timelineToggle.setAttribute("aria-expanded", String(!timelineCollapsed));
  timelineToggle.querySelector(".toggle-icon").classList.toggle("collapsed", timelineCollapsed);
}

function showView(name) {
  const showingSkills = name === "skills";
  chatView.classList.toggle("active", !showingSkills);
  skillsView.classList.toggle("active", showingSkills);
  chatTab.classList.toggle("active", !showingSkills);
  skillsTab.classList.toggle("active", showingSkills);
  if (showingSkills) loadSkillsCatalog(selectedSkillSlug);
}

async function loadSkillsCatalog(selectedSlug = "") {
  try {
    const response = await fetch("/api/skills", { cache: "no-store" });
    const payload = await response.json();
    skillsCatalog = payload.skills || [];
    renderSkillsList(selectedSlug);
  } catch (error) {
    skillSaveStatus.textContent = cleanError(error.message || "Failed to load skills");
  }
}

function renderSkillsList(selectedSlug = "") {
  skillsListPanel.innerHTML = "";
  if (!skillsCatalog.length) {
    skillsListPanel.className = "skills-list-panel empty-state";
    skillsListPanel.textContent = "No skills found.";
    skillEditor.value = "";
    saveSkillButton.disabled = true;
    deleteSkillButton.disabled = true;
    return;
  }

  skillsListPanel.className = "skills-list-panel";
  for (const skill of skillsCatalog) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `skill-list-item ${skill.slug === selectedSlug ? "selected" : ""}`;
    item.innerHTML = `
      <span class="skill-list-title"></span>
      <span class="skill-list-description"></span>
    `;
    item.querySelector(".skill-list-title").textContent = skill.slug;
    item.querySelector(".skill-list-description").textContent = skill.description || skill.path || "";
    item.addEventListener("click", () => loadSkillMarkdown(skill.slug));
    skillsListPanel.appendChild(item);
  }

  const nextSlug = selectedSlug || selectedSkillSlug || skillsCatalog[0].slug;
  if (nextSlug) loadSkillMarkdown(nextSlug);
}

function renderSelectedSkill(skill, markdown) {
  selectedSkillSlug = skill?.slug || "";
  selectedSkillCanDelete = Boolean(skill?.path?.includes("/skills/custom/"));
  skillEditorTitle.textContent = skill?.slug || "New skill";
  skillEditorSubtitle.textContent = skill?.path || "Draft a new SKILL.md";
  skillEditor.value = markdown || "";
  skillSaveStatus.textContent = skill?.path || "New skill will be imported into skills/custom";
  saveSkillButton.disabled = false;
  deleteSkillButton.disabled = !selectedSkillCanDelete;

  for (const item of skillsListPanel.querySelectorAll(".skill-list-item")) {
    item.classList.toggle("selected", item.querySelector(".skill-list-title")?.textContent === selectedSkillSlug);
  }
}

function startNewSkill() {
  const markdown = [
    "---",
    "name: new-skill",
    "description: Describe when this skill should be used.",
    "---",
    "",
    "# New Skill",
    "",
    "Use this skill when...",
    "",
  ].join("\n");
  renderSelectedSkill(null, markdown);
}

async function loadSkillMarkdown(slug) {
  if (!slug) return;
  skillSaveStatus.textContent = "Loading...";
  saveSkillButton.disabled = true;
  deleteSkillButton.disabled = true;
  try {
    const response = await fetch(`/api/skills/${encodeURIComponent(slug)}`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to load skill");
    renderSelectedSkill(payload.skill, payload.markdown || "");
  } catch (error) {
    skillEditor.value = "";
    skillSaveStatus.textContent = cleanError(error.message || "Failed to load skill");
  }
}

async function saveSelectedSkill() {
  const markdown = skillEditor.value;
  skillSaveStatus.textContent = "Saving...";
  saveSkillButton.disabled = true;
  try {
    const endpoint = selectedSkillSlug ? "/api/skills/save" : "/api/skills/import";
    const body = selectedSkillSlug
      ? { slug: selectedSkillSlug, markdown }
      : { markdown };
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to save skill");
    skillSaveStatus.textContent = `Saved ${payload.skill.slug}`;
    await loadSkillsCatalog(payload.skill.slug);
  } catch (error) {
    skillSaveStatus.textContent = cleanError(error.message || "Failed to save skill");
    saveSkillButton.disabled = false;
  }
}

async function deleteSelectedSkill() {
  if (!selectedSkillSlug || !selectedSkillCanDelete) return;
  if (!confirm(`Delete ${selectedSkillSlug}? This removes its folder under skills/custom.`)) return;
  skillSaveStatus.textContent = "Deleting...";
  deleteSkillButton.disabled = true;
  try {
    const response = await fetch("/api/skills/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: selectedSkillSlug }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to delete skill");
    selectedSkillSlug = "";
    skillSaveStatus.textContent = "Deleted";
    await loadSkillsCatalog();
  } catch (error) {
    skillSaveStatus.textContent = cleanError(error.message || "Failed to delete skill");
    deleteSkillButton.disabled = !selectedSkillCanDelete;
  }
}

async function importSkillFile(file) {
  const markdown = await file.text();
  skillSaveStatus.textContent = "Importing...";
  try {
    const response = await fetch("/api/skills/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to import skill");
    skillSaveStatus.textContent = `Imported ${payload.skill.slug}`;
    await loadSkillsCatalog(payload.skill.slug);
  } catch (error) {
    skillSaveStatus.textContent = cleanError(error.message || "Failed to import skill");
  } finally {
    skillUploadInput.value = "";
  }
}

async function runAgent(message, fake) {
  const started = performance.now();
  sendButton.disabled = true;
  sendButton.textContent = "Running";
  runMeta.textContent = "Streaming...";
  events = [];
  selectedStep = null;
  renderActiveSkills([], []);
  renderTimeline();
  conversation.appendChild(messageBubble("You", message));
  const assistantBubble = messageBubble("Assistant", "");
  const toolCards = new Map();
  conversation.appendChild(assistantBubble);
  const assistantText = assistantBubble.querySelector(".message-text");

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
    if (traceEvent.type === "skills_loaded") {
      renderActiveSkills(traceEvent.data?.skills || [], traceEvent.data?.missing || []);
      appendSkillCard(assistantBubble, traceEvent);
    }
  });

  source.addEventListener("delta", (event) => {
    const payload = JSON.parse(event.data);
    appendMessageText(assistantText, payload.text || "", true);
    conversation.scrollTop = conversation.scrollHeight;
  });

  source.addEventListener("done", (event) => {
    const payload = JSON.parse(event.data);
    setMessageText(assistantText, payload.final || "(model returned an empty final response)", true);
    setCopyButton(assistantBubble, payload.final || "");
    setMessageUsage(assistantBubble, payload.usage);
    if (payload.events?.length) {
      events = payload.events;
      renderTimeline();
      selectedStep = events.length;
      renderTimeline();
    }
    renderActiveSkills(payload.skills || [], []);
    if (payload.session) {
      renderSessions([payload.session, ...sessionsCatalog.filter((session) => session.id !== payload.session.id)]);
    } else {
      loadSessions();
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
      setMessageText(assistantText, cleanError(payload.error || "Stream failed"));
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

function startNewChat() {
  sessionId = createSessionId();
  events = [];
  selectedStep = null;
  conversation.innerHTML = "";
  runMeta.textContent = "No run yet";
  renderActiveSkills([], []);
  sessionMeta.textContent = `Session ${sessionId.slice(0, 8)}`;
  renderTimeline();
  renderSessions(sessionsCatalog);
}

clearButton.addEventListener("click", () => {
  startNewChat();
});

skillsToggle.addEventListener("click", () => {
  skillsCollapsed = !skillsCollapsed;
  localStorage.setItem("miniHermesSkillsCollapsed", skillsCollapsed ? "1" : "0");
  renderSkillsCollapse();
});

timelineToggle.addEventListener("click", () => {
  timelineCollapsed = !timelineCollapsed;
  localStorage.setItem("miniHermesTimelineCollapsed", timelineCollapsed ? "1" : "0");
  renderTimelineCollapse();
});

chatTab.addEventListener("click", () => {
  showView("chat");
});

skillsTab.addEventListener("click", () => {
  showView("skills");
});

reloadSkillsButton.addEventListener("click", () => {
  loadSkillsCatalog(selectedSkillSlug);
});

newSkillButton.addEventListener("click", () => {
  startNewSkill();
});

saveSkillButton.addEventListener("click", () => {
  saveSelectedSkill();
});

deleteSkillButton.addEventListener("click", () => {
  deleteSelectedSkill();
});

skillUploadInput.addEventListener("change", () => {
  const file = skillUploadInput.files?.[0];
  if (file) importSkillFile(file);
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
renderActiveSkills([], []);
renderSkillsCollapse();
renderTimelineCollapse();
loadSkillsCatalog();
loadSessions();
renderTimeline();
