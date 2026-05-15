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
    return child;
  }

  insertBefore(child) {
    this.children.push(child);
    return child;
  }

  addEventListener(type, listener) {
    this.eventListeners[type] = listener;
  }

  setAttribute() {}
}

const elements = new Map();
function getElement(selector) {
  if (!elements.has(selector)) elements.set(selector, new FakeElement());
  return elements.get(selector);
}

const appJs = fs.readFileSync(path.join(__dirname, "..", "mini_hermes", "static", "app.js"), "utf8");
const context = {
  console,
  crypto: { randomUUID: () => "unit-test-session" },
  localStorage: { getItem: () => null, setItem: () => {} },
  document: {
    querySelector: getElement,
    createElement: (tagName) => new FakeElement(tagName),
  },
  fetch: () => Promise.resolve({ json: () => Promise.resolve({ skills: [] }) }),
  URLSearchParams,
  EventSource: function EventSource() {},
  performance: { now: () => 0 },
  confirm: () => true,
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(appJs, context, { filename: "app.js" });

const assistantBubble = context.messageBubble(
  "Assistant",
  "## 系统信息\n\n你当前的系统是：\n\n- **操作系统**：macOS\n- `Build`：25D125"
);
const assistantText = assistantBubble.querySelector(".message-text");

assert.match(assistantText.innerHTML, /<h2>系统信息<\/h2>/);
assert.match(assistantText.innerHTML, /<ul>/);
assert.match(assistantText.innerHTML, /<strong>操作系统<\/strong>/);
assert.match(assistantText.innerHTML, /<code>Build<\/code>/);

const userBubble = context.messageBubble("You", "**不要渲染** <script>alert(1)</script>");
const userText = userBubble.querySelector(".message-text");

assert.strictEqual(userText.textContent, "**不要渲染** <script>alert(1)</script>");
assert.strictEqual(userText.innerHTML, "");

console.log("ok");
