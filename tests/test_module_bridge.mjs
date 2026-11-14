import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const bridgePath = new URL("../astrbot_plugin_zhiban/views/知伴/module_bridge.js", import.meta.url);

async function createBridge(moduleKey = "meme") {
  const source = await readFile(bridgePath, "utf8");
  const calls = [];
  const original = {
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
  };
  const listeners = new Map();
  const window = { AstrBotPluginView: original, AstrBotPluginPage: original, location: { href: "http://127.0.0.1/views/知伴/_t/token/modules/meme/index.html" } };
  const document = {
    currentScript: {
      dataset: { moduleKey },
      src: "http://127.0.0.1/views/知伴/_t/token/module_bridge.js",
    },
    readyState: "loading",
    head: { append() {} },
    createElement: (tagName) => ({ tagName, textContent: "" }),
    addEventListener: (name, listener) => listeners.set(name, listener),
  };
  vm.runInNewContext(source, { window, document, URL, Map, Object, String, Promise, Error, Number });
  return { bridge: window.AstrBotPluginView, calls, listeners };
}

test("direct page adapter routes APIs through the selected module", async () => {
  const { bridge, calls } = await createBridge("meme");
  assert.equal((await bridge.ready()).pluginName, "meme_manager");
  assert.equal(bridge.getContext().pageTitle, "表情互动");
  assert.deepEqual(await bridge.apiGet("meme_manager/packs", { page: 1 }), { data: "ui/module_api/meme/packs" });
  assert.deepEqual(calls[0], ["get", "ui/module_api/meme/packs", { page: 1 }]);
  assert.equal((await bridge.apiGet("bridge/auth_token")).token, "");
  assert.equal(calls.length, 1);
  assert.throws(() => bridge.apiGet("../status"), /模块 API 路径无效/);
  assert.throws(() => bridge.apiGet("astrbot_plugin_qzone_ultra/page/status"), /模块 API 范围不匹配/);
  assert.equal(calls.length, 1);
});

test("direct page adapter preserves post, upload, download and SSE calls", async () => {
  const { bridge, calls } = await createBridge("qzone");
  await bridge.apiPost("page/publish", { text: "draft" });
  await bridge.upload("photo/upload", { name: "photo.jpg" });
  await bridge.download("page/export", { id: 3 }, "page.zip");
  await bridge.subscribeSSE("page/status", { onOpen() {} }, { id: 3 });
  await bridge.unsubscribeSSE("sub-1");
  assert.deepEqual(calls.map((call) => call.slice(0, 2)), [
    ["post", "ui/module_api/qzone/page/publish"],
    ["upload", "ui/module_api/qzone/photo/upload"],
    ["download", "ui/module_api/qzone/page/export"],
    ["sse", "ui/module_api/qzone/page/status"],
    ["unsubscribe", "sub-1"],
  ]);
});
