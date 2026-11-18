import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const bridgePath = new URL("../astrbot_plugin_zhiban/views/知伴/host_bridge.js", import.meta.url);

async function createBridge(module = "meme", label = "表情互动") {
  const source = await readFile(bridgePath, "utf8");
  const listeners = new Map();
  const calls = [];
  let sseHandlers;
  let contextHandler;
  let parentContext = { locale: "zh-CN", isDark: false };
  const parent = {
    ready: async () => ({}),
    getContext: () => parentContext,
    onContext: (handler) => { contextHandler = handler; return () => { contextHandler = null; }; },
    apiGet: async (endpoint, params) => {
      calls.push(["get", endpoint, params]);
      return { endpoint, ok: true };
    },
    apiPost: async (endpoint, body) => {
      calls.push(["post", endpoint, body]);
      return { saved: true };
    },
    upload: async (endpoint, file) => ({ uploaded: endpoint, name: file.name }),
    download: async (endpoint) => ({ downloaded: endpoint }),
    subscribeSSE: async (endpoint, handlers) => {
      calls.push(["sse", endpoint]);
      sseHandlers = handlers;
      return "host-subscription";
    },
    unsubscribeSSE: async (id) => calls.push(["unsubscribe", id]),
  };
  const window = {
    location: { origin: "https://astrbot.test" },
    AstrBotPluginView: parent,
    addEventListener: (name, handler) => listeners.set(name, handler),
  };
  class FakeFile {
    constructor(_parts, name, options) {
      this.name = name;
      this.type = options.type;
      this.lastModified = options.lastModified;
    }
  }
  class FakeCustomEvent {
    constructor(type, options) {
      this.type = type;
      this.detail = options?.detail;
      this.cancelable = options?.cancelable === true;
      this.defaultPrevented = false;
    }
    preventDefault() {
      if (this.cancelable) this.defaultPrevented = true;
    }
  }
  vm.runInNewContext(source, {
    window,
    File: FakeFile,
    CustomEvent: FakeCustomEvent,
    Map,
    Promise,
    String,
    Number,
    Error,
    JSON,
    Date,
    URL,
    URLSearchParams,
  });
  const sent = [];
  const events = [];
  const frame = {
    contentWindow: { postMessage: (message, origin) => sent.push({ message, origin }) },
    dataset: {},
    addEventListener: () => {},
    dispatchEvent: (event) => {
      events.push(event);
      return !event.defaultPrevented;
    },
  };
  const detach = window.ZhibanBridge.attachFrame(frame, module, label);
  const message = listeners.get("message");
  const sendFromChild = async (data) => message({
    source: frame.contentWindow,
    origin: window.location.origin,
    data: { channel: "astrbot-plugin-page", ...data },
  });
  const emitContext = (next) => {
    parentContext = { ...parentContext, ...(next || {}) };
    contextHandler?.(parentContext);
  };
  return { window, parent, calls, frame, sent, events, detach, emitContext, sseHandlers: () => sseHandlers, sendFromChild };
}

test("shell broker maps search status to the Anysearch API scope", async () => {
  const bridge = await createBridge("search", "联网搜索");
  await bridge.sendFromChild({ kind: "ready", module: "search" });
  assert.equal(bridge.sent[0].message.context.pluginName, "astrbot_plugin_anysearch");
  await bridge.sendFromChild({ kind: "request", requestId: "search-status", action: "api:get", endpoint: "status", params: {} });
  assert.deepEqual(bridge.calls[0], ["get", "ui/module_api/search/status", {}]);
  assert.equal(bridge.sent.at(-1).message.ok, true);
});

test("shell broker proxies child API requests through the authenticated Zhiban route", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  assert.equal(bridge.sent[0].message.kind, "context");
  assert.equal(bridge.sent[0].origin, "*");
  assert.equal(bridge.sent[0].message.context.pluginName, "meme_manager");
  assert.equal(bridge.frame.dataset.bridgeReady, "true");

  await bridge.sendFromChild({ kind: "request", requestId: "1", action: "api:get", endpoint: "meme_manager/packs", params: {} });
  assert.deepEqual(bridge.calls[0], ["get", "ui/module_api/meme/packs", {}]);
  assert.equal(bridge.sent.at(-1).message.requestId, "1");
  assert.equal(bridge.sent.at(-1).message.ok, true);

  await bridge.sendFromChild({ kind: "request", requestId: "2", action: "api:get", endpoint: "astrbot_plugin_qzone_ultra/page/status" });
  assert.equal(bridge.calls.length, 1);
  assert.equal(bridge.sent.at(-1).message.ok, false);
});

