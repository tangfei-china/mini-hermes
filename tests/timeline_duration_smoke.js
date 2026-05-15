const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert");

class FakeClassList {
  toggle() {}
  add() {}
}

const appended = [];

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
    appended.push(child);
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

assert.strictEqual(context.formatDuration(43), "43ms");
assert.strictEqual(context.formatDuration(1250), "1.3s");
assert.strictEqual(context.formatDuration(65000), "1m 5s");
assert.strictEqual(context.formatDuration(undefined), "—");

vm.runInContext(
  "events = [{ step: 1, type: 'model_response', duration_ms: 1250, offset_ms: 42, data: { iteration: 1 } }]; renderTimeline();",
  context
);

const renderedTimeline = appended.map((item) => item.innerHTML).join("\n");
assert.match(renderedTimeline, /class="time-label">start<\/span>/);
assert.match(renderedTimeline, /class="time-value">\+42ms<\/span>/);
assert.match(renderedTimeline, /class="time-label">took<\/span>/);
assert.match(renderedTimeline, /class="time-value">1\.3s<\/span>/);

appended.length = 0;
vm.runInContext(
  "events = [{ step: 1, type: 'user_message', data: {} }]; renderTimeline();",
  context
);
const missingTimingTimeline = appended.map((item) => item.innerHTML).join("\n");
assert.match(missingTimingTimeline, /class="time-value">—<\/span>/);
assert.doesNotMatch(missingTimingTimeline, />0ms</);

console.log("ok");
