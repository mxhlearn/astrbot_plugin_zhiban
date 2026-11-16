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
    qqprofile: "astrbot_plugin_qqprofile",
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
    const path = moduleRelativeEndpoint(moduleKey, endpoint);
    return `ui/module_api/${moduleKey}/${path}`;
  }

  function childFrame(source) {
    for (const [frame, state] of frames) {
      if (frame.contentWindow === source) return { frame, state };
    }
    return null;
  }

  const trustedChildOrigins = new WeakMap();

  function safeDetail(value) {
    return String(value || "")
      .replace(/asset_token=[^&\s]+/gi, "asset_token=***")
      .replace(/Bearer\s+[^\s]+/gi, "Bearer ***")
      .replace(/sk-[A-Za-z0-9_-]{8,}/g, "sk-***")
      .slice(0, 240);
  }

  function post(frame, message) {
    if (!frame?.contentWindow) return;
    // Child documents use the host-mandated sandbox without allow-same-origin.
    // Their envelopes arrive with origin "null"; verify the exact registered
    // frame source before targeting "*" for the return message.
    const fromKnownChild = trustedChildOrigins.get(frame) === true;
    const origin = fromKnownChild || window.location.origin === "null" ? "*" : window.location.origin;
    frame.contentWindow.postMessage(message, origin);
  }

  function frameContext(state) {
    const parentContext = bridge()?.getContext?.() || {};
    return {
      pluginName: MODULE_API_NAMES[state.module],
      displayName: "知伴",
      pageName: state.module,
      pageTitle: state.label,
      locale: parentContext.locale || "zh-CN",
      i18n: parentContext.i18n || {},
      isDark: parentContext.isDark,
      appReadyToken: state.appReadyToken,
      subpage: state.subpage || "",
      subpageHash: state.subpageHash || "",
      query: state.query || {},
    };
  }

  const MODULE_ROUTE_WHITELIST = {
    meme: new Set([
      "a_manage/index.html",
      "catalog/index.html",
      "semantic/index.html",
      "settings/index.html",
    ]),
  };

  const ROUTE_QUERY_KEY_RE = /^[a-z][a-z0-9_]{0,40}$/i;
  const RESERVED_ROUTE_QUERY_KEYS = new Set(["asset_token", "embedded", "zhiban_panel", "theme"]);

  function decodeModuleRoutePath(pathname) {
    let decoded;
    try {
      decoded = decodeURIComponent(String(pathname || ""));
    } catch {
      throw new Error("模块子页面路径无效");
    }
    if (!decoded || decoded.includes("\\") || decoded.includes("\0") ||
        decoded.includes("://") || decoded.includes("?") || decoded.includes("#") ||
        /(?:^|\/)\.{1,2}(?:\/|$)/.test(decoded)) {
      throw new Error("模块子页面路径无效");
    }
    return decoded;
  }

  function safeChildRoute(message, moduleKey) {
    const rawTarget = String(message?.path || "").trim();
    if (!rawTarget || rawTarget.includes("\\")) throw new Error("模块子页面路径无效");

    // The child may report either a module-relative path or the signed asset
    // URL visible in its srcdoc. Only the latter is absolute; never accept an
    // arbitrary origin or an absolute path that is not rooted at this module.
    const absolute = /^(?:[a-z][a-z0-9+.-]*:|\/\/|\/)/i.test(rawTarget);
    const rawPathText = rawTarget.split(/[?#]/, 1)[0];
    let decodedRawPath = rawPathText;
    try {
      decodedRawPath = decodeURIComponent(rawPathText);
    } catch {
      throw new Error("模块子页面路径无效");
    }
    if (absolute && /(?:^|\/)\.{1,2}(?:\/|$)/.test(decodedRawPath)) {
      throw new Error("模块子页面路径无效");
    }

    let pathname = rawTarget;
    let targetQuery = new URLSearchParams();
    let targetHash = "";
    if (absolute) {
      let parsed;
      try {
        parsed = new URL(rawTarget, window.location.origin);
      } catch {
        throw new Error("模块子页面路径无效");
      }
      if (!/^https?:$/.test(parsed.protocol) || parsed.origin !== window.location.origin) {
        throw new Error("模块子页面来源无效");
      }
      pathname = parsed.pathname;
      targetQuery = parsed.searchParams;
      targetHash = parsed.hash.replace(/^#/, "");
    } else if (/[?#]/.test(rawTarget)) {
      let parsed;
      try {
        parsed = new URL(rawTarget, "https://zhiban.invalid/");
      } catch {
        throw new Error("模块子页面路径无效");
      }
      pathname = parsed.pathname;
      targetQuery = parsed.searchParams;
      targetHash = parsed.hash.replace(/^#/, "");
    }

    const decodedPath = decodeModuleRoutePath(pathname);
    const marker = `/modules/${moduleKey}/`;
    const markerIndex = decodedPath.indexOf(marker);
    let rawPath;
    if (markerIndex >= 0) {
      rawPath = decodedPath.slice(markerIndex + marker.length);
    } else {
      if (absolute) throw new Error("模块子页面不在允许范围");
      rawPath = decodedPath.replace(/^\.\//, "").replace(/^\/+/, "");
    }
    if (rawPath.endsWith("/")) rawPath += "index.html";
    if (!rawPath || rawPath.length > 240 || rawPath.includes("?") || rawPath.includes("#") ||
        rawPath.split("/").some((part) => !part || part === "." || part === "..")) {
      throw new Error("模块子页面路径无效");
    }
    const allowed = MODULE_ROUTE_WHITELIST[moduleKey];
    if (!allowed || !allowed.has(rawPath)) {
      throw new Error(`模块子页面不在允许范围：${safeDetail(rawPath)}`);
    }

    const rawHash = String(message?.hash || targetHash || "").trim().replace(/^#/, "");
    if (rawHash.length > 120 || /[\s<>"']/u.test(rawHash)) throw new Error("模块子页面定位无效");

    const query = {};
    const seen = new Set();
    const addQuery = (key, value) => {
      if (!ROUTE_QUERY_KEY_RE.test(key) || RESERVED_ROUTE_QUERY_KEYS.has(key) || seen.size >= 8) return;
      const text = String(value ?? "");
      if (text.length > 240 || /[\r\n\0]/u.test(text)) return;
      query[key] = text;
      seen.add(key);
    };
    for (const [key, value] of targetQuery.entries()) addQuery(key, value);
    const input = message?.query && typeof message.query === "object" ? message.query : {};
    for (const [key, value] of Object.entries(input)) addQuery(key, value);
    return { path: rawPath, hash: rawHash, query };
  }

  function broadcastContext() {
    for (const [frame, state] of frames) {
      if (state.destroyed) continue;
      post(frame, { channel: CHANNEL, kind: "context", context: frameContext(state) });
    }
  }

  let contextSubscribed = false;
  function subscribeContext() {
    const api = bridge();
    if (contextSubscribed || typeof api?.onContext !== "function") return;
    contextSubscribed = true;
    api.onContext(() => broadcastContext());
  }

  function cloneableData(value, fallback = {}) {
    if (value === undefined) return fallback;
    try {
      return JSON.parse(JSON.stringify(value));
    } catch {
      return fallback;
    }
  }

  function sendResponse(frame, requestId, data) {
    post(frame, { channel: CHANNEL, kind: "response", requestId, ok: true, data: cloneableData(data) });
  }

  function sendError(frame, requestId, error) {
    const message = typeof error?.message === "string" ? error.message.slice(0, 240) : "请求失败";
    post(frame, { channel: CHANNEL, kind: "response", requestId, ok: false, error: message });
  }

  function assertModuleEndpoint(moduleKey, endpoint) {
    moduleRelativeEndpoint(moduleKey, endpoint);
  }

  function moduleRelativeEndpoint(moduleKey, endpoint) {
    const moduleName = MODULE_API_NAMES[moduleKey];
    if (!moduleName || typeof endpoint !== "string") {
      throw new Error("模块 API 范围不匹配");
    }
    let value = endpoint.replace(/^\/+/, "");
    if (!value || value.includes("\\") || value.includes("://") || value.includes("?") || value.includes("#") ||
        value.split("/").some((part) => !part || part === "." || part === "..")) {
      throw new Error("模块 API 路径无效");
    }
    const proxyPrefixes = [
      `ui/module_api/${moduleKey}/`,
      `${moduleName}/`,
    ];
    for (const prefix of proxyPrefixes) {
      if (value.startsWith(prefix)) value = value.slice(prefix.length);
    }
    const prefix = `${moduleName}/`;
    if (value.startsWith(prefix)) return value.slice(prefix.length);
    if (value === moduleName || value === APP_PLUGIN_NAME || value.startsWith(`${APP_PLUGIN_NAME}/`) ||
        Object.values(MODULE_API_NAMES).some((name) => name !== moduleName && (value === name || value.startsWith(`${name}/`)))) {
      throw new Error("模块 API 范围不匹配");
    }
    return value;
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
        if (moduleRelativeEndpoint(state.module, endpoint) === "bridge/auth_token") return { token: "" };
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
    if (state.destroyed) return;
    trustedChildOrigins.set(frame, true);
    const message = event.data;
    if (!message || message.channel !== CHANNEL) return;
    function trustedInstanceMessage(message) {
      return message?.module === state.module
        && typeof message.token === "string"
        && message.token.length > 0
        && message.token === state.appReadyToken;
    }

    if (message.kind === "app:ready") {
      if (!trustedInstanceMessage(message)) return;
      state.appReady = true;
      frame.dataset.appReady = "true";
      frame.dispatchEvent(new CustomEvent("zhiban:app-ready", { detail: { module: message.module } }));
      return;
    }
    if (message.kind === "app:error") {
      if (!trustedInstanceMessage(message)) return;
      state.lastError = { stage: safeDetail(message.stage), message: safeDetail(message.message) };
      frame.dispatchEvent(new CustomEvent("zhiban:app-error", { detail: state.lastError }));
      return;
    }
    if (message.kind === "navigate") {
      if (message.module !== state.module) return;
      if (!state.bridgeReady) return;
      try {
        if (!trustedInstanceMessage(message)) throw new Error("模块实例校验失败");
        const route = safeChildRoute(message, state.module);
        const detail = { module: state.module, ...route, accepted: false };
        const navigationEvent = new CustomEvent("zhiban:navigate", { detail, cancelable: true });
        frame.dispatchEvent(navigationEvent);
        // The parent app handles this event asynchronously after appending a
        // fresh module frame. Treat the event as accepted unless explicitly
        // rejected with preventDefault.
        if (!navigationEvent.defaultPrevented) detail.accepted = true;
        if (detail.accepted === true) {
          frame.dataset.subpage = route.path;
          frame.dataset.subpageHash = route.hash;
          state.subpage = route.path;
          state.subpageHash = route.hash;
          state.query = route.query;
          post(frame, { channel: CHANNEL, kind: "context", context: frameContext(state) });
        }
      } catch (error) {
        const detail = { stage: "导航", message: safeDetail(error?.message || "模块子页面无效") };
        post(frame, {
          channel: CHANNEL,
          kind: "navigation:error",
          module: state.module,
          ...detail,
        });
      }
      return;
    }
    if (message.kind === "ready") {
      if (message.module !== state.module) return;
      const firstReady = !state.bridgeReady;
      state.bridgeReady = true;
      frame.dataset.bridgeReady = "true";
      if (firstReady) {
        frame.dispatchEvent(new CustomEvent("zhiban:bridge-ready", { detail: { module: state.module } }));
      }
      post(frame, { channel: CHANNEL, kind: "context", context: frameContext(state) });
      return;
    }
    if (message.kind !== "request" || typeof message.requestId !== "string" || !state.bridgeReady) return;
    try {
      const data = await handleRequest(frame, state, message);
      sendResponse(frame, message.requestId, data);
    } catch (error) {
      sendError(frame, message.requestId, error);
    }
  });

  subscribeContext();

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
    attachFrame(frame, module, label, options = {}) {
      subscribeContext();
      const previous = frames.get(frame);
      if (previous) void cleanupFrame(frame, previous);
      const state = {
        module, label,
        subpage: String(options.subpage || ""),
        subpageHash: String(options.subpageHash || ""),
        query: options.query && typeof options.query === "object" ? { ...options.query } : {},
        subscriptions: new Map(), loaded: false, bridgeReady: false, appReady: false,
        destroyed: false, lastError: null, appReadyToken: `${module}-${Date.now()}`,
      };
      frames.set(frame, state);
      frame.dataset.bridgeReady = "false";
      frame.dataset.appReady = "false";
      frame.dataset.subpage = state.subpage;
      frame.addEventListener("load", () => {
        if (state.destroyed) return;
        if (state.loaded) void cleanupFrame(frame, state);
        state.loaded = true;
      });
      return () => {
        state.destroyed = true;
        if (frames.get(frame) === state) frames.delete(frame);
        void cleanupFrame(frame, state);
      };
    },
  };
})();
