const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert");

class FakeClassList {
  toggle() {}
  add() {}
}

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName;
    this.children = [];
    this.eventListeners = {};
    this.className = "";
    this.textContent = "";
    this._innerHTML = "";
    this.hidden = false;
    this.classList = new FakeClassList();
    this.style = {};
  }

  set innerHTML(value) {
    this._innerHTML = value;
    this.children = [];
    const classNames = [...value.matchAll(/class="([^"]+)"/g)].flatMap((match) => match[1].split(/\s+/));
    for (const className of classNames) {
      const child = new FakeElement("div");
      child.className = className;
      this.children.push(child);
    }
  }

  get innerHTML() {
    return this._innerHTML;
  }

  querySelector(selector) {
    if (!selector.startsWith(".")) return new FakeElement();
    const className = selector.slice(1);
    return this.children.find((child) => child.className.split(/\s+/).includes(className)) || new FakeElement();
  }

  querySelectorAll() {
    return [];
  }

  appendChild(child) {
    this.children.push(child);
    this._innerHTML += child.innerHTML || child.textContent || "";
    return child;
  }

  insertBefore(child) {
    this.children.push(child);
    return child;
  }

  addEventListener(type, listener) {
    this.eventListeners[type] = listener;
  }

  setAttribute(name, value) {
    this[name] = value;
  }
}

const elements = new Map();
function getElement(selector) {
  if (!elements.has(selector)) elements.set(selector, new FakeElement());
  return elements.get(selector);
}

const appJs = fs.readFileSync(path.join(__dirname, "..", "mini_hermes", "static", "app.js"), "utf8");
const indexHtml = fs.readFileSync(path.join(__dirname, "..", "mini_hermes", "static", "index.html"), "utf8");
const stylesCss = fs.readFileSync(path.join(__dirname, "..", "mini_hermes", "static", "styles.css"), "utf8");

assert.match(indexHtml, /id="sessionMeta" class="toolbar-pill session-pill"/);
assert.match(indexHtml, /class="mode-toggle fake-toggle"/);
assert.match(stylesCss, /\.session-pill\s*{\s*display:\s*none;\s*}/);
assert.match(stylesCss, /\.fake-toggle\s*{\s*display:\s*none;\s*}/);

const context = {
  console,
  crypto: { randomUUID: () => "new-session-id" },
  localStorage: { getItem: () => null, setItem: () => {} },
  document: {
    querySelector: getElement,
    createElement: (tagName) => new FakeElement(tagName),
  },
  navigator: { clipboard: { writeText: async () => {} } },
  fetch: () => Promise.resolve({ json: () => Promise.resolve({ skills: [] }) }),
  URLSearchParams,
  EventSource: function EventSource() {},
  performance: { now: () => 0 },
  confirm: () => true,
  setTimeout: () => {},
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(appJs, context, { filename: "app.js" });

const sessions = [
  {
    id: "session-a",
    title: "负荷预测项目",
    preview: "可以从负荷预测开始",
    message_count: 4,
    updated_at: 1778849000,
    fake: false,
  },
];

context.renderSessions(sessions);
const historyList = getElement("#sessionList");
const firstSession = historyList.children[0];
assert.strictEqual(firstSession.querySelector(".session-title").textContent, "负荷预测项目");
assert.match(firstSession.querySelector(".session-details").textContent, /4 msgs/);

context.restoreConversation({
  id: "session-a",
  title: "负荷预测项目",
  messages: [
    { role: "system", content: "hidden system" },
    { role: "user", content: "用户问题" },
    { role: "assistant", content: "## 回答\n\n- 重点" },
    { role: "tool", content: "hidden tool" },
  ],
});

const conversation = getElement("#conversation");
assert.strictEqual(conversation.children.length, 2);
assert.strictEqual(conversation.children[0].querySelector(".message-text").textContent, "用户问题");
assert.match(conversation.children[1].querySelector(".message-text").innerHTML, /<h2>回答<\/h2>/);
assert.strictEqual(getElement("#sessionMeta").textContent, "Session session-");

console.log("ok");
