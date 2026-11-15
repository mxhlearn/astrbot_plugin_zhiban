"""Resolve the small set of bundled module pages exposed by the app shell."""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath


MODULE_UI_ROOTS = {
    "heart": ("astrbot_plugin_angel_heart", "pages", "chat-config"),
    "memory": ("astrbot_plugin_livingmemory", "pages", "dashboard"),
    "meme": ("astrbot_plugin_meme_manager", "pages", "app"),
    "tts": ("astrbot_plugin_breeze_tts", "views", "panel"),
    "brush": ("astrbot_plugin_angel_brush", "pages", "brush-config"),
    "music": ("astrbot_plugin_listen_music", "pages", "accounts"),
    "qzone": ("astrbot_plugin_qzone_ultra", "pages", "qzone"),
}

MODULE_API_NAMES = {
    "heart": "astrbot_plugin_angel_heart",
    "memory": "astrbot_plugin_livingmemory",
    "meme": "meme_manager",
    "tts": "astrbot_plugin_breeze_tts",
    "brush": "astrbot_plugin_angel_brush",
    "music": "astrbot_plugin_listen_music",
    "eye": "astrbot_plugin_angel_eye",
    "qzone": "astrbot_plugin_qzone_ultra",
    "qqprofile": "astrbot_plugin_qqprofile",
}


