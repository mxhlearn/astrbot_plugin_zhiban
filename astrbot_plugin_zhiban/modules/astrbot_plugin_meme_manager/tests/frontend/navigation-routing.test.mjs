import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(
  new URL("../../pages/app/shared/ui.js", import.meta.url),
  "utf8",
);
const code = source.slice(0, source.indexOf("function subpageForTarget("));
if (!source.includes("function syncModuleRoute(")) {
  throw new Error("shared ui missing syncModuleRoute");
}

class Element {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.parentElement = null;
    this.nodeType = 1;
    this.textContent = "";
    this.className = "";
    this.href = "";
    this.innerHTML = "";
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  getAttribute(name) {
    return this.attributes[name] ?? null;
  }
  removeAttribute(name) {
    delete this.attributes[name];
  }
  addEventListener(name, callback) {
    this.listeners[name] = callback;
  }
  append(...nodes) {
    for (const node of nodes) {
      if (node && typeof node === "object") node.parentElement = this;
      this.children.push(node);
    }
  }
  prepend(...nodes) {
    for (const node of nodes) {
      if (node && typeof node === "object") node.parentElement = this;
      this.children.unshift(node);
    }
  }
  get childNodes() {
    return this.children;
  }
  replaceChildren(...nodes) {
    this.children = nodes;
  }
  querySelector(selector) {
    if (selector === "h1") return this.children.find((n) => n.tagName === "H1") || null;
    if (selector === ".meme-breadcrumb") return this.children.find((n) => n.className === "meme-breadcrumb") || null;
    return null;
  }
}

function fixture({ route, breakBase = false } = {}) {
  const title = new Element("h1");
  title.append(Object.assign(new Element("i"), { nodeType: 1 }));
  title.append({ nodeType: 3, textContent: "表情包管理" });
  const host = new Element();
  host.append(title);
  const header = new Element("header");
  header.className = "page-header";
  header.append(host);
  const nav = new Element("nav");
  nav.className = "nav-actions";
  const documentElement = { dataset: {} };
  const listeners = {};
  const root = route;
  const calls = [];
  const contextHandlers = [];
  const eventListeners = {};
  const location = { href: "about:srcdoc", search: "", origin: "null", hash: "" };
  const document = {
    documentElement,
    activeElement: null,
    querySelector(selector) {
      if (selector === ".page-header > div") return host;
      if (selector === ".nav-actions") return nav;
      return null;
    },
    createElement: (tag) => new Element(tag),
    addEventListener() {},
    body: { prepend() {} },
  };
  const window = {
    ZhibanModule: {
      isEmbedded: true,
      onContext(callback) {
        contextHandlers.push(callback);
      },
      navigate(target) {
        calls.push(target);
        return true;
      },
    },
    addEventListener(name, callback) {
      eventListeners[name] = callback;
    },
  };
  Object.defineProperty(window.ZhibanModule, "route", { get: () => root });
  const sandbox = {
    window,
    document,
    location,
    Node: { TEXT_NODE: 3 },
    URL,
    URLSearchParams,
    console,
    NodeList: Array,
    Set,
    Object,
    String,
    Boolean,
    Error,
    CSS: { escape: String },
    setTimeout,
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(code + "\nwindow.MemeUI = { getRouteQuery, getRouteHash, currentSubpage, pageLabel: currentModuleLabel, updateRoute: syncModuleRoute, navigateTarget: navigateModuleTarget, onRouteChange, isEmbedded: embedded };", context);
  return { context, window, location, root, calls, contextHandlers, eventListeners, host, title, documentElement, breakBase, hostChildren: host.children };
}

test("opaque srcdoc route uses parent metadata, not location", () => {
  const f = fixture({
    route: { path: "settings/index.html", subpage: "settings", hash: "config-group-storage", query: { pack: "x" } },
  });
  assert.equal(JSON.stringify(f.window.MemeUI.getRouteQuery()), JSON.stringify({ pack: "x" }));
  assert.equal(f.window.MemeUI.getRouteHash(), "config-group-storage");
  assert.equal(f.window.MemeUI.currentSubpage(), "settings");
  assert.equal(f.window.MemeUI.isEmbedded, true);
});

test("module navigation targets remain inside known pages and strip credentials", () => {
  const f = fixture({ route: { path: "catalog/index.html", subpage: "catalog" } });
  assert.equal(f.window.MemeUI.updateRoute("catalog/index.html?view=updates&asset_token=secret"), true);
  assert.deepEqual(f.calls, []);
  assert.equal(f.documentElement.dataset.zhibanSubpage, "catalog");
  assert.equal(JSON.stringify({ ...f.root.query }), JSON.stringify({ view: "updates" }));
  assert.equal(f.window.MemeUI.navigateTarget("a_manage/index.html?managed_pack_id=p1"), true);
  assert.equal(JSON.stringify(f.calls), JSON.stringify(["a_manage/index.html?managed_pack_id=p1"]));
  assert.equal(f.window.MemeUI.navigateTarget("../settings/index.html#storage"), true);
  assert.equal(f.calls.at(-1), "settings/index.html#storage");
  assert.equal(f.window.MemeUI.navigateTarget("javascript:alert(1)"), false);
  assert.equal(f.window.MemeUI.navigateTarget("../../outside/index.html"), false);
});

test("parent context updates reach page listeners and refresh breadcrumb", () => {
  const f = fixture({
    route: { path: "a_manage/index.html", subpage: "manage", hash: "", query: {} },
  });
  const changes = [];
  f.window.MemeUI.onRouteChange((route) => changes.push(route));
  Object.assign(f.root, { path: "settings/index.html", subpage: "settings", hash: "config-group-semantic-models", subpageHash: "config-group-semantic-models" });
  f.contextHandlers[0](f.root);
  assert.equal(f.window.MemeUI.currentSubpage(), "settings");
  assert.equal(changes.length, 1);
  assert.equal(changes[0].hash, "config-group-semantic-models");
  assert.equal(f.host.querySelector(".meme-breadcrumb"), null);
  assert.equal(f.window.MemeUI.pageLabel(), "设置中心");
});
