import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const bridgePath = new URL("../astrbot_plugin_zhiban/views/知伴/module_bridge.js", import.meta.url);
const CHANNEL = "astrbot-plugin-page";

async function createBridge(moduleKey = "meme", { withSdk = false } = {}) {
  const source = await readFile(bridgePath, "utf8");
  const calls = [];
  const original = withSdk ? {
    ready: async () => ({}),
    getContext: () => ({ pluginName: "astrbot_plugin_zhiban", locale: "zh-CN" }),
    getI18n: () => ({}),
    apiGet: async (endpoint, params) => { calls.push(["get", endpoint, params]); return { data: endpoint }; },
    apiPost: async (endpoint, body) => { calls.push(["post", endpoint, body]); return { saved: true }; },
    upload: async (endpoint, file) => { calls.push(["upload", endpoint, file]); return { uploaded: true }; },
    download: async (endpoint, params, filename) => { calls.push(["download", endpoint, params, filename]); return { downloaded: true }; },
    subscribeSSE: async (endpoint, handlers, params) => { calls.push(["sse", endpoint, handlers, params]); return "sub-1"; },
    unsubscribeSSE: async (id) => calls.push(["unsubscribe", id]),
    onContext: () => () => {},
  } : null;
  const listeners = new Map();
  const posts = [];
  const window = {
    AstrBotPluginView: original,
    AstrBotPluginPage: original,
    location: { href: "about:srcdoc", origin: "null" },
    parent: { postMessage: (message, origin) => posts.push({ message, origin }) },
    addEventListener: (name, listener) => listeners.set(name, listener),
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
  };
  const document = {
    currentScript: {
      dataset: { moduleKey },
      src: "http://127.0.0.1/views/知伴/_t/token/module_bridge.js",
    },
    readyState: "loading",
    documentElement: { dataset: { zhibanEmbedded: "true", zhibanHostFrame: "true" } },
    getElementById: () => null,
    head: { append() {} },
    createElement: (tagName) => ({ tagName, textContent: "" }),
    addEventListener: (name, listener) => listeners.set(name, listener),
    querySelector: () => null,
    body: null,
  };
  vm.runInNewContext(source, {
    window,
    document,
    URL,
    URLSearchParams,
    location: window.location,
    Map,
    Set,
    Object,
    Array,
    String,
    Number,
    Boolean,
    JSON,
    Promise,
    Error,
    console,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
  });
  const message = listeners.get("message");
  const sendFromHost = (data) => message({ source: window.parent, data: { channel: CHANNEL, ...data } });
  return { bridge: window.AstrBotPluginView, calls, listeners, posts, sendFromHost };
}

async function answerReady(bridge, token = "tok-1") {
  const ready = bridge.bridge.ready();
  const readyPost = bridge.posts.find((item) => item.message.kind === "ready");
  assert.ok(readyPost, "module should announce bridge readiness");
  bridge.sendFromHost({
    kind: "context",
    context: { pluginName: "astrbot_plugin_meme_manager", pageTitle: "表情互动", locale: "zh-CN", appReadyToken: token },
  });
  return { context: await ready, readyPost };
}

async function request(bridge, invoke, expectedAction) {
  const pending = invoke();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const post = bridge.posts.at(-1);
  assert.equal(post.message.kind, "request");
  assert.equal(post.message.action, expectedAction);
  bridge.sendFromHost({ kind: "response", requestId: post.message.requestId, ok: true, data: { action: expectedAction } });
  return pending;
}

test("sandboxed module gets a self-contained bridge without the official SDK", async () => {
  const bridge = await createBridge("meme");
  const { context, readyPost } = await answerReady(bridge);
  assert.equal(readyPost.origin, "*");
  assert.equal(readyPost.message.module, "meme");
  assert.equal(context.pluginName, "meme_manager");
  assert.equal(context.pageTitle, "表情互动");
  assert.equal(bridge.bridge.getLocale(), "zh-CN");
  assert.equal(bridge.calls.length, 0);
});

