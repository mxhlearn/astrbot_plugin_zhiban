// 四个插件页面共用页面外框和对话框行为。
const pageNames = [
  ["a_manage", "表情包管理", "fa-face-grin-beam"],
  ["catalog", "资源广场", "fa-store"],
  ["semantic", "语义化", "fa-wand-magic-sparkles"],
  ["settings", "设置中心", "fa-sliders"],
];
const SUBPAGE_BY_FOLDER = {
  a_manage: "manage",
  catalog: "catalog",
  semantic: "semantic",
  settings: "settings",
};
const zhibanModule = window.ZhibanModule || null;
const embedded = Boolean(zhibanModule && zhibanModule.isEmbedded === true);
if (embedded && typeof zhibanModule?.onContext === "function") {
  zhibanModule.onContext((context) => {
    updateRouteMetadata(context);
    ensureBreadcrumb();
    const subpage = document.querySelector(".meme-breadcrumb strong");
    if (subpage) subpage.textContent = currentModuleLabel();
    notifyRouteChange();
  });
}
window.addEventListener("hashchange", () => {
  updateRouteMetadata();
  notifyRouteChange();
});

function moduleRoute() {
  return zhibanModule &&
    zhibanModule.route &&
    typeof zhibanModule.route === "object"
    ? zhibanModule.route
    : {};
}