test("shell broker accepts official SDK plugin-relative endpoints and rejects path escapes", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  await bridge.sendFromChild({ kind: "request", requestId: "bare", action: "api:get", endpoint: "packs", params: {} });
  assert.deepEqual(bridge.calls[0], ["get", "ui/module_api/meme/packs", {}]);
  assert.equal(bridge.sent.at(-1).message.ok, true);


  await bridge.sendFromChild({ kind: "request", requestId: "other", action: "api:get", endpoint: "astrbot_plugin_qzone_ultra/page/status" });
  assert.equal(bridge.sent.at(-1).message.ok, false);
  await bridge.sendFromChild({ kind: "request", requestId: "escape", action: "api:get", endpoint: "../status" });
  assert.equal(bridge.sent.at(-1).message.ok, false);
  assert.equal(bridge.calls.length, 1);
});

test("shell broker never forwards a child request for an AstrBot asset token", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  await bridge.sendFromChild({ kind: "request", requestId: "token", action: "api:get", endpoint: "bridge/auth_token" });
  assert.equal(bridge.sent.at(-1).message.data.token, "");
  assert.equal(bridge.calls.length, 0);
});

test("shell API endpoints stay plugin-relative for AstrBot's SDK prefix", async () => {
  const bridge = await createBridge();
  const getResult = await bridge.window.ZhibanBridge.apiGet("ui/status");
  assert.deepEqual(bridge.calls[0], ["get", "ui/status", undefined]);
  assert.equal(
    `/api/v1/plugins/extensions/astrbot_plugin_zhiban/${getResult.endpoint}`,
    "/api/v1/plugins/extensions/astrbot_plugin_zhiban/ui/status",
  );

  const postBody = { revision: "r1", enabled: true, changes: {}, clear_secrets: [] };
  await bridge.window.ZhibanBridge.apiPost("ui/config/heart", postBody);
  assert.deepEqual(bridge.calls[1], ["post", "ui/config/heart", postBody]);

  await assert.rejects(
    bridge.window.ZhibanBridge.apiGet("astrbot_plugin_zhiban/ui/status"),
    /Invalid 知伴 API endpoint/,
  );
  assert.equal(bridge.calls.length, 2);
});

test("shell broker preserves upload, download and SSE lifecycle", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  await bridge.sendFromChild({ kind: "request", requestId: "u", action: "files:upload", endpoint: "meme_manager/emoji/a", fileName: "a.png", fileType: "image/png", fileLastModified: 10, fileBuffer: new ArrayBuffer(4) });
  assert.equal(bridge.sent.at(-1).message.data.name, "a.png");

  await bridge.sendFromChild({ kind: "request", requestId: "d", action: "files:download", endpoint: "meme_manager/packs/export", filename: "pack.zip" });
  assert.deepEqual(bridge.sent.at(-1).message.data, { downloaded: "ui/module_api/meme/packs/export" });

  await bridge.sendFromChild({ kind: "request", requestId: "s", action: "sse:subscribe", endpoint: "meme_manager/sync/status", subscriptionId: "child-1" });
  assert.equal(bridge.sent.at(-1).message.data.subscriptionId, "child-1");
  bridge.sseHandlers().onOpen();
  bridge.sseHandlers().onMessage({ raw: "{\"n\":1}", eventType: "message", lastEventId: "e1" });
  assert.equal(bridge.sent.at(-2).message.state, "open");
  assert.equal(bridge.sent.at(-1).message.data, "{\"n\":1}");

  await bridge.sendFromChild({ kind: "request", requestId: "x", action: "sse:unsubscribe", subscriptionId: "child-1" });
  assert.deepEqual(bridge.calls.at(-1), ["unsubscribe", "host-subscription"]);
});

test("parent theme changes are broadcast to the active module frame", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  bridge.sent.length = 0;
  bridge.emitContext({ isDark: true });
  assert.equal(bridge.sent.at(-1).message.kind, "context");
  assert.equal(bridge.sent.at(-1).message.context.isDark, true);
  assert.equal(bridge.sent.at(-1).origin, "*");
  bridge.emitContext({ isDark: false });
  assert.equal(bridge.sent.at(-1).message.context.isDark, false);
});

