"""Resolve the small set of bundled module pages exposed by the app shell."""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath


MODULE_UI_ROOTS = {
    "heart": ("astrbot_plugin_angel_heart", "pages", "chat-config"),
    "search": ("astrbot_plugin_anysearch", "pages", "search"),
    "memory": ("astrbot_plugin_livingmemory", "pages", "dashboard"),
    "meme": ("astrbot_plugin_meme_manager", "pages", "app"),
    "tts": ("astrbot_plugin_breeze_tts", "views", "panel"),
    "brush": ("astrbot_plugin_angel_brush", "pages", "brush-config"),
    "music": ("astrbot_plugin_listen_music", "pages", "accounts"),
    "qzone": ("astrbot_plugin_qzone_ultra", "pages", "qzone"),
}

MODULE_API_NAMES = {
    "heart": "astrbot_plugin_angel_heart",
    "search": "astrbot_plugin_anysearch",
    "memory": "astrbot_plugin_livingmemory",
    "meme": "meme_manager",
    "tts": "astrbot_plugin_breeze_tts",
    "brush": "astrbot_plugin_angel_brush",
    "music": "astrbot_plugin_listen_music",
    "eye": "astrbot_plugin_angel_eye",
    "qzone": "astrbot_plugin_qzone_ultra",
    "qqprofile": "astrbot_plugin_qqprofile",
}


# 知伴宿主主题的单一浅绿语义调色板。模块页首帧、深色切换和桥接覆盖共用
# 这套变量；模块不得再维护自己的风格预设或明暗偏好。
HOST_PALETTE = {
    "light": {
        "--bg-app": "#f5f8f4", "--bg-base": "#f5f8f4", "--bg-sidebar": "#eef5ec",
        "--bg-card": "#ffffff", "--bg-hover": "#e7f0e7", "--bg-active": "#ddeedc",
        "--bg-input": "#ffffff", "--bg-overlay": "rgba(255,255,255,.94)", "--bg-tint": "#eef5ec",
        "--bg-toolbar": "#ffffff", "--bg-table-head": "#eef5ec", "--screen-overlay": "rgba(30,50,38,.24)",
        "--graph-surface": "#f8fbf7", "--border-light": "#dce6da", "--border-normal": "#bdcfbb",
        "--border-color": "#dce6da", "--border-focus": "#2f6b4f", "--text-primary": "#24382c",
        "--text-secondary": "#617367", "--text-tertiary": "#718477", "--text-inverse": "#ffffff",
        "--accent": "#2f6b4f", "--accent-color": "#2f6b4f", "--accent-light": "#ddeedc",
        "--accent-hover": "#24563f", "--signal": "#9dc7ac", "--signal-soft": "#e8f3e7",
        "--coral": "#9b5c46", "--cyan": "#3f7661", "--gold": "#b07b36",
        "--success": "#2f6b4f", "--success-light": "#ddeedc", "--warning": "#8a5a1f",
        "--warning-light": "#f7ecd9", "--danger": "#b0443f", "--danger-light": "#f8e4e1",
        "--danger-hover": "#8f342f", "--node-topic": "#78a94b", "--node-person": "#2a9e96",
        "--node-fact": "#c58c2a", "--node-summary": "#df6d62", "--node-other": "#74868a",
        "--primary-color": "#2f6b4f", "--primary": "#2f6b4f", "--link-color": "#2f6b4f",
    },
    "dark": {
        "--bg-app": "#111811", "--bg-base": "#111811", "--bg-sidebar": "#162117",
        "--bg-card": "#1b261c", "--bg-hover": "#243528", "--bg-active": "#2a3f2d",
        "--bg-input": "#1b261c", "--bg-overlay": "rgba(17,24,17,.95)", "--bg-tint": "#162117",
        "--bg-toolbar": "#1b261c", "--bg-table-head": "#162117", "--screen-overlay": "rgba(0,0,0,.55)",
        "--graph-surface": "#131c14", "--border-light": "#354637", "--border-normal": "#4b6150",
        "--border-color": "#354637", "--border-focus": "#8fc7a5", "--text-primary": "#eef5ef",
        "--text-secondary": "#aebbad", "--text-tertiary": "#91a394", "--text-inverse": "#101611",
        "--accent": "#8fc7a5", "--accent-color": "#8fc7a5", "--accent-light": "#263a2b",
        "--accent-hover": "#b3d9c1", "--signal": "#b3d9c1", "--signal-soft": "#263a2b",
        "--coral": "#d79a84", "--cyan": "#6fb59a", "--gold": "#d3a35b",
        "--success": "#8fc7a5", "--success-light": "#203427", "--warning": "#e4b066",
        "--warning-light": "#3b2d19", "--danger": "#f08b84", "--danger-light": "#3c211f",
        "--danger-hover": "#f6aaa4", "--node-topic": "#8fbe62", "--node-person": "#56b8ae",
        "--node-fact": "#d9a64c", "--node-summary": "#e88276", "--node-other": "#92a4a8",
        "--primary-color": "#8fc7a5", "--primary": "#8fc7a5", "--link-color": "#8fc7a5",
    },
}