const routeListeners = new Set();
function routeKey(route = moduleRoute()) {
  const query = route?.query && typeof route.query === "object" ? route.query : {};
  return JSON.stringify([
    String(route?.path || ""),
    String(route?.subpage || ""),
    String(route?.hash || route?.subpageHash || "").replace(/^#/, ""),
    query,
  ]);
}


let lastRouteKey = routeKey();

function routeSnapshot() {
  const route = moduleRoute();
  return {
    ...route,
    query:
      route.query && typeof route.query === "object" ? { ...route.query } : {},
  };
}

function notifyRouteChange(force = false) {
  const snapshot = routeSnapshot();
  const nextKey = routeKey(snapshot);
  if (!force && nextKey === lastRouteKey) return;
  lastRouteKey = nextKey;
  for (const listener of [...routeListeners]) {
    try {
      listener(snapshot);
    } catch (error) {
      console.error("模块路由监听器执行失败：", error);
    }
  }
}

function onRouteChange(listener) {
  if (typeof listener !== "function") return () => {};
  routeListeners.add(listener);
  return () => routeListeners.delete(listener);
}

function updateRouteMetadata(context = moduleRoute()) {
  const route = context && typeof context === "object" ? context : {};
  const rawPath = String(route.path || "")
    .replace(/\\/g, "/")
    .replace(/^(?:\.\.\/|\.\/|\/)+/, "");
  const subpage =
    SUBPAGE_BY_FOLDER[rawPath.split("/")[0]] || route.subpage || "";
  if (subpage) document.documentElement.dataset.zhibanSubpage = subpage;
  const hash = String(route.hash || route.subpageHash || "").replace(/^#/, "");
  document.documentElement.dataset.zhibanSubpageHash = hash;
  if (hash) window.__zhibanRouteHash = hash;
  else delete window.__zhibanRouteHash;
  return { subpage, hash };
}

function folderSubpage(value) {
  const text = String(value || "")
    .replace(/\\/g, "/")
    .replace(/^(?:\.\.\/|\.\/|\/)+/, "");
  return SUBPAGE_BY_FOLDER[text.split("/")[0]] || "";
}

function currentSubpage() {
  const route = moduleRoute();
  const raw = String(
    route.subpage || document.documentElement.dataset.zhibanSubpage || "",
  ).trim();
  if (SUBPAGE_BY_FOLDER[raw]) return SUBPAGE_BY_FOLDER[raw];
  if (Object.values(SUBPAGE_BY_FOLDER).includes(raw)) return raw;
  return folderSubpage(route.path || "");
}

function getRouteQuery() {
  const query = {};
  const route = moduleRoute();
  if (route.query && typeof route.query === "object") {
    for (const [key, value] of Object.entries(route.query)) {
      if (key === "asset_token" || value === null || value === undefined)
        continue;
      query[key] = String(value);
    }
  }
  try {
    for (const [key, value] of new URLSearchParams(location.search)) {
      if (
        key === "asset_token" ||
        ["embedded", "zhiban_panel", "theme"].includes(key) ||
        key in query
      )
        continue;
      query[key] = value;
    }
  } catch {
    // about:srcdoc 等不透明来源可能无法读取 location.search。
  }
  return query;
}

function getRouteHash() {
  const route = moduleRoute();
  // syncModuleRoute() may receive a read-only route snapshot from the host
  // bridge. Its local override is authoritative after an in-page navigation.
  const candidate =
    window.__zhibanRouteHash ||
    document.documentElement.dataset.zhibanSubpageHash ||
    route.hash ||
    route.subpageHash ||
    "";
  if (candidate) return String(candidate).replace(/^#/, "");
  if (!embedded) return String(location.hash || "").replace(/^#/, "");
  return "";
}

function splitModuleTarget(targetPath) {
  const text = String(targetPath || "").trim();
  const hashIndex = text.indexOf("#");
  const hash = hashIndex >= 0 ? text.slice(hashIndex) : "";
  const beforeHash = hashIndex >= 0 ? text.slice(0, hashIndex) : text;
  const queryIndex = beforeHash.indexOf("?");
  const query = new URLSearchParams(
    queryIndex >= 0 ? beforeHash.slice(queryIndex + 1) : "",
  );
  const path = (queryIndex >= 0 ? beforeHash.slice(0, queryIndex) : beforeHash)
    .replace(/^\.\.?\//, "")
    .replace(/^\/+/, "");
  return { path, query, hash };
}

function buildModuleTarget(path, extraParams = {}) {
  const target = splitModuleTarget(path);
  const query = new URLSearchParams(target.query);
  for (const [key, value] of Object.entries(extraParams)) {
    if (key === "asset_token") continue;
    if (value === null || value === undefined || value === "")
      query.delete(key);
    else query.set(key, String(value));
  }
  const suffix = query.toString();
  return `${target.path}${suffix ? `?${suffix}` : ""}${target.hash}`;
}

function normalizeModuleTarget(targetPath) {
  const raw = String(targetPath || "").trim();
  if (!raw || raw.startsWith("#")) return "";
  const target = splitModuleTarget(raw);
  const parts = [];
  for (const part of target.path.replace(/\\/g, "/").replace(/^\/+/, "").split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (!parts.length) return "";
      parts.pop();
      continue;
    }
    parts.push(part);
  }
  const path = parts.join("/");
  if (!path || !(path.endsWith(".html") || path.endsWith("/"))) return "";
  const [folder] = path.split("/");
  if (!SUBPAGE_BY_FOLDER[folder]) return "";
  return buildModuleTarget(path, Object.fromEntries(target.query)) + target.hash;
}
function navigateModuleTarget(targetPath, extraParams = {}) {
  if (!embedded || typeof zhibanModule?.navigate !== "function") return false;
  if (String(targetPath || "").startsWith("#")) {
    const hash = String(targetPath).replace(/^#/, "");
    const route = moduleRoute();
    const path = String(route?.path || `${currentSubpage() || "a_manage"}/index.html`);
    if (route && typeof route === "object") {
      route.hash = hash;
      route.subpageHash = hash;
    }
    window.__zhibanRouteHash = hash;
    document.documentElement.dataset.zhibanSubpageHash = hash;
    notifyRouteChange(true);
    return zhibanModule.navigate(`${path}${hash ? `#${hash}` : ""}`) !== false;
  }
  const target = normalizeModuleTarget(
    extraParams && Object.keys(extraParams).length
      ? buildModuleTarget(targetPath, extraParams)
      : targetPath,
  );
  if (!target) return false;
  try {
    return zhibanModule.navigate(target) !== false;
  } catch {
    return false;
  }
}

function syncModuleRoute(targetPath, extraParams = {}) {
  const target = normalizeModuleTarget(
    extraParams && Object.keys(extraParams).length
      ? buildModuleTarget(targetPath, extraParams)
      : targetPath,
  );
  if (!target) return false;
  const parsed = splitModuleTarget(target);
  const route = moduleRoute();
  if (route && typeof route === "object") {
    route.path = parsed.path;
    route.subpage = folderSubpage(parsed.path);
    route.hash = parsed.hash.replace(/^#/, "");
    route.subpageHash = route.hash;
    route.query = Object.fromEntries(parsed.query);
  }
  document.documentElement.dataset.zhibanSubpage = folderSubpage(parsed.path);
  document.documentElement.dataset.zhibanSubpageHash = parsed.hash.replace(
    /^#/,
    "",
  );
  if (parsed.hash) window.__zhibanRouteHash = parsed.hash.replace(/^#/, "");
  else delete window.__zhibanRouteHash;
  notifyRouteChange(true);
  return true;
}
function currentModuleLabel(folder = currentSubpage()) {
  const match = pageNames.find(
    ([page]) => SUBPAGE_BY_FOLDER[page] === folder,
  );
  return match?.[1] || "表情互动";
}

function ensureBreadcrumb() {
  // The parent shell owns the breadcrumb. A second crumb inside the sandboxed
  // module would repeat 表达创作 / 表情互动 in the visible page.
  if (embedded) return;
  const host = document.querySelector(".page-header > div");
  if (!host || host.querySelector(".meme-breadcrumb")) return;
  const title = host.querySelector("h1");
  if (title) {
    const text = [...(title.childNodes || [])].find(
      (node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim(),
    );
    if (text) text.textContent = currentModuleLabel();
  }
  const crumbs = document.createElement("nav");
  crumbs.className = "meme-breadcrumb";
  crumbs.setAttribute("aria-label", "当前位置");
  crumbs.dataset.group = "表达创作";
  crumbs.dataset.module = "表情互动";
  crumbs.dataset.subpage = currentSubpage();
  const group = document.createElement("span");
  group.textContent = "表达创作";
  const separator1 = document.createElement("span");
  separator1.textContent = "/";
  separator1.setAttribute("aria-hidden", "true");
  const module = document.createElement("span");
  module.textContent = "表情互动";
  const separator2 = document.createElement("span");
  separator2.textContent = "/";
  separator2.setAttribute("aria-hidden", "true");
  const subpage = document.createElement("strong");
  subpage.textContent = currentModuleLabel();
  crumbs.append(group, separator1, module, separator2, subpage);
  host.prepend(crumbs);
}
function subpageForTarget(targetPath) {
  return folderSubpage(splitModuleTarget(targetPath).path);
}

ensureBreadcrumb();
window.addEventListener("error", (event) => {
  console.error("[meme route debug]", event.message, event.filename, event.lineno);
});
const nav = document.querySelector(".nav-actions");
if (nav) {
  nav.className = "nav-actions";
  nav.setAttribute("role", "navigation");
  nav.setAttribute("aria-label", "页面导航");
  nav.replaceChildren();
  const active = currentSubpage();
  for (const [page, label, icon] of pageNames) {
    const link = document.createElement("a");
    link.className = "nav-link";
    link.dataset.navTarget = `../${page}/index.html`;
    link.dataset.moduleTarget = `${page}/index.html`;
    link.dataset.zhibanSubpage = subpageForTarget(link.dataset.moduleTarget);
    link.href = link.dataset.navTarget;
    if (page === "catalog") link.dataset.navView = "catalog";
    if (active && link.dataset.zhibanSubpage === active)
      link.setAttribute("aria-current", "page");
    link.innerHTML = `<i class="fas ${icon} icon" aria-hidden="true"></i>${label}`;
    nav.append(link);
  }
}
const main = document.querySelector("main, #content");
if (main) {
  if (!main.id) main.id = "main-content";
  main.tabIndex = -1;
  const skip = document.createElement("a");
  skip.className = "skip-link";
  skip.href = `#${main.id}`;
  skip.textContent = "跳到主要内容";
  document.body.prepend(skip);
}

let navAuthToken = "";
function withCurrentAuthParams(targetPath, extraParams = {}) {
  let base = location.href;
  if (embedded) {
    try {
      if (document.baseURI && !/^about:/i.test(document.baseURI))
        base = document.baseURI;
    } catch {
      // 保持 about:srcdoc 下的兼容回退。
    }
  }
  let nextUrl;
  try {
    nextUrl = new URL(targetPath, base);
  } catch {
    nextUrl = new URL(targetPath, "http://zhiban.invalid/");
  }
  const inherited = embedded
    ? getRouteQuery()
    : Object.fromEntries(new URLSearchParams(location.search));
  for (const [key, value] of Object.entries(inherited)) {
    if (key === "asset_token" || nextUrl.searchParams.has(key)) continue;
    nextUrl.searchParams.set(key, value);
  }
  for (const [key, value] of Object.entries(extraParams)) {
    if (key === "asset_token") {
      if (embedded || nextUrl.origin !== location.origin) continue;
    }
    if (value === null || value === undefined || value === "")
      nextUrl.searchParams.delete(key);
    else nextUrl.searchParams.set(key, String(value));
  }
  return nextUrl;
}
async function ensureNavAuthToken() {
  if (embedded) return "";
  if (navAuthToken) return navAuthToken;
  try {
    const response = await window.AstrBotPluginPage.apiGet("bridge/auth_token");
    navAuthToken = String(response?.token || "").trim();
  } catch {
    navAuthToken = "";
  }
  return navAuthToken;
}
function bindEmbeddedNavLink(link) {
  if (!embedded || !link || link.dataset.zhibanNavBound === "true") return;
  link.dataset.zhibanNavBound = "true";
  const target =
    link.dataset.moduleTarget ||
    buildModuleTarget(link.dataset.navTarget || link.getAttribute("href"));
  link.dataset.moduleTarget = target;
  if (!link.dataset.zhibanSubpage)
    link.dataset.zhibanSubpage = subpageForTarget(target);
  link.addEventListener("click", (event) => {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      link.target === "_blank" ||
      link.hasAttribute("download")
    )
      return;
    event.preventDefault();
    zhibanModule.navigate(target);
  });
}
async function applySecureNavLinks() {
  const links = document.querySelectorAll("a[data-nav-target]");
  if (embedded) {
    const active = currentSubpage();
    for (const link of links) {
      bindEmbeddedNavLink(link);
      if (active && link.dataset.zhibanSubpage === active)
        link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    return;
  }
  const token = await ensureNavAuthToken();
  for (const link of links) {
    link.href = withCurrentAuthParams(link.dataset.navTarget, {
      view: link.dataset.navView || null,
      asset_token: token || null,
    }).toString();
  }
}
function goToModulePage(targetPath, extraParams = {}) {
  if (embedded) return navigateModuleTarget(targetPath, extraParams);
  const nextUrl = withCurrentAuthParams(targetPath, {
    ...extraParams,
    asset_token: navAuthToken || null,
  });
  window.location.assign(nextUrl.toString());
  return true;
}

const confirmMask = document.createElement("div");
confirmMask.className = "dialog-mask ui-confirm-mask hidden";
confirmMask.setAttribute("aria-hidden", "true");
confirmMask.innerHTML = `<section class="dialog-card" role="dialog" aria-modal="true" aria-labelledby="ui-confirm-title" aria-describedby="ui-confirm-message">
  <h3 id="ui-confirm-title" class="ui-dialog-title text-h3 pa-4 pb-0 pl-6"></h3>
  <p id="ui-confirm-message" class="dialog-message"></p>
  <div class="dialog-actions"><button type="button" id="ui-confirm-cancel" class="ghost" variant="text">取消</button><button type="button" id="ui-confirm-accept" variant="tonal">确认</button></div>
</section>`;
document.body.append(confirmMask);
let confirmResolver = null;
const confirmCancel = confirmMask.querySelector("#ui-confirm-cancel");
const confirmAccept = confirmMask.querySelector("#ui-confirm-accept");
for (const button of [confirmCancel, confirmAccept]) {
  button.addEventListener("click", () => {
    confirmMask.classList.add("hidden");
    confirmMask.setAttribute("aria-hidden", "true");
    const resolve = confirmResolver;
    confirmResolver = null;
    resolve?.(button === confirmAccept);
  });
}
confirmMask.addEventListener("click", (event) => {
  if (event.target === confirmMask) confirmCancel.click();
});

// 仅观察模态遮罩，避免渲染列表时反复抢夺焦点。
const dialogStack = [];
const dialogObserver = new MutationObserver(() => {
  for (const dialog of document.querySelectorAll('[role="dialog"]')) {
    const mask = dialog.parentElement;
    const visible =
      !mask.classList.contains("hidden") &&
      mask.getAttribute("aria-hidden") !== "true" &&
      !mask.hidden;
    const index = dialogStack.findIndex((entry) => entry.dialog === dialog);
    if (visible && index < 0) {
      dialogStack.push({ dialog, previous: document.activeElement });
      dialog.tabIndex = -1;
      const first =
        dialog.querySelector("[data-dialog-dismiss]:not(:disabled)") ||
        dialog.querySelector(
          'button[id*="cancel"]:not(:disabled), button[id*="close"]:not(:disabled), input:not(:disabled), button:not(:disabled)',
        );
      (first || dialog).focus({ preventScroll: true });
    } else if (!visible && index >= 0) {
      const [entry] = dialogStack.splice(index, 1);
      if (
        entry.previous?.isConnected &&
        !entry.previous.closest(".hidden, [inert]")
      )
        entry.previous.focus({ preventScroll: true });
    }
  }
  document.body.classList.toggle("ui-modal-open", dialogStack.length > 0);
});
for (const dialog of document.querySelectorAll('[role="dialog"]')) {
  const mask = dialog.parentElement;
  let pointerDownTarget = null;
  let pointerUpTarget = null;
  mask.addEventListener(
    "pointerdown",
    (event) => {
      pointerDownTarget = event.target;
      pointerUpTarget = null;
    },
    true,
  );
  mask.addEventListener(
    "pointerup",
    (event) => {
      pointerUpTarget = event.target;
    },
    true,
  );
  mask.addEventListener(
    "pointercancel",
    () => {
      pointerDownTarget = null;
      pointerUpTarget = null;
    },
    true,
  );
  mask.addEventListener(
    "click",
    (event) => {
      // 拖动选区可能使点击目标变为对话框或其遮罩。
      if (
        event.detail > 0 &&
        (event.target === mask || event.target === dialog) &&
        (event.target !== pointerDownTarget || event.target !== pointerUpTarget)
      ) {
        event.stopImmediatePropagation();
      }
      pointerDownTarget = null;
      pointerUpTarget = null;
    },
    true,
  );
  dialogObserver.observe(mask, {
    attributes: true,
    attributeFilter: ["class", "aria-hidden", "hidden"],
  });
}
document.addEventListener(
  "keydown",
  (event) => {
    const dialog = dialogStack.at(-1)?.dialog;
    if (!dialog) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
      const cancel =
        dialog.querySelector("[data-dialog-dismiss]") ||
        dialog.querySelector('button[id*="cancel"], button[id*="close"]');
      if (cancel && !cancel.disabled) cancel.click();
    }
    if (event.key !== "Tab") return;
    const focusable = [
      ...dialog.querySelectorAll(
        'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
      ),
    ].filter(
      (element) =>
        element.getClientRects().length &&
        !element.closest("[inert], [hidden], .hidden"),
    );
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first) {
      event.preventDefault();
      dialog.focus();
    } else if (
      event.shiftKey &&
      (document.activeElement === first ||
        !dialog.contains(document.activeElement))
    ) {
      event.preventDefault();
      last.focus();
    } else if (
      !event.shiftKey &&
      (document.activeElement === last ||
        !dialog.contains(document.activeElement))
    ) {
      event.preventDefault();
      first.focus();
    }
  },
  true,
);

// 压缩包分片上传：宿主对单次请求体有上限，大压缩包必须分片传输。
const PACK_ARCHIVE_CHUNK_SIZE = 8 * 1024 * 1024;

async function uploadPackArchiveInChunks(file, { onProgress } = {}) {
  const pageApi = window.AstrBotPluginPage;
  if (!pageApi) {
    throw new Error("页面无法连接 AstrBot");
  }
  const totalChunks = Math.max(
    1,
    Math.ceil((file?.size || 0) / PACK_ARCHIVE_CHUNK_SIZE),
  );
  const session = await pageApi.apiPost("packs/import/session", {
    filename: String(file?.name || "pack.zip"),
    total_chunks: totalChunks,
  });
  const sessionId = session.session_id;
  let result = null;
  for (let index = 0; index < totalChunks; index += 1) {
    const start = index * PACK_ARCHIVE_CHUNK_SIZE;
    const end = Math.min(start + PACK_ARCHIVE_CHUNK_SIZE, file.size);
    const chunk = file.slice(start, end);
    result = await pageApi.upload(
      `packs/import/session/chunk/${sessionId}/${index}/${totalChunks}`,
      chunk,
    );
    onProgress?.(index + 1, totalChunks);
  }
  return result;
}

window.MemeUI = {
  get navAuthToken() {
    return navAuthToken;
  },
  isEmbedded: embedded,
  pageLabel: currentModuleLabel,
  getRoute: moduleRoute,
  getRouteQuery,
  getRouteHash,
  currentSubpage,
  onRouteChange,
  updateRoute: syncModuleRoute,
  navigate: navigateModuleTarget,
  navigateTarget: navigateModuleTarget,
  buildModuleTarget,
  go: goToModulePage,
  withCurrentAuthParams,
  ensureNavAuthToken,
  applySecureNavLinks,
  uploadPackArchiveInChunks,
  toast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      container.setAttribute("aria-live", "polite");
      document.body.append(container);
    }
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.append(toast);
    window.setTimeout(() => toast.remove(), type === "error" ? 6000 : 3500);
  },
  confirm({
    title = "确认操作",
    message = "",
    confirmText = "确认",
    cancelText = "取消",
    danger = false,
  } = {}) {
    if (confirmResolver) return Promise.resolve(false);
    confirmMask.querySelector("#ui-confirm-title").textContent = title;
    confirmMask.querySelector("#ui-confirm-message").textContent = message;
    confirmAccept.textContent = confirmText;
    confirmCancel.textContent = cancelText;
    confirmAccept.className = danger ? "danger" : "";
    confirmMask.classList.remove("hidden");
    confirmMask.setAttribute("aria-hidden", "false");
    return new Promise((resolve) => {
      confirmResolver = resolve;
    });
  },
  showPageError(error) {
    console.error("插件页面初始化失败：", error);
    let banner = document.querySelector(".ui-page-error");
    if (banner) return;
    banner = document.createElement("div");
    banner.className = "ui-page-error";
    banner.setAttribute("role", "alert");
    const message = document.createElement("span");
    message.textContent = `页面加载失败：${
      error?.message || "请检查连接后重试"
    }`;
    const retry = document.createElement("button");
    retry.className = "ghost";
    retry.textContent = "重新加载";
    retry.addEventListener("click", () => {
      if (embedded) {
        const route = moduleRoute();
        const fallback = `${currentSubpage() || "a_manage"}/index.html`;
        navigateModuleTarget(route.path || fallback);
        return;
      }
      location.reload();
    });
    banner.append(message, retry);
    document.querySelector(".page-header")?.after(banner);
  },
};
