import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const bridgePath = new URL("../astrbot_plugin_zhiban/views/知伴/module_bridge.js", import.meta.url);
const CHANNEL = "astrbot-plugin-page";

async function createBridge(moduleKey = "meme", { withSdk = false, route = {}, bridgeSrc = "http://127.0.0.1/views/知伴/_t/token/module_bridge.js" } = {}) {
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
    __zhibanRoute: route,
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
      src: bridgeSrc,
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
  return {
    bridge: window.AstrBotPluginView,
    calls,
    listeners,
    posts,
    sendFromHost,
    root: document.documentElement,
    window,
    document,
    rootBase: new URL("http://127.0.0.1/views/知伴/_t/token/", "http://127.0.0.1/"),
  };
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

test("search module bridge maps status to the Anysearch module API scope", async () => {
  const bridge = await createBridge("search");
  const { context } = await answerReady(bridge);
  assert.equal(context.pluginName, "astrbot_plugin_anysearch");
  const pending = bridge.bridge.apiGet("status", {});
  await new Promise((resolve) => setTimeout(resolve, 0));
  const post = bridge.posts.at(-1);
  assert.equal(post.message.action, "api:get");
  assert.equal(post.message.endpoint, "status");
  bridge.sendFromHost({ kind: "response", requestId: post.message.requestId, ok: true, data: { configured: false } });
  assert.deepEqual(await pending, { configured: false });
});

test("host context applies the shared dark palette before module mount", async () => {
  const bridge = await createBridge("memory");
  const ready = bridge.bridge.ready();
  bridge.sendFromHost({
    kind: "context",
    context: { pluginName: "astrbot_plugin_livingmemory", pageTitle: "记忆成长", locale: "zh-CN", isDark: true },
  });
  await ready;
  assert.equal(bridge.root.dataset.theme, "dark");
  bridge.sendFromHost({
    kind: "context",
    context: { pluginName: "astrbot_plugin_livingmemory", pageTitle: "记忆成长", locale: "zh-CN", isDark: false },
  });
  assert.equal(bridge.root.dataset.theme, "light");
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

test("embedded module exposes scoped navigation without enabling general URL transport", async () => {
  const bridge = await createBridge("meme");
  await answerReady(bridge, "instance-token");
  assert.equal(bridge.bridge.isEmbedded, undefined);
  assert.equal(bridge.bridge.route, undefined);
  assert.equal(typeof bridge.bridge.apiGet, "function");
  assert.equal(typeof bridge.bridge.apiPost, "function");
  assert.equal(bridge.bridge.apiGet.length >= 1, true);

});

test("embedded module exposes onContext and replays the current route", async () => {
  const bridge = await createBridge("meme", {
    route: { path: "settings/index.html", subpage: "settings", hash: "models", subpageHash: "models", query: { view: "advanced" } },
  });
  await answerReady(bridge, "instance-token");
  const seen = [];
  const unsubscribe = bridge.window.ZhibanModule.onContext((context) => seen.push(context));
  assert.equal(seen.length, 1);
  assert.equal(seen[0].subpage, "settings");
  assert.equal(seen[0].hash, "models");
  assert.equal(seen[0].subpageHash, "models");
  assert.equal(JSON.stringify(seen[0].query), JSON.stringify({ view: "advanced" }));
  unsubscribe();
});

test("child navigation carries the parent-issued instance token", async () => {
  const bridge = await createBridge("meme");
  await answerReady(bridge, "instance-token");
  bridge.root.dataset.appReadyToken = "instance-token";
  const moduleApi = bridge.window.ZhibanModule;
  assert.equal(moduleApi.navigate("catalog/index.html?view=official#featured"), true);
  const post = bridge.posts.at(-1);
  assert.equal(post.message.kind, "navigate");
  assert.equal(post.message.path, "catalog/index.html");
  assert.equal(post.message.hash, "featured");
  assert.equal(post.message.query.view, "official");
  assert.equal(post.message.token, "instance-token");
});

test("hash-only navigation keeps the current module path", async () => {
  const bridge = await createBridge("meme");
  await answerReady(bridge, "instance-token");
  bridge.root.dataset.appReadyToken = "instance-token";
  assert.equal(bridge.window.ZhibanModule.navigate("#config-group-semantic-models"), true);
  const post = bridge.posts.at(-1);
  assert.equal(post.message.path, "index.html");
  assert.equal(post.message.hash, "config-group-semantic-models");
  assert.equal(post.message.token, "instance-token");
});

test("signed srcdoc URLs and real top/empty-state targets normalize to module paths", async () => {
  const signedRoot = "https://astrbot.test/api/v1/plugins/astrbot_plugin_zhiban/views/%E7%9F%A5%E4%BC%B4/_t/header.payload.signature/";
  const bridge = await createBridge("meme", {
    route: { path: "semantic/index.html", subpage: "semantic", hash: "", query: {} },
    bridgeSrc: `${signedRoot}module_bridge.js`,
  });
  await answerReady(bridge, "instance-token");
  bridge.root.dataset.appReadyToken = "instance-token";
  const api = bridge.window.ZhibanModule;

  const signed = `${signedRoot}modules/meme/settings/index.html?asset_token=header.payload.signature&embedded=frame&view=deep#config-group-semantic-models`;
  assert.equal(api.navigate(signed), true);
  let post = bridge.posts.at(-1);
  assert.equal(post.message.kind, "navigate");
  assert.equal(post.message.path, "settings/index.html");
  assert.equal(post.message.hash, "config-group-semantic-models");
  assert.equal(JSON.stringify(post.message.query), JSON.stringify({ view: "deep" }));
  assert.equal(post.message.token, "instance-token");
  assert.equal(JSON.stringify(post.message).includes("header.payload.signature"), false);

  assert.equal(api.navigate("../settings/index.html#config-group-semantic-models"), true);
  post = bridge.posts.at(-1);
  assert.equal(post.message.path, "settings/index.html");
  assert.equal(post.message.hash, "config-group-semantic-models");

  assert.equal(api.navigate("catalog/index.html?view=catalog"), true);
  post = bridge.posts.at(-1);
  assert.equal(post.message.path, "catalog/index.html");
  assert.equal(JSON.stringify(post.message.query), JSON.stringify({ view: "catalog" }));

  assert.equal(api.navigate(`${signedRoot}modules/qzone/index.html`), false);
  assert.equal(api.navigate(`${signedRoot}modules/meme/settings/../catalog/index.html`), false);
  assert.equal(api.navigate(`${signedRoot}modules/meme/settings/%2e%2e/catalog/index.html`), false);
  assert.equal(bridge.posts.at(-1).message.kind, "navigate");
});