test("shell distinguishes bridge readiness, app mount and sanitized app errors", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  assert.equal(bridge.frame.dataset.bridgeReady, "true");
  assert.equal(bridge.frame.dataset.appReady, "false");
  const token = bridge.sent[0].message.context.appReadyToken;
  assert.ok(token);
  assert.deepEqual(bridge.events.map((event) => event.type), ["zhiban:bridge-ready"]);

  await bridge.sendFromChild({ kind: "app:ready", module: "meme", token: "wrong-token" });
  assert.equal(bridge.frame.dataset.appReady, "false");
  assert.equal(bridge.events.length, 1);

  await bridge.sendFromChild({ kind: "app:ready", module: "meme", token });
  assert.equal(bridge.frame.dataset.appReady, "true");
  assert.deepEqual(bridge.events.map((event) => event.type), ["zhiban:bridge-ready", "zhiban:app-ready"]);

  await bridge.sendFromChild({
    kind: "app:error",
    module: "meme",
    token,
    stage: "界面挂载",
    message: "asset_token=secret-token Bearer abc sk-1234567890 failed",
  });
  const errorEvent = bridge.events.at(-1);
  assert.equal(errorEvent.type, "zhiban:app-error");
  assert.equal(errorEvent.detail.stage, "界面挂载");
  assert.match(errorEvent.detail.message, /asset_token=\*\*\*/);
  assert.doesNotMatch(errorEvent.detail.message, /secret-token|abc|1234567890/);
});

test("child navigation is limited to registered module subpages", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  const token = bridge.sent[0].message.context.appReadyToken;
  bridge.sent.length = 0;
  await bridge.sendFromChild({
    kind: "navigate",
    module: "meme",
    token,
    path: "catalog/index.html?view=official",
    hash: "featured",
    query: { view: "official" },
  });
  const accepted = bridge.events.at(-1);
  assert.equal(accepted.type, "zhiban:navigate");
  assert.equal(accepted.detail.path, "catalog/index.html");
  assert.equal(accepted.detail.hash, "featured");
  assert.equal(JSON.stringify(accepted.detail.query), JSON.stringify({ view: "official" }));
  assert.equal(bridge.frame.dataset.subpage, "catalog/index.html");
  assert.equal(bridge.sent.at(-1).message.kind, "context");
  assert.equal(bridge.sent.at(-1).message.context.subpage, "catalog/index.html");

  await bridge.sendFromChild({
    kind: "navigate",
    module: "meme",
    token,
    path: "settings/../../api/status",
  });
  assert.equal(bridge.sent.at(-1).message.kind, "navigation:error");
  assert.equal(bridge.sent.at(-1).message.stage, "导航");

  await bridge.sendFromChild({
    kind: "navigate",
    module: "meme",
    token,
    path: "unregistered/index.html",
  });
  assert.equal(bridge.sent.at(-1).message.kind, "navigation:error");
  assert.equal(bridge.frame.dataset.subpage, "catalog/index.html");
});

test("child navigation accepts and canonicalizes a same-origin signed module URL", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  const token = bridge.sent[0].message.context.appReadyToken;
  bridge.events.length = 0;
  await bridge.sendFromChild({
    kind: "navigate",
    module: "meme",
    token,
    path: "https://astrbot.test/api/v1/plugins/astrbot_plugin_zhiban/views/%E7%9F%A5%E4%BC%B4/_t/header.payload.signature/modules/meme/catalog/index.html?view=catalog&asset_token=header.payload.signature&embedded=frame&theme=dark#official",
  });
  const accepted = bridge.events.at(-1);
  assert.equal(accepted.type, "zhiban:navigate");
  assert.equal(accepted.detail.path, "catalog/index.html");
  assert.equal(accepted.detail.hash, "official");
  assert.equal(JSON.stringify(accepted.detail.query), JSON.stringify({ view: "catalog" }));
  assert.equal(bridge.frame.dataset.subpage, "catalog/index.html");
  assert.equal(JSON.stringify(bridge.sent.at(-1).message).includes("header.payload.signature"), false);
});