def resolve_module_ui_asset(plugin_root: Path, module: str, asset_path: str) -> Path | None:
    """Return a file only from a mapped UI directory, rejecting path traversal."""
    mapping = MODULE_UI_ROOTS.get(module)
    if mapping is None or not asset_path or "\\" in asset_path:
        return None

    relative = PurePosixPath(asset_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return None

    base = (plugin_root / "modules" / mapping[0] / Path(*mapping[1:])).resolve()
    target = (base / Path(*relative.parts)).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target if target.is_file() else None


def legacy_bridge_script(plugin_name: str) -> str:
    """Adapt legacy bundled pages to AstrBot's nested-page postMessage contract."""
    module_key = next(
        (key for key, root in MODULE_UI_ROOTS.items() if root[0] == plugin_name),
        None,
    )
    api_plugin_name = MODULE_API_NAMES.get(module_key, plugin_name)
    template = """<script>
(() => {{
  const CHANNEL = "astrbot-plugin-page";
  const SELF_ORIGIN = window.location.origin;
  const pluginName = __API_PLUGIN_NAME__;
  let context = {{ pluginName, displayName: "知伴", pageName: "module", pageTitle: "module", locale: "zh-CN", i18n: {{}} }};
  const pendingRequests = new Map();
  const sseHandlers = new Map();
  const contextHandlers = new Set();
  let requestCounter = 0;
  let subscriptionCounter = 0;
  let parentOrigin = null;
  let resolveReady;
  const readyPromise = new Promise(resolve => {{ resolveReady = resolve; }});

  function makeEndpoint(endpoint) {{
    const path = String(endpoint || "").trim().replace(/^\\/+/, "");
    if (!path || path.includes("\\\\") || path.includes("://") || path.includes("?") || path.includes("#") ||
        path.split("/").some(part => !part || part === "." || part === "..")) {{
      throw new Error("Invalid plugin bridge endpoint.");
    }}
    return `${{pluginName}}/${{path}}`;
  }}

  function targetOrigin() {{
    if (parentOrigin && parentOrigin !== "null") return parentOrigin;
    if (SELF_ORIGIN !== "null") return SELF_ORIGIN;
    return "*";
  }}

  function isAllowedParentOrigin(origin) {{
    if (typeof origin !== "string" || !origin) return false;
    if (parentOrigin) return origin === parentOrigin;
    return SELF_ORIGIN === "null" || origin === SELF_ORIGIN;
  }}

  function send(kind, payload, transfer) {{
    window.parent.postMessage(
      {{ channel: CHANNEL, kind, ...(payload || {{}}) }},
      targetOrigin(),
      transfer || [],
    );
  }}

  function makeRequest(action, payload, transfer) {{
    return new Promise((resolve, reject) => {{
      requestCounter += 1;
      const requestId = `plugin_req_${{requestCounter}}`;
      pendingRequests.set(requestId, {{ resolve, reject }});
      send("request", {{ requestId, action, ...(payload || {{}}) }}, transfer);
    }});
  }}

  function parseMaybeJson(value) {{
    if (typeof value !== "string") return value;
    try {{ return JSON.parse(value); }} catch {{ return value; }}
  }}

  function notifyContextHandlers() {{
    contextHandlers.forEach(handler => {{
      try {{ handler(context); }} catch (error) {{ console.error("Plugin context handler failed:", error); }}
    }});
  }}

  function applyContext(nextContext) {{
    if (!nextContext || typeof nextContext !== "object") return;
    context = {{ ...context, ...nextContext, pluginName }};
    if (typeof nextContext.isDark === "boolean") {{
      document.documentElement.setAttribute("data-theme", nextContext.isDark ? "dark" : "light");
    }}
    if (resolveReady) {{ resolveReady(context); resolveReady = null; }}
    notifyContextHandlers();
  }}

  window.addEventListener("message", event => {{
    if (event.source !== window.parent || !isAllowedParentOrigin(event.origin)) return;
    if (!parentOrigin) parentOrigin = event.origin;
    const message = event.data;
    if (!message || message.channel !== CHANNEL) return;

    if (message.kind === "context") {{ applyContext(message.context); return; }}
    if (message.kind === "response") {{
      const pending = pendingRequests.get(message.requestId);
      if (!pending) return;
      pendingRequests.delete(message.requestId);
      if (message.ok) pending.resolve(message.data);
      else pending.reject(new Error(message.error || "Plugin bridge request failed."));
      return;
    }}
    if (message.kind === "sse_message") {{
      const handlers = sseHandlers.get(message.subscriptionId);
      if (handlers?.onMessage) handlers.onMessage({{
        raw: message.data,
        parsed: parseMaybeJson(message.data),
        eventType: message.eventType || "message",
        lastEventId: message.lastEventId,
      }});
      return;
    }}
    if (message.kind === "sse_state") {{
      const handlers = sseHandlers.get(message.subscriptionId);
      if (message.state === "open" && handlers?.onOpen) handlers.onOpen();
      if (message.state === "error" && handlers?.onError) handlers.onError();
    }}
  }});

  window.AstrBotPluginView = window.AstrBotPluginPage = {{
    ready: () => readyPromise,
    getContext: () => context,
    getLocale: () => context.locale || "zh-CN",
    getI18n: () => context.i18n || {{}},
    t: (key, fallback) => {{
      const value = String(key || "").split(".").reduce((current, part) => current?.[part], context.i18n?.[context.locale] || context.i18n?.["zh-CN"]);
      return value === undefined || value === null ? (fallback || "") : String(value);
    }},
    onContext: handler => {{
      if (typeof handler !== "function") return () => {{}};
      contextHandlers.add(handler);
      if (context) handler(context);
      return () => contextHandlers.delete(handler);
    }},
    __setInitialContext: applyContext,
    apiGet: (endpoint, params) => {{
      if (String(endpoint || "").replace(/^\\/+/, "") === "bridge/auth_token") return Promise.resolve({{ token: "" }});
      return makeRequest("api:get", {{ endpoint: makeEndpoint(endpoint), params }});
    }},
    apiPost: (endpoint, body) => makeRequest("api:post", {{ endpoint: makeEndpoint(endpoint), body }}),
    async upload(endpoint, file) {{
      if (!file || typeof file.arrayBuffer !== "function") throw new Error("Missing uploaded file payload.");
      const fileBuffer = await file.arrayBuffer();
      return makeRequest("files:upload", {{
        endpoint: makeEndpoint(endpoint),
        fileName: file.name || "upload.bin",
        fileType: file.type || "application/octet-stream",
        fileLastModified: typeof file.lastModified === "number" ? file.lastModified : null,
        fileBuffer,
      }}, [fileBuffer]);
    }},
    download: (endpoint, params, filename) => makeRequest("files:download", {{ endpoint: makeEndpoint(endpoint), params, filename }}),
    async subscribeSSE(endpoint, handlers, params) {{
      subscriptionCounter += 1;
      const subscriptionId = `plugin_sse_${{subscriptionCounter}}`;
      sseHandlers.set(subscriptionId, handlers || {{}});
      try {{
        await makeRequest("sse:subscribe", {{ endpoint: makeEndpoint(endpoint), params, subscriptionId }});
        return subscriptionId;
      }} catch (error) {{
        sseHandlers.delete(subscriptionId);
        throw error;
      }}
    }},
    async unsubscribeSSE(subscriptionId) {{
      sseHandlers.delete(subscriptionId);
      return makeRequest("sse:unsubscribe", {{ subscriptionId }});
    }}
  }};
  send("ready");
}})();
</script>"""
    return (
        template.replace("__API_PLUGIN_NAME__", json.dumps(api_plugin_name))
        .replace("{{", "{")
        .replace("}}", "}")
    )


def prepare_module_ui_html(
    html: str,
    plugin_name: str,
    *,
    module_bridge_src: str = "../../module_bridge.js",
) -> str:
    """Add AstrBot's SDK and module adapter before bundled page scripts."""
    html = re.sub(
        r"<script\b[^>]*\bsrc=[\"']\/api\/plugin\/page\/bridge-sdk\.js(?:\?[^\"']*)?[\"'][^>]*>\s*<\/script>",
        "",
        html,
        flags=re.IGNORECASE,
    )
    module_key = next(
        (key for key, root in MODULE_UI_ROOTS.items() if root[0] == plugin_name),
        None,
    )
    page_theme_bootstrap = (
        '<script id="zhiban-page-theme-bootstrap">'
        '(function(){var el=document.documentElement;if(!el||!el.dataset)return;'
        'var embedded=new URLSearchParams(location.search).get("embedded")==="frame";'
        'el.dataset.zhibanEmbedded=embedded?"true":"false";'
        'if(embedded){el.dataset.zhibanHostFrame="true";}'
        '})();'
        '</script>'
    )
    first_paint = '<meta name="view-transition" content="same-origin">'
    first_paint += '<meta name="color-scheme" content="light">'
    first_paint += '<meta name="zhiban-runtime-marker" content="module">'
    first_paint += "<style id=\"zhiban-head-theme\">:root{color-scheme:light;--bg-app:#f5f8f4;--bg-sidebar:#eef5ec;--bg-card:#fff;--bg-hover:#e7f0e7;--accent-light:#ddeedc;--graph-surface:#f8fbf7;--border-light:#dce6da;--border-normal:#bdcfbb;--text-primary:#24382c;--text-secondary:#617367;--text-tertiary:#718477;--text-inverse:#fff;--accent:#2f6b4f;--accent-hover:#24563f;--primary-color:#2f6b4f;--primary:#2f6b4f;--accent-color:#2f6b4f;--link-color:#2f6b4f}html{background:#f5f8f4;color:#24382c}body{background:#f5f8f4;color:#24382c}:is(.n-button--primary-type,.btn-primary,.button-primary,.el-button--primary,.ant-btn-primary){background:#2f6b4f;border-color:#2f6b4f;color:#fff}</style>"
    shell_bootstrap = (
        '<script id="zhiban-shell-bootstrap">'
        'document.documentElement.dataset.zhibanEmbedded='
        'new URLSearchParams(location.search).get("embedded")==="frame"?"true":"false";'
        '</script>'
    )
    script = '<script src="/api/plugin/page/bridge-sdk.js"></script>'
    if module_key:
        script += f'<script id="zhiban-module-adapter" src="{module_bridge_src}" data-module-key="{module_key}"></script>'
    match = re.search(r"<head\b[^>]*>", html, flags=re.IGNORECASE)
    if match:
        return html[: match.end()] + page_theme_bootstrap + first_paint + shell_bootstrap + script + html[match.end() :]
    return page_theme_bootstrap + first_paint + shell_bootstrap + script + html
