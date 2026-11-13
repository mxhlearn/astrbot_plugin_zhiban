(() => {
  const CHANNEL = "astrbot-plugin-page";
  const APP_PLUGIN_NAME = "astrbot_plugin_zhiban";
  const MODULE_API_NAMES = {
    heart: "astrbot_plugin_angel_heart",
    memory: "astrbot_plugin_livingmemory",
    meme: "meme_manager",
    tts: "astrbot_plugin_breeze_tts",
    brush: "astrbot_plugin_angel_brush",
    music: "astrbot_plugin_listen_music",
    eye: "astrbot_plugin_angel_eye",
    qzone: "astrbot_plugin_qzone_ultra",
    filter: "astrbot_plugin_link_filter",
  };
  const frames = new Map();
  const bridge = () => window.AstrBotPluginView || window.AstrBotPluginPage;

  function appEndpoint(path) {
    const value = String(path || "").replace(/^\/+/, "");
    if (!value || value.includes("\\") || value.includes("://") || value.includes("?") || value.includes("#") ||
        value.split("/").some((part) => !part || part === "." || part === "..")) {
      throw new Error("Invalid 知伴 API endpoint.");
    }
    if (value === APP_PLUGIN_NAME || value.startsWith(`${APP_PLUGIN_NAME}/`)) {
      throw new Error("Invalid 知伴 API endpoint: use a plugin-relative path.");
    }
    return value;
  }

  function moduleProxyEndpoint(moduleKey, endpoint) {
    assertModuleEndpoint(moduleKey, endpoint);
    const prefix = `${MODULE_API_NAMES[moduleKey]}/`;
    const path = endpoint.slice(prefix.length);
    return `ui/module_api/${moduleKey}/${path}`;
  }

  function childFrame(source) {
    for (const [frame, state] of frames) {
      if (frame.contentWindow === source) return { frame, state };
    }
    return null;
  }

  function post(frame, message) {
    if (!frame?.contentWindow) return;
    const origin = window.location.origin;
    frame.contentWindow.postMessage(message, origin === "null" ? "*" : origin);
  }

  function sendResponse(frame, requestId, data) {
    post(frame, { channel: CHANNEL, kind: "response", requestId, ok: true, data });
  }

  function sendError(frame, requestId, error) {
    const message = typeof error?.message === "string" ? error.message.slice(0, 240) : "请求失败";
    post(frame, { channel: CHANNEL, kind: "response", requestId, ok: false, error: message });
  }

  function assertModuleEndpoint(moduleKey, endpoint) {
    const prefix = `${MODULE_API_NAMES[moduleKey]}/`;
    if (!MODULE_API_NAMES[moduleKey] || typeof endpoint !== "string" || !endpoint.startsWith(prefix)) {
      throw new Error("模块 API 范围不匹配");
    }
  }

  async function handleRequest(frame, state, message) {
    const api = bridge();
    if (!api) throw new Error("AstrBot 已登录页面桥接尚未就绪");
    if (typeof api.ready === "function") await api.ready();
    const payload = message.payload || message;
    const endpoint = payload.endpoint;
    const proxyEndpoint = message.action === "sse:unsubscribe"
      ? null
      : moduleProxyEndpoint(state.module, endpoint);

    switch (message.action) {
      case "api:get":
        return api.apiGet(proxyEndpoint, payload.params);
      case "api:post":
        return api.apiPost(proxyEndpoint, payload.body);
      case "files:upload": {
        if (typeof api.upload !== "function") throw new Error("当前 AstrBot 不支持上传桥接");
        const file = new File([payload.fileBuffer], payload.fileName || "upload.bin", {
          type: payload.fileType || "application/octet-stream",
          lastModified: Number(payload.fileLastModified) || Date.now(),
        });
        return api.upload(proxyEndpoint, file);
      }
      case "files:download":
        if (typeof api.download !== "function") throw new Error("当前 AstrBot 不支持下载桥接");
        return api.download(proxyEndpoint, payload.params, payload.filename);
      case "sse:subscribe": {
        if (typeof api.subscribeSSE !== "function") throw new Error("当前 AstrBot 不支持实时事件桥接");
        assertModuleEndpoint(state.module, endpoint);
        const childId = String(payload.subscriptionId || "");
        if (!childId) throw new Error("实时订阅 ID 无效");
        const handlers = {
          onOpen: () => post(frame, { channel: CHANNEL, kind: "sse_state", subscriptionId: childId, state: "open" }),
          onError: () => post(frame, { channel: CHANNEL, kind: "sse_state", subscriptionId: childId, state: "error" }),
          onMessage: (event) => post(frame, {
            channel: CHANNEL,
            kind: "sse_message",
            subscriptionId: childId,
            data: event?.raw ?? JSON.stringify(event?.parsed ?? event ?? null),
            eventType: event?.eventType || "message",
            lastEventId: event?.lastEventId || "",
          }),
        };
        const hostId = await api.subscribeSSE(proxyEndpoint, handlers, payload.params);
        state.subscriptions.set(childId, hostId);
        return { subscriptionId: childId };
      }
      case "sse:unsubscribe": {
        const childId = String(payload.subscriptionId || "");
        const hostId = state.subscriptions.get(childId);
        if (hostId !== undefined && typeof api.unsubscribeSSE === "function") {
          await api.unsubscribeSSE(hostId);
          state.subscriptions.delete(childId);
        }
        return { subscriptionId: childId };
      }
      default:
        throw new Error("模块页面请求的桥接操作不受支持");
    }
  }

  async function cleanupFrame(frame, state) {
    const api = bridge();
    if (api && typeof api.unsubscribeSSE === "function") {
      for (const hostId of state.subscriptions.values()) {
        try { await api.unsubscribeSSE(hostId); } catch { /* The frame is already closing. */ }
      }
    }
    state.subscriptions.clear();
  }

  window.addEventListener("message", async (event) => {
    const found = childFrame(event.source);
    if (!found) return;
    if (event.origin !== "null" && event.origin !== window.location.origin) return;
    const { frame, state } = found;
    const message = event.data;
    if (!message || message.channel !== CHANNEL) return;
    if (message.kind === "ready") {
      const parentContext = bridge()?.getContext?.() || {};
      post(frame, {
        channel: CHANNEL,
        kind: "context",
        context: {
          pluginName: MODULE_API_NAMES[state.module],
          displayName: "知伴",
          pageName: state.module,
          pageTitle: state.label,
          locale: parentContext.locale || "zh-CN",
          i18n: parentContext.i18n || {},
          isDark: parentContext.isDark,
        },
      });
      return;
    }
    if (message.kind !== "request" || typeof message.requestId !== "string") return;
    try {
      const data = await handleRequest(frame, state, message);
      sendResponse(frame, message.requestId, data);
    } catch (error) {
      sendError(frame, message.requestId, error);
    }
  });

  window.ZhibanBridge = {
    apiGet: async (path, params) => {
      const api = bridge();
      if (!api) throw new Error("AstrBot 已登录页面桥接尚未就绪");
      if (typeof api.ready === "function") await api.ready();
      return api.apiGet(appEndpoint(path), params);
    },
    apiPost: async (path, body) => {
      const api = bridge();
      if (!api) throw new Error("AstrBot 已登录页面桥接尚未就绪");
      if (typeof api.ready === "function") await api.ready();
      return api.apiPost(appEndpoint(path), body);
    },
    attachFrame(frame, module, label) {
      const previous = frames.get(frame);
      if (previous) void cleanupFrame(frame, previous);
      const state = { module, label, subscriptions: new Map(), loaded: false };
      frames.set(frame, state);
      frame.addEventListener("load", () => {
        if (state.loaded) void cleanupFrame(frame, state);
        state.loaded = true;
      });
      return () => {
        if (frames.get(frame) === state) frames.delete(frame);
        void cleanupFrame(frame, state);
      };
    },
  };
})();