test("child navigation rejects foreign origins and encoded path traversal", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  const token = bridge.sent[0].message.context.appReadyToken;
  bridge.events.length = 0;

  await bridge.sendFromChild({
    kind: "navigate",
    module: "meme",
    token,
    path: "https://evil.test/api/v1/plugins/astrbot_plugin_zhiban/views/x/_t/t/modules/meme/catalog/index.html",
  });
  assert.equal(bridge.sent.at(-1).message.kind, "navigation:error");
  assert.equal(bridge.sent.at(-1).message.stage, "导航");

  await bridge.sendFromChild({
    kind: "navigate",
    module: "meme",
    token,
    path: "https://astrbot.test/api/v1/plugins/astrbot_plugin_zhiban/views/x/_t/t/modules/meme/settings/%2e%2e/catalog/index.html",
  });
  assert.equal(bridge.sent.at(-1).message.kind, "navigation:error");
  assert.equal(bridge.events.length, 0);
});

test("instance messages require the exact parent-issued token", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  const token = bridge.sent[0].message.context.appReadyToken;
  bridge.events.length = 0;

  await bridge.sendFromChild({ kind: "app:ready", module: "meme" });
  assert.equal(bridge.frame.dataset.appReady, "false");
  await bridge.sendFromChild({ kind: "app:error", module: "meme", stage: "runtime", message: "missing token" });
  assert.equal(bridge.events.length, 0);

  await bridge.sendFromChild({ kind: "app:ready", module: "meme", token });
  assert.deepEqual(bridge.events.map((event) => event.type), ["zhiban:app-ready"]);
});

test("requests wait for the bridge handshake and stay module scoped", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "request", requestId: "early", action: "api:get", endpoint: "packs" });
  assert.equal(bridge.calls.length, 0);
  assert.equal(bridge.sent.length, 0);
  await bridge.sendFromChild({ kind: "request", requestId: "other", action: "api:get", endpoint: "packs" });
  assert.equal(bridge.calls.length, 0);
});

test("child navigation from another module is ignored", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  bridge.events.length = 0;
  await bridge.sendFromChild({
    kind: "navigate",
    module: "qzone",
    token: bridge.sent[0].message.context.appReadyToken,
    path: "catalog/index.html",
  });
  assert.equal(bridge.events.length, 0);
  assert.equal(bridge.frame.dataset.subpage, "");
});

test("detached frames ignore late handshakes and app errors", async () => {
  const bridge = await createBridge();
  bridge.detach();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  await bridge.sendFromChild({ kind: "app:error", module: "meme", stage: "界面挂载", message: "late" });
  assert.equal(bridge.sent.length, 0);
  assert.equal(bridge.events.length, 0);
});

test("late SSE subscribe is cancelled when the frame detaches", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  const token = bridge.sent[0].message.context.appReadyToken;
  bridge.sent.length = 0;
  let resolveSubscribe;
  const callsForLateSse = bridge.calls;
  bridge.parent.subscribeSSE = (endpoint, handlers, params) => {
    callsForLateSse.push(["sse", endpoint]);
    return new Promise((resolve) => { resolveSubscribe = resolve; });
  };
  bridge.parent.unsubscribeSSE = async (id) => bridge.calls.push(["unsubscribe", id]);
  const pending = bridge.sendFromChild({
    kind: "request",
    requestId: "sse-late",
    token,
    action: "sse:subscribe",
    endpoint: "packs/stream",
    subscriptionId: "late-child",
    params: {},
  });
  bridge.detach();
  await new Promise((resolve) => setImmediate(resolve));
  if (typeof resolveSubscribe !== "function") {
    assert.ok(bridge.calls.some((call) => call[0] === "unsubscribe"));
    return;
  }
  resolveSubscribe("late-sub");
  await pending;
  assert.deepEqual(bridge.calls.at(-1), ["unsubscribe", "late-sub"]);
});

test("detached frames ignore late navigation", async () => {
  const bridge = await createBridge();
  await bridge.sendFromChild({ kind: "ready", module: "meme" });
  const token = bridge.sent[0].message.context.appReadyToken;
  bridge.detach();
  bridge.events.length = 0;
  await bridge.sendFromChild({ kind: "navigate", module: "meme", token, path: "catalog/index.html" });
  assert.equal(bridge.events.length, 0);
});
