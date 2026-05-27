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

const assistantBubble = context.messageBubble("Assistant", "hello");
context.setMessageUsage(assistantBubble, {
  input_tokens: 123,
  output_tokens: 45,
  total_tokens: 168,
  tokens_per_second: 12.34,
  context_window: 1000,
  context_percent: 16.8,
  source: "api",
});
const usage = assistantBubble.querySelector(".message-usage");

assert.match(usage.textContent, /input 123/);
assert.match(usage.textContent, /output 45/);
assert.match(usage.textContent, /total 168/);
assert.match(usage.textContent, /context 168 \/ 1,000/);
assert.match(usage.textContent, /16\.8%/);
assert.match(usage.textContent, /12\.3 tokens\/s/);
assert.doesNotMatch(usage.textContent, /estimated/);

context.setMessageUsage(assistantBubble, {
  input_tokens: 10,
  output_tokens: 5,
  total_tokens: 15,
  tokens_per_second: 2,
  source: "estimated",
});

assert.match(usage.textContent, /estimated/);

console.log("ok");