def _palette_css(selector: str, palette: dict[str, str]) -> str:
    return selector + "{" + ";".join(f"{key}:{value}" for key, value in palette.items()) + "}"


def host_theme_css() -> str:
    """Return the shared first-paint palette used before module scripts run."""
    light = _palette_css(":root", HOST_PALETTE["light"])
    dark = _palette_css(':root[data-theme="dark"]', HOST_PALETTE["dark"])
    return (
        light
        + dark
        + ":root{color-scheme:light}html{background:var(--bg-app);color:var(--text-primary)}"
        + "body{background:var(--bg-app);color:var(--text-primary)}"
        + ':root[data-theme="dark"]{color-scheme:dark}'
        + ":is(.n-button--primary-type,.btn-primary,.button-primary,.el-button--primary,.ant-btn-primary)"
        + "{background:var(--accent);border-color:var(--accent);color:var(--text-inverse)}"
    )


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
    """Add AstrBot's SDK and module adapter before bundled page scripts.

    The transformation is idempotent: regenerated pages replace the generated
    bootstrap/style/adapter tags instead of stacking them, and an existing
    embedded marker is never overwritten by a second pass.
    """
    html = re.sub(
        r"<script\b[^>]*\bid=[\"']zhiban-(?:page-theme-bootstrap|shell-bootstrap|embed-bootstrap|module-adapter)[\"'][^>]*>.*?<\/script>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html = re.sub(
        r"<style\b[^>]*\bid=[\"']zhiban-head-theme[\"'][^>]*>.*?<\/style>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
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
    embed_bootstrap = (
        '<script id="zhiban-embed-bootstrap">'
        '(function(){var el=document.documentElement;if(!el||!el.dataset)return;'
        'if(el.dataset.zhibanEmbedded==="true"||el.dataset.zhibanHostFrame==="true")return;'
        'var embedded=new URLSearchParams(location.search).get("embedded")==="frame";'
        'el.dataset.zhibanEmbedded=embedded?"true":"false";'
        'if(embedded){el.dataset.zhibanHostFrame="true";}'
        '})();'
        '</script>'
    )
    first_paint = '<meta name="view-transition" content="same-origin">'
    first_paint += '<meta name="color-scheme" content="light">'
    first_paint += '<meta name="zhiban-runtime-marker" content="module">'
    first_paint += f'<style id="zhiban-head-theme">{host_theme_css()}</style>'
    script = '<script src="/api/plugin/page/bridge-sdk.js"></script>'
    if module_key:
        bridge_url = module_bridge_src
        if "?" not in bridge_url:
            bridge_url += "?v=20261117"
        script += f'<script id="zhiban-module-adapter" src="{bridge_url}" data-module-key="{module_key}"></script>'
    match = re.search(r"<head\b[^>]*>", html, flags=re.IGNORECASE)
    if match:
        return html[: match.end()] + embed_bootstrap + first_paint + script + html[match.end() :]
    return embed_bootstrap + first_paint + script + html