test("host transport keeps API, upload, download and SSE inside the module scope", async () => {
  const bridge = await createBridge("qzone");
  await answerReady(bridge);

  assert.deepEqual(
    await request(bridge, () => bridge.bridge.apiGet("astrbot_plugin_qzone_ultra/page/status", { limit: 2 }), "api:get"),
    { action: "api:get" },
  );
  assert.equal(bridge.posts.at(-1).message.endpoint, "page/status");
  assert.deepEqual(bridge.posts.at(-1).message.params, { limit: 2 });

  assert.deepEqual(await request(bridge, () => bridge.bridge.apiPost("page/publish", { text: "draft" }), "api:post"), { action: "api:post" });
  assert.deepEqual(bridge.posts.at(-1).message.body, { text: "draft" });

  const file = {
    name: "photo.jpg",
    type: "image/jpeg",
    lastModified: 10,
    arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
  };
  assert.deepEqual(await request(bridge, () => bridge.bridge.upload("photo/upload", file), "files:upload"), { action: "files:upload" });
  assert.equal(bridge.posts.at(-1).message.fileName, "photo.jpg");
  assert.equal(bridge.posts.at(-1).message.fileBuffer.byteLength, 3);

  assert.deepEqual(await request(bridge, () => bridge.bridge.download("page/export", { id: 3 }, "page.zip"), "files:download"), { action: "files:download" });
  assert.equal(bridge.posts.at(-1).message.filename, "page.zip");

  const sse = bridge.bridge.subscribeSSE("page/status", { onOpen() {}, onMessage() {} }, { id: 3 });
  const ssePost = bridge.posts.at(-1);
  assert.equal(ssePost.message.action, "sse:subscribe");
  bridge.sendFromHost({ kind: "response", requestId: ssePost.message.requestId, ok: true, data: { subscriptionId: ssePost.message.subscriptionId } });
  const subscriptionId = await sse;
  assert.equal(subscriptionId, ssePost.message.subscriptionId);
  await request(bridge, () => bridge.bridge.unsubscribeSSE(subscriptionId), "sse:unsubscribe");
});

test("module scope rejects cross-module and escaping endpoints before posting", async () => {
  const bridge = await createBridge("meme");
  await answerReady(bridge);
  assert.equal((await bridge.bridge.apiGet("bridge/auth_token")).token, "");
  assert.throws(() => bridge.bridge.apiGet("../status"), /模块 API 路径无效/);
  assert.throws(() => bridge.bridge.apiGet("astrbot_plugin_qzone_ultra/page/status"), /模块 API 范围不匹配/);
  assert.equal(bridge.posts.filter((item) => item.message.kind === "request").length, 0);
});

test("direct pages keep using the official SDK when they are not embedded", async () => {
  const bridge = await createBridge("meme", { withSdk: true });
  // Re-run the same source in a non-embedded document.
  const source = await readFile(bridgePath, "utf8");
  const listeners = new Map();
  const calls = [];
  const original = {
    ready: async () => ({}),
    getContext: () => ({ locale: "zh-CN" }),
    apiGet: async (endpoint, params) => { calls.push(["get", endpoint, params]); return { data: endpoint }; },
    apiPost: async (endpoint, body) => { calls.push(["post", endpoint, body]); return { saved: true }; },
    upload: async () => ({}),
    download: async () => ({}),
    subscribeSSE: async () => "sub-1",
    unsubscribeSSE: async () => {},
    onContext: () => () => {},
  };
  const window = {
    AstrBotPluginView: original,
    AstrBotPluginPage: original,
    location: { href: "http://127.0.0.1/modules/meme/index.html", origin: "http://127.0.0.1" },
    parent: {},
    addEventListener: (name, listener) => listeners.set(name, listener),
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
  };
  const document = {
    currentScript: { dataset: { moduleKey: "meme" }, src: "http://127.0.0.1/module_bridge.js" },
    readyState: "loading",
    documentElement: { dataset: {} },
    getElementById: () => null,
    head: { append() {} },
    createElement: (tagName) => ({ tagName, textContent: "" }),
    addEventListener: (name, listener) => listeners.set(name, listener),
    querySelector: () => null,
    body: null,
  };
  vm.runInNewContext(source, {
    window, document, URL, URLSearchParams, location: window.location,
    Map, Set, Object, Array, String, Number, Boolean, JSON, Promise, Error, console,
    setTimeout, clearTimeout, setInterval, clearInterval,
  });
  assert.deepEqual(await window.AstrBotPluginPage.apiGet("meme_manager/packs", { page: 1 }), { data: "ui/module_api/meme/packs" });
  assert.deepEqual(calls[0], ["get", "ui/module_api/meme/packs", { page: 1 }]);
});
