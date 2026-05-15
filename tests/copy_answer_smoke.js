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

let copiedText = "";
const timeoutCallbacks = [];
const appJs = fs.readFileSync(path.join(__dirname, "..", "mini_hermes", "static", "app.js"), "utf8");
const context = {
  console,
  crypto: { randomUUID: () => "unit-test-session" },
  localStorage: { getItem: () => null, setItem: () => {} },
  document: {
    querySelector: getElement,
    createElement: (tagName) => new FakeElement(tagName),
  },
  navigator: {
    clipboard: {
      writeText: async (text) => {
        copiedText = text;
      },
    },
  },
  setTimeout: (callback) => {
    timeoutCallbacks.push(callback);
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

const assistantBubble = context.messageBubble("Assistant", "");
const assistantText = assistantBubble.querySelector(".message-text");
context.setMessageText(assistantText, "## 标题\n\n- **重点**", true);
context.setCopyButton(assistantBubble, "## 标题\n\n- **重点**");

const copyButton = assistantBubble.querySelector(".message-copy");
assert.strictEqual(copyButton.hidden, false);
assert.strictEqual(copyButton.textContent, "Copy");

copyButton.onclick();

setImmediate(() => {
  assert.strictEqual(copiedText, "## 标题\n\n- **重点**");
  assert.strictEqual(copyButton.textContent, "Copied");
  assert.strictEqual(timeoutCallbacks.length, 1);
  console.log("ok");
});
