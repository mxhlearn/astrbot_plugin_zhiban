import {
  buildConfigSavePayload,
  buildDefaultValues,
  configuredSecretPathList,
  flattenSchema,
  isSensitiveField,
  normalizeSecretPath,
  normalizeProviderOptions,
  numericConstraints,
  orderModules,
  parseFieldValue,
  secretPathList,
  setValueAtPath,
  unwrapApiPayload,
  validateNumericValue,
} from "./settings.mjs";

const moduleCatalog = [
  { key: "heart", label: "聊天互动", logo: "./logos/heart.png", description: "群聊接话、唤醒与私聊上下文", group: "聊天系统", groupKey: "chat", page: "heart", plugin: "astrbot_plugin_angel_heart" },
  { key: "memory", label: "记忆成长", logo: "./logos/memory.png", description: "长期记忆、知识检索与人格审批", group: "记忆成长", groupKey: "memory", page: "memory", plugin: "astrbot_plugin_livingmemory" },
  { key: "meme", label: "表情互动", logo: "./logos/meme.png", description: "服务器图库检索、管理与发送", group: "表达创作", groupKey: "creative", page: "meme", plugin: "astrbot_plugin_meme_manager" },
  { key: "tts", label: "语音回复", logo: "./logos/tts.png", description: "BreezeBlue 语音合成、音色与回复策略", group: "表达创作", groupKey: "creative", page: "tts", plugin: "astrbot_plugin_breeze_tts" },
  { key: "proactive", label: "主动问候", logo: "./logos/proactive.png", description: "按现有私聊策略进行主动问候", group: "聊天系统", groupKey: "chat", help: "主动问候由后台调度器执行。启用范围、免打扰时段与计划参数可在本模块配置中管理。" },
  { key: "brush", label: "图片创作", logo: "./logos/brush.png", description: "生图、改图与供应商配置", group: "表达创作", groupKey: "creative", page: "brush", plugin: "astrbot_plugin_angel_brush" },
  { key: "music", label: "音乐点播", logo: "./logos/music.png", description: "Bilibili 搜索、账号与音频发送", group: "表达创作", groupKey: "creative", page: "music", plugin: "astrbot_plugin_listen_music" },
  { key: "eye", label: "历史查询", logo: "./logos/eye.png", description: "群记录检索与分页查询", group: "聊天系统", groupKey: "chat", help: "通过原有历史查询命令或 LLM 工具检索记录；查询范围和分页参数可在本模块配置中管理。" },
  { key: "qzone", label: "QQ 动态", logo: "./logos/qzone.png", description: "QQ 空间动态浏览、发布与互动工具", group: "QQ 社交", groupKey: "social", page: "qzone", plugin: "astrbot_plugin_qzone_ultra" },
  { key: "qqprofile", label: "QQ 资料", logo: "./logos/qqprofile.png", description: "QQ 状态、签名、昵称与头像管理", group: "QQ 社交", groupKey: "social", help: "通过 OneBot 管理员命令或受权限限制的模型工具管理资料，例如“设置状态 忙碌”“设置签名 …”。" },
];
const GROUPS = [
  { key: "overview", label: "总览", description: "运行状态、待办与全局设置" },
  { key: "chat", label: "聊天系统", description: "回应、主动问候与历史查询" },
  { key: "memory", label: "记忆成长", description: "长期记忆、人格建议与检索管理" },
  { key: "creative", label: "表达创作", description: "表情、语音、图片与音乐" },
  { key: "social", label: "QQ 社交", description: "QQ 动态与资料管理" },
];
let modules = moduleCatalog;

const primaryNav = document.querySelector("#primaryNav");
const moduleTabs = document.querySelector("#moduleNav");
const title = document.querySelector("#moduleTitle");
const description = document.querySelector("#moduleDescription");
const status = document.querySelector("#moduleStatus");
const workspace = document.querySelector("#moduleWorkspace");
const settingsWorkspace = document.querySelector("#settingsWorkspace");
const refresh = document.querySelector("#refreshModule");
const breadcrumbGroup = document.querySelector("#breadcrumbGroup");
const breadcrumbPage = document.querySelector("#breadcrumbPage");
const overviewTabs = document.querySelector("#overviewTabs");
const groupTabs = document.querySelector("#groupTabs");
const configButton = document.querySelector("#headerConfigButton");
const backButton = document.querySelector("#headerBackButton");
const moduleStates = new Map();
const pendingApply = new Set();
let activeGroup = "overview";
let activeKey = "heart";
let activeFrame = null;
let activeFrameDetach = null;
let activeFrameReadyTimer = null;
let activeView = "overview";
let settingsRequest = 0;
let statusPollTimer = null;
let schedulerStatus = null;
let settingsControlSequence = 0;
let draftGuard = null;

function nextSettingsControlId() {
  settingsControlSequence += 1;
  return `zhiban-setting-${settingsControlSequence}`;
}

function syncTheme(context = window.AstrBotPluginView?.getContext?.()) {
  if (typeof context?.isDark === "boolean") {
    document.documentElement.dataset.theme = context.isDark ? "dark" : "light";
  } else if (!document.documentElement.dataset.theme) {
    document.documentElement.dataset.theme = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
  }
}

syncTheme();
window.AstrBotPluginView?.onContext?.(syncTheme);

function detachActiveFrame() {
  if (activeFrameReadyTimer) {
    clearTimeout(activeFrameReadyTimer);
    activeFrameReadyTimer = null;
  }
  if (typeof activeFrameDetach === "function") activeFrameDetach();
  activeFrameDetach = null;
  activeFrame = null;
}

function attachActiveFrame(frame, item) {
  activeFrame = frame;
  activeFrameDetach = window.ZhibanBridge?.attachFrame(frame, item.key, item.label) || null;
  activeFrameReadyTimer = setTimeout(() => {
    activeFrameReadyTimer = null;
    if (activeFrame !== frame || frame.dataset.bridgeReady === "true") return;
    detachActiveFrame();
    renderFrameLoadFailure(item);
  }, 12000);
}

function renderFrameLoadFailure(item) {
  const panel = document.createElement("article");
  panel.className = "module-note failed";
  const heading = document.createElement("h3");
  heading.textContent = `${item.label}功能页没有完成加载`;
  const copy = document.createElement("p");
  copy.textContent = "模块页面未返回初始化信号。请重试；若仍失败，请检查该模块状态与静态资源路由。";
  const actions = document.createElement("div");
  actions.className = "overview-actions";
  const retry = document.createElement("button");
  retry.className = "settings-button primary";
  retry.type = "button";
  retry.textContent = "重试加载";
  retry.addEventListener("click", () => renderActiveView());
  const settings = document.createElement("button");
  settings.className = "settings-button";
  settings.type = "button";
  settings.textContent = "打开配置";
  settings.addEventListener("click", () => setView("settings"));
  actions.append(retry, settings);
  panel.append(heading, copy, actions);
  workspace.replaceChildren(panel);
}

function statusLabel(value) {
  return ({ running: "运行中", failed: "启动失败", blocked: "冲突未加载", disabled: "已关闭", starting: "启动中", stopping: "停止中", stopped: "已停止" })[value] || "状态未知";
}

function readinessLabel(stateOrReadiness) {
  const value = typeof stateOrReadiness === "string"
    ? stateOrReadiness
    : stateOrReadiness?.state;
  return ({
    ready: "业务可用",
    not_ready: "业务未就绪",
    failed: "不可用",
    starting: "初始化中",
    disabled: "已关闭",
    unknown: "未检测",
  })[value] || "未检测";
}

function createModuleHero(item, state, kicker, copy) {
  const stateValue = typeof state === "string" ? state : state?.state;
  const hero = document.createElement("section");
  hero.className = "module-hero";
  const mark = document.createElement("img");
  mark.className = "module-hero-logo";
  mark.alt = "";
  mark.setAttribute("aria-hidden", "true");
  mark.dataset.moduleLogo = item.key;
  mark.src = item.logo || "./logo.png";
  mark.addEventListener("error", () => {
    if (mark.dataset.fallback) return;
    mark.dataset.fallback = "true";
    mark.src = "./logo.png";
  }, { once: true });
  const body = document.createElement("div");
  body.className = "module-hero-copy";
  const eyebrow = document.createElement("p");
  eyebrow.className = "module-hero-kicker";
  eyebrow.textContent = kicker;
  const heading = document.createElement("h3");
  heading.textContent = item.label;
  const description = document.createElement("p");
  description.className = "module-hero-description";
  description.textContent = copy || item.description;
  body.append(eyebrow, heading, description);
  const stateChip = document.createElement("span");
  stateChip.className = `state-chip ${stateValue || "unknown"}`;
  stateChip.textContent = statusLabel(stateValue);
  hero.append(mark, body, stateChip);
  return hero;
}

const ICON_PATHS = {
  overview: ["M3 3h7v7H3z", "M14 3h7v7h-7z", "M3 14h7v7H3z", "M14 14h7v7h-7z"],
  chat: ["M4 5h16v11H8l-4 4z", "M8 9h8", "M8 12h5"],
  memory: ["M9 4a3 3 0 0 1 6 0", "M7 7a3 3 0 0 0-2 5", "M17 7a3 3 0 0 1 2 5", "M8 18a4 4 0 0 1 0-8h8a4 4 0 0 1 0 8z"],
  creative: ["M12 3a9 9 0 1 0 0 18h1.5a2 2 0 0 0 0-4H12a2 2 0 0 1 0-4h4a5 5 0 0 0 0-10z", "M7.5 10h.01", "M9.5 6.5h.01", "M14 6.5h.01"],
  social: ["M4 18a8 8 0 1 1 16 0", "M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8"],
};

function createGroupIcon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  for (const pathData of ICON_PATHS[name] || ICON_PATHS.overview) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pathData);
    svg.append(path);
  }
  return svg;
}

function renderPrimaryNavigation() {
  primaryNav.replaceChildren(...GROUPS.map((group) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "primary-nav-item";
    button.dataset.group = group.key;
    button.setAttribute("aria-current", group.key === activeGroup ? "page" : "false");
    const label = document.createElement("span");
    label.textContent = group.label;
    button.append(createGroupIcon(group.key), label);
    button.addEventListener("click", () => selectGroup(group.key));
    return button;
  }));
}

function groupModules(groupKey = activeGroup) {
  return modules.filter((item) => item.groupKey === groupKey);
}

function moduleById(key) {
  return modules.find((item) => item.key === key) || modules[0];
}

function renderModuleTabs() {
  const entries = groupModules();
  if (activeGroup === "overview" || entries.length <= 1) {
    groupTabs.hidden = true;
    moduleTabs.replaceChildren();
    return;
  }
  groupTabs.hidden = false;
  moduleTabs.replaceChildren(...entries.map((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "module-tab";
    button.dataset.module = item.key;
    button.setAttribute("aria-pressed", String(item.key === activeKey));
    button.textContent = item.label;
    const state = moduleStates.get(item.key);
    button.title = `${item.label} · ${statusLabel(state?.state)} · ${readinessLabel(state)}`;
    button.addEventListener("click", () => selectModule(item.key, true));
    return button;
  }));
}

function renderNavigation() {
  renderPrimaryNavigation();
  renderModuleTabs();
}

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function readinessOf(state) {
  if (state?.readiness && typeof state.readiness === "object") return state.readiness;
  return { state: "unknown", label: "未检测", detail: "尚未取得业务就绪状态" };
}

function renderStatusTriplet(state, compact = false) {
  const root = element("div", compact ? "status-triplet compact" : "status-triplet");
  const readiness = readinessOf(state);
  const values = [
    ["启用", state?.enabled === false ? "已关闭" : state?.enabled === true ? "已启用" : "未获取", state?.enabled === false ? "disabled" : state?.enabled === true ? "ok" : "unknown"],
    ["运行", statusLabel(state?.state), state?.running ? "ok" : state?.state === "failed" || state?.state === "blocked" ? "danger" : "unknown"],
    ["业务", readinessLabel(readiness), readiness.state === "ready" ? "ok" : readiness.state === "failed" || readiness.state === "not_ready" ? "warn" : "unknown"],
  ];
  for (const [label, value, tone] of values) {
    const group = element("span", `status-part ${tone}`);
    const caption = element("span", "status-part-label", label);
    const text = element("strong", "", value);
    group.append(caption, text);
    if (compact) {
      caption.hidden = true;
      group.title = `${label}：${value}`;
    }
    if (!compact && label === "业务") group.title = readiness.detail || "";
    root.append(group);
  }
  return root;
}

function attentionItems() {
  const items = [];
  for (const item of modules) {
    const state = moduleStates.get(item.key);
    if (!state) continue;
    const readiness = readinessOf(state);
    if (!state.enabled) {
      items.push({ item, title: `${item.label}已关闭`, copy: "需要在全局设置中启用后才能参与业务流程。", view: "global" });
    } else if (state.state === "failed" || state.state === "blocked") {
      items.push({ item, title: `${item.label}启动异常`, copy: state.error || "请检查模块配置与 AstrBot 日志。", view: "settings" });
    } else if (readiness.state === "not_ready" || readiness.state === "failed") {
      items.push({ item, title: `${item.label}业务未就绪`, copy: readiness.detail || "需要完成模块配置。", view: "settings" });
    }
  }
  return items;
}

function renderGlobalOverview() {
  const root = element("div", "overview-page");
  const statesLoaded = moduleStates.size > 0;
  const running = [...moduleStates.values()].filter((state) => state.running).length;
  const ready = [...moduleStates.values()].filter((state) => readinessOf(state).state === "ready").length;
  const attention = attentionItems().length;
  const stats = element("section", "stats-grid");
  for (const [label, value, note] of [
    ["已启用模块", statesLoaded ? `${[...moduleStates.values()].filter((state) => state.enabled).length} / ${modules.length}` : "未获取", "配置状态"],
    ["正在运行", statesLoaded ? String(running) : "未获取", "生命周期状态"],
    ["业务就绪", statesLoaded ? String(ready) : "未检测", "完成启动检查"],
    ["需要关注", statesLoaded ? String(attention) : "未检测", "待办与连接问题"],
  ]) {
    const card = element("article", "stat-card");
    card.append(element("span", "muted", label), element("strong", "", value), element("small", "", note));
    stats.append(card);
  }

  const columns = element("div", "overview-columns");
  const todo = element("section", "panel");
  const todoHead = element("div", "panel-heading");
  todoHead.append(element("h3", "", "需要你看看"), element("span", "muted", "按实际状态生成"));
  todo.append(todoHead);
  const issues = attentionItems();
  if (!issues.length) {
    const empty = element("p", "empty-copy", statesLoaded ? "当前没有检测到待处理事项。" : "状态尚未读取，暂不显示待办结论。");
    todo.append(empty);
  } else {
    for (const issue of issues.slice(0, 5)) {
      const row = element("div", "list-row");
      const copy = element("div");
      copy.append(element("strong", "", issue.title), element("p", "", issue.copy));
      const open = element("button", "text-link", issue.view === "global" ? "去启用" : "去处理");
      open.type = "button";
      open.addEventListener("click", () => {
        if (issue.view === "global") setOverviewView("global");
        else openGroup(issue.item.groupKey, issue.item.key, "settings");
      });
      row.append(copy, open);
      todo.append(row);
    }
  }

  const shortcuts = element("section", "panel");
  shortcuts.append(element("h3", "", "常用功能"));
  for (const group of GROUPS.slice(1, 4)) {
    const row = element("div", "list-row");
    const copy = element("div");
    copy.append(element("strong", "", group.label), element("p", "", group.description));
    const open = element("button", "text-link", "打开");
    open.type = "button";
    open.addEventListener("click", () => selectGroup(group.key));
    row.append(copy, open);
    shortcuts.append(row);
  }
  columns.append(todo, shortcuts);

  const modulePanel = element("section", "panel module-status-panel");
  const moduleHead = element("div", "panel-heading");
  moduleHead.append(element("h3", "", "模块状态"), element("span", "muted", "启用 / 运行 / 业务"));
  modulePanel.append(moduleHead);
  for (const item of modules) {
    const state = moduleStates.get(item.key);
    const row = element("div", "status-row");
    const identity = element("div", "module-identity");
    const logo = element("img", "module-row-logo");
    logo.src = item.logo;
    logo.alt = "";
    logo.addEventListener("error", () => { logo.src = "./logo.png"; }, { once: true });
    const copy = element("div");
    copy.append(element("strong", "", item.label), element("p", "", item.description));
    identity.append(logo, copy);
    const open = element("button", "text-link", "打开");
    open.type = "button";
    open.setAttribute("aria-label", `打开${item.label}`);
    open.addEventListener("click", () => openGroup(item.groupKey, item.key, "workbench"));
    row.append(identity, renderStatusTriplet(state, true), open);
    modulePanel.append(row);
  }
  root.append(stats, columns, modulePanel);
  workspace.replaceChildren(root);
  refresh.disabled = false;
}

function createModuleFrameElement(item) {
  const frame = document.createElement("iframe");
  frame.className = "module-frame";
  frame.title = `${item.label}工作台`;
  frame.loading = "lazy";
  frame.referrerPolicy = "same-origin";
  const url = new URL(`modules/${item.page}/index.html`, document.baseURI);
  url.searchParams.set("embedded", "1");
  workspace.replaceChildren(frame);
  attachActiveFrame(frame, item);
  frame.src = url.href;
  refresh.disabled = false;
}

function renderProcessModule(item, state) {
  const page = element("div", "process-page");
  const snapshot = element("section", "panel process-summary");
  const head = element("div", "panel-heading");
  head.append(element("h3", "", item.label), renderStatusTriplet(state, true));
  const detail = element("p", "summary-copy", readinessOf(state).detail || "尚未取得业务就绪信息。");
  const help = element("p", "summary-copy", item.help || "该模块通过 AstrBot 消息事件、命令或 LLM 工具工作。");
  const actions = element("div", "action-row");
  const settings = element("button", "button primary", "配置模块");
  settings.type = "button";
  settings.addEventListener("click", () => setView("settings"));
  actions.append(settings);
  snapshot.append(head, detail, help, actions);
  const scheduler = item.groupKey === "chat" ? renderSchedulerSummary() : null;
  page.append(snapshot);
  if (scheduler) page.append(scheduler);
  workspace.replaceChildren(page);
  refresh.disabled = false;
}

function renderWorkbench(item = moduleById(activeKey)) {
  const state = moduleStates.get(item.key);
  if (item.page && (!state || state.state === "running")) {
    window.location.replace(new URL(`modules/${item.page}/index.html`, document.baseURI).href);
    return;
  }
  detachActiveFrame();
  settingsWorkspace.hidden = true;
  settingsWorkspace.replaceChildren();
  workspace.hidden = false;
  renderProcessModule(item, state);
}

function renderSchedulerSummary() {
  const section = element("section", "panel scheduler-summary");
  const header = element("div", "panel-heading");
  header.append(element("h3", "", "聊天调度"), element("span", "muted", "来自当前调度器"));
  const metrics = element("div", "mini-metrics");
  for (const [key, label] of [
    ["running", "处理中"], ["waiting", "等待中"], ["media_running", "媒体任务"], ["rejected", "拒绝数"],
  ]) {
    const tile = element("div", "mini-metric");
    const value = element("strong", "", "未获取");
    value.dataset.schedulerMetric = key;
    tile.append(element("span", "muted", label), value);
    metrics.append(tile);
  }
  section.append(header, metrics);
  updateSchedulerSummary(section);
  return section;
}

function renderFallback(item, state) {
  const section = document.createElement("article");
  section.className = `module-note ${state?.state || ""}`;
  const heading = document.createElement("h3");
  heading.textContent = state?.state === "failed" || state?.state === "blocked"
    ? "模块尚未就绪"
    : state?.state === "starting"
      ? "模块正在初始化"
      : state?.state === "disabled"
        ? "模块已关闭"
        : "功能说明";
  const copy = document.createElement("p");
  copy.className = ["failed", "blocked"].includes(state?.state) ? "error" : "";
  copy.textContent = state?.error
    ? `启动信息：${state.error}`
    : state?.detail || (state?.state === "disabled"
      ? "启用该模块并应用更改后，即可在消息流程中使用。"
      : item.help || "该模块通过 AstrBot 消息事件和 LLM 工具提供功能。");
  section.append(heading, copy);
  return section;
}

function countVisibleFields(schema) {
  return Object.values(schema || {}).reduce((count, definition) => {
    if (!definition || typeof definition !== "object" || definition.invisible === true) return count;
    if (definition.type === "object" && definition.items) return count + countVisibleFields(definition.items);
    return count + 1;
  }, 0);
}

function moduleSchema(schema) {
  const root = schema?.items && typeof schema.items === "object" ? schema.items : schema;
  if (root?.settings?.items && typeof root.settings.items === "object") return root.settings.items;
  if (schema?.settings?.items && typeof schema.settings.items === "object") return schema.settings.items;
  if (root?.items && typeof root.items === "object" && !root.enabled) return root.items;
  return root || {};
}

function enabledDefault(schema, fallback) {
  const root = schema?.items && typeof schema.items === "object" ? schema.items : schema;
  const value = root?.enabled?.default;
  return typeof value === "boolean" ? value : fallback;
}

function getAtPath(value, path) {
  return path.reduce((cursor, part) => cursor && typeof cursor === "object" ? cursor[part] : undefined, value);
}

function appendSettingsNodes(parent, schema, values, providers, config, path = [], depth = 0) {
  const byPath = config._fieldMap;
  let openedFirstRootGroup = false;

  for (const [key, definition] of Object.entries(schema || {})) {
    if (!definition || typeof definition !== "object") continue;
    if (definition.invisible === true) continue;
    const fieldPath = [...path, key];
    const field = byPath.get(fieldPath.join("."));
    if (field?.kind !== "secret" && !isSensitiveField(key, definition)
      && definition.type === "object" && definition.items && typeof definition.items === "object") {
      const details = document.createElement("details");
      details.className = "settings-group";
      details.open = depth === 0 && !openedFirstRootGroup;
      if (depth === 0) openedFirstRootGroup = true;
      const summary = document.createElement("summary");
      const groupTitle = document.createElement("span");
      groupTitle.className = "settings-group-title";
      groupTitle.textContent = definition.description || key;
      const groupCount = document.createElement("span");
      groupCount.className = "settings-group-count";
      groupCount.textContent = `${countVisibleFields(definition.items)} 项`;
      summary.append(groupTitle, groupCount);
      details.append(summary);
      if (definition.hint) {
        const hint = document.createElement("p");
        hint.className = "settings-hint";
        hint.textContent = definition.hint;
        details.append(hint);
      }
      const body = document.createElement("div");
      body.className = "settings-group-body";
      appendSettingsNodes(body, definition.items, values?.[key] || {}, providers, config, fieldPath, depth + 1);
      details.append(body);
      parent.append(details);
      continue;
    }

    const row = document.createElement("div");
    row.className = "settings-field";
    const label = document.createElement("label");
    label.className = "settings-label";
    const titleText = document.createElement("div");
    titleText.textContent = definition.description || key;
    label.append(titleText);
    if (definition.hint) {
      const hint = document.createElement("div");
      hint.className = "settings-hint";
      hint.textContent = definition.hint;
      label.append(hint);
    }

    if (field?.kind === "secret" || isSensitiveField(key, definition)) {
      const secretCell = document.createElement("div");
      secretCell.className = "settings-secret-cell";
      const input = document.createElement("input");
      input.className = "settings-input";
      input.id = nextSettingsControlId();
      label.htmlFor = input.id;
      input.type = "password";
      input.autocomplete = "new-password";
      input.placeholder = field?.configured ? "留空保持当前值" : "输入新密钥";
      input.dataset.secretPath = JSON.stringify(fieldPath);
      input.dataset.settingsPath = JSON.stringify(fieldPath);
      input.dataset.settingsType = "string";
      secretCell.append(input);

      const note = document.createElement("span");
      note.className = "settings-secret";
      note.textContent = field?.configured ? "已配置；值不会显示" : "未配置";
      secretCell.append(note);

      if (field?.configured) {
        const clear = document.createElement("button");
        clear.className = "settings-button secret-clear";
        clear.type = "button";
        clear.textContent = "清除密钥";
        clear.dataset.secretClearPath = secretPathList(config.secret_fields)
          .find((candidate) => normalizeSecretPath(candidate) === fieldPath.join(".")) || fieldPath.join(".");
        clear.addEventListener("click", () => {
          const marked = clear.getAttribute("aria-pressed") === "true";
          clear.setAttribute("aria-pressed", String(!marked));
          clear.textContent = marked ? "清除密钥" : "待清除";
          input.disabled = !marked;
        });
        input.addEventListener("input", () => {
          if (input.value.trim()) {
            clear.setAttribute("aria-pressed", "false");
            clear.textContent = "清除密钥";
            input.disabled = false;
          }
        });
        secretCell.append(clear);
      }
      row.append(label, secretCell);
      parent.append(row);
      continue;
    }

    let control;
    if (definition.type === "bool") {
      control = document.createElement("input");
      control.type = "checkbox";
      control.checked = Boolean(getAtPath(values, [key]));
    } else if (String(definition._special || "").startsWith("select_provider")
      || ["embedding_provider_id", "rerank_provider_id"].includes(key)) {
      const providerKind = definition._special === "select_provider_embedding" || key === "embedding_provider_id"
        ? "embedding"
        : definition._special === "select_provider_rerank" || key === "rerank_provider_id"
          ? "rerank"
          : "chat_completion";
      const visibleProviders = normalizeProviderOptions(providers, providerKind);
      const currentValue = String(getAtPath(values, [key]) ?? "");
      if (visibleProviders.length) {
        control = document.createElement("select");
        control.className = "settings-input";
        const choices = new Map(visibleProviders.map((provider) => [provider.id, provider.label]));
        if (currentValue && !choices.has(currentValue)) choices.set(currentValue, currentValue);
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "未选择";
        control.append(blank);
        for (const [id, label] of choices) {
          const option = document.createElement("option");
          option.value = id;
          option.textContent = label;
          control.append(option);
        }
        control.value = currentValue;
      } else {
        control = document.createElement("input");
        control.className = "settings-input";
        control.type = "text";
        control.value = currentValue;
      }
    } else if (Array.isArray(definition.options) && definition.options.length) {
      control = document.createElement("select");
      control.className = "settings-input";
      const currentValue = String(getAtPath(values, [key]) ?? "");
      const choices = [...new Set([currentValue, ...definition.options.map(String)].filter(Boolean))];
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "未选择";
      control.append(blank);
      for (const choice of choices) {
        const option = document.createElement("option");
        option.value = choice;
        option.textContent = choice;
        control.append(option);
      }
      control.value = currentValue;
    } else if (definition.type === "text" || definition.type === "list" || definition.type === "template_list" || definition.type === "dict") {
      control = document.createElement("textarea");
      control.className = "settings-input";
      const value = getAtPath(values, [key]);
      control.value = definition.type === "list" || definition.type === "template_list" || definition.type === "dict"
        ? JSON.stringify(value ?? (definition.type === "dict" ? {} : []), null, 2)
        : String(value ?? "");
    } else {
      control = document.createElement("input");
      control.className = "settings-input";
      control.type = definition.type === "int" || definition.type === "float" ? "number" : "text";
      if (definition.type === "int" || definition.type === "float") {
        const constraints = numericConstraints(definition);
        control.step = String(constraints.step);
        if (constraints.min !== null) control.min = String(constraints.min);
        if (constraints.max !== null) control.max = String(constraints.max);
        if (constraints.min !== null || constraints.max !== null) {
          const range = document.createElement("div");
          range.className = "settings-hint settings-range-hint";
          range.textContent = `范围：${constraints.min ?? "不限"} 至 ${constraints.max ?? "不限"}`;
          label.append(range);
        }
      }
      const value = getAtPath(values, [key]);
      control.value = value == null ? "" : String(value);
    }
    if (control.type !== "checkbox") control.classList.add("settings-input");
    control.id = nextSettingsControlId();
    label.htmlFor = control.id;
    control.dataset.settingsPath = JSON.stringify(fieldPath);
    control.dataset.settingsType = definition.type || "string";
    row.append(label, control);
    parent.append(row);
  }
}

function appendUnmappedSecrets(parent, config, fieldMap) {
  const known = new Set([...fieldMap.values()]
    .filter((field) => field.kind === "secret")
    .map((field) => field.path.join(".")));
  const configured = new Set(configuredSecretPathList(config.configured_secrets).map(normalizeSecretPath));
  for (const rawPath of secretPathList(config.secret_fields)) {
    const normalizedPath = normalizeSecretPath(rawPath);
    if (!normalizedPath || known.has(normalizedPath)) continue;
    const path = normalizedPath.split(".");
    const row = document.createElement("div");
    row.className = "settings-field";
    const label = document.createElement("label");
    label.className = "settings-label";
    label.textContent = path[path.length - 1];
    const controls = document.createElement("div");
    controls.className = "settings-secret-cell";
    const input = document.createElement("input");
    input.className = "settings-input";
    input.id = nextSettingsControlId();
    label.htmlFor = input.id;
    input.type = "password";
    input.autocomplete = "new-password";
    input.placeholder = configured.has(normalizedPath) ? "留空保持当前值" : "输入新密钥";
    input.dataset.secretPath = JSON.stringify(path);
    input.dataset.settingsPath = JSON.stringify(path);
    input.dataset.settingsType = "string";
    controls.append(input);
    const note = document.createElement("span");
    note.className = "settings-secret";
    note.textContent = configured.has(normalizedPath) ? "已配置；值不会显示" : "未配置";
    controls.append(note);
    if (configured.has(normalizedPath)) {
      const clear = document.createElement("button");
      clear.className = "settings-button secret-clear";
      clear.type = "button";
      clear.textContent = "清除密钥";
      clear.dataset.secretClearPath = rawPath;
      clear.addEventListener("click", () => {
        const marked = clear.getAttribute("aria-pressed") === "true";
        clear.setAttribute("aria-pressed", String(!marked));
        clear.textContent = marked ? "清除密钥" : "待清除";
        input.disabled = !marked;
      });
      input.addEventListener("input", () => {
        if (input.value.trim()) {
          clear.setAttribute("aria-pressed", "false");
          clear.textContent = "清除密钥";
          input.disabled = false;
        }
      });
      controls.append(clear);
    }
    row.append(label, controls);
    parent.append(row);
  }
}

function renderSettingsLoading(item, message = "读取模块配置…") {
  settingsWorkspace.replaceChildren();
  const panel = document.createElement("div");
  panel.className = "settings-panel";
  const text = document.createElement("p");
  text.className = "settings-message";
  text.textContent = message;
  panel.append(text);
  settingsWorkspace.append(panel);
}

function collectSettingsChanges(form, config, currentSettings) {
  const changes = {};
  for (const input of form.querySelectorAll("[data-settings-path]")) {
    const path = JSON.parse(input.dataset.settingsPath);
    if (input.dataset.secretPath) {
      if (input.disabled) continue;
      if (input.value.trim()) setValueAtPath(changes, path, input.value);
      continue;
    }
    const type = input.dataset.settingsType;
    const value = type === "bool" ? input.checked : parseFieldValue(input.value, type);
    const fieldDefinition = config._fieldMap.get(path.join("."))?.definition;
    validateNumericValue(value, fieldDefinition, fieldDefinition?.description || path[path.length - 1]);
    const previous = getAtPath(currentSettings, path);
    if (JSON.stringify(value) !== JSON.stringify(previous)) setValueAtPath(changes, path, value);
  }
  const clearSecrets = [...form.querySelectorAll('[data-secret-clear-path][aria-pressed="true"]')]
    .map((button) => button.dataset.secretClearPath)
    .filter((path) => !getAtPath(changes, normalizeSecretPath(path).split(".")));
  return { changes, clearSecrets };
}

async function applySavedModule(item, message, stateLabel) {
  try {
    stateLabel.className = "settings-message pending";
    stateLabel.textContent = "已保存，正在应用…";
    await callSettingsApi("POST", `ui/apply/${item.key}`, {});
    pendingApply.delete(item.key);
    await refreshStatus();
    await renderSettings(item.key, `${message}，配置已生效。`);
  } catch {
    stateLabel.className = "settings-message error";
    stateLabel.textContent = "应用失败：配置已保存但尚未生效。请查看模块状态和 AstrBot 日志后重试。";
  }
}

function renderSettingsEditor(item, config, savedMessage = "") {
  const schema = moduleSchema(config.schema);
  const currentSettings = config.settings && typeof config.settings === "object" ? config.settings : {};
  const panel = document.createElement("div");
  panel.className = "settings-panel";
  panel.append(createModuleHero(item, config.state, "模块配置", item.description));

  const statusBar = document.createElement("section");
  statusBar.className = "config-status-bar";
  const statusCopy = document.createElement("div");
  const statusTitle = document.createElement("strong");
  statusTitle.textContent = "模块状态";
  const statusHint = document.createElement("p");
  statusHint.textContent = "启停与跨模块资源在“总览 → 全局设置”统一管理；这里只编辑业务参数。";
  statusCopy.append(statusTitle, statusHint);
  statusBar.append(statusCopy, renderStatusTriplet(config.state || moduleStates.get(item.key)));

  const toolbar = document.createElement("div");
  toolbar.className = "settings-toolbar";
  const search = document.createElement("input");
  search.className = "settings-input settings-search";
  search.type = "search";
  search.placeholder = "搜索配置项";
  search.setAttribute("aria-label", "搜索配置项");
  toolbar.append(search);
  const reloadButton = element("button", "settings-button", "重新读取");
  reloadButton.type = "button";
  reloadButton.addEventListener("click", () => {
    if (draftGuard && !draftGuard()) return;
    draftGuard = null;
    void renderSettings(item.key);
  });
  const resetButton = element("button", "settings-button", "恢复默认");
  resetButton.type = "button";
  const saveButton = element("button", "settings-button", "仅保存");
  saveButton.type = "button";
  const saveApplyButton = element("button", "settings-button primary", "保存并应用");
  saveApplyButton.type = "button";
  const applyButton = element("button", "settings-button", config.requires_reload ? "" : "");
  applyButton.type = "button";
  applyButton.textContent = "应用已保存更改";
  applyButton.hidden = !config.requires_reload;
  toolbar.append(reloadButton, resetButton, saveButton, saveApplyButton, applyButton);

  const message = element("p", `settings-message${savedMessage.startsWith("错误") ? " error" : savedMessage ? " success" : ""}`, savedMessage);
  message.setAttribute("aria-live", "polite");
  let dirty = Boolean(savedMessage && savedMessage.includes("未保存"));
  const setDirty = (value, text) => {
    dirty = value;
    panel.classList.toggle("has-unsaved", dirty);
    if (!message.className.includes("error")) {
      message.className = `settings-message${dirty ? " pending" : savedMessage ? " success" : ""}`;
      message.textContent = text;
    }
  };
  draftGuard = () => !dirty || window.confirm("当前配置有未保存更改。放弃这些更改吗？");

  const form = document.createElement("form");
  form.className = "settings-form";
  form.addEventListener("submit", (event) => event.preventDefault());
  form.addEventListener("input", () => setDirty(true, "有未保存更改"));
  const secretFields = config.secret_fields || [];
  const configuredSecrets = config.configured_secrets || [];
  config._fieldMap = new Map(flattenSchema(schema, currentSettings, [], [], { secretFields, configuredSecrets })
    .map((field) => [field.path.join("."), field]));
  const intro = element("p", "settings-message", "基础配置优先展开。敏感值只显示配置状态，不会回显原值。");
  form.append(intro);
  appendSettingsNodes(form, schema, currentSettings, config.providers || {}, config, [], 0);
  appendUnmappedSecrets(form, config, config._fieldMap);

  search.addEventListener("input", () => {
    const query = search.value.trim().toLocaleLowerCase("zh-CN");
    for (const field of form.querySelectorAll(".settings-field")) {
      field.hidden = Boolean(query) && !field.textContent.toLocaleLowerCase("zh-CN").includes(query);
    }
    for (const group of form.querySelectorAll(".settings-group")) {
      const hasVisible = [...group.querySelectorAll(".settings-field")].some((field) => !field.hidden);
      group.hidden = Boolean(query) && !hasVisible && !group.querySelector("summary")?.textContent.toLocaleLowerCase("zh-CN").includes(query);
      if (query && hasVisible) group.open = true;
    }
  });

  const submit = async (applyAfterSave) => {
    if (!form.reportValidity()) return;
    let collected;
    try {
      collected = collectSettingsChanges(form, config, currentSettings);
    } catch (error) {
      message.className = "settings-message error";
      message.textContent = `错误：${error?.message || "请检查数字和 JSON 数组／对象。"}`;
      return;
    }
    if (!collected.changes || Object.keys(collected.changes).length === 0 && collected.clearSecrets.length === 0) {
      message.className = "settings-message";
      message.textContent = "没有待保存的修改。";
      if (config.requires_reload && applyAfterSave) await applySavedModule(item, "已保存的配置", message);
      return;
    }
    saveButton.disabled = true;
    saveApplyButton.disabled = true;
    const activeButton = applyAfterSave ? saveApplyButton : saveButton;
    activeButton.textContent = applyAfterSave ? "保存中…" : "保存中…";
    try {
      const result = await saveSettings(item, config, collected.changes, config.enabled, collected.clearSecrets);
      dirty = false;
      if (applyAfterSave) {
        await applySavedModule(item, "配置已保存", message);
      } else {
        await renderSettings(item.key, result?.requires_reload ? "已保存，待应用。" : "已保存，配置已生效。");
      }
    } catch {
      message.className = "settings-message error";
      message.textContent = "保存失败：配置冲突或服务异常。当前编辑仍保留在页面中，请重新读取后比较修改。";
      saveButton.disabled = false;
      saveApplyButton.disabled = false;
      activeButton.textContent = applyAfterSave ? "保存并应用" : "仅保存";
    }
  };

  resetButton.addEventListener("click", async () => {
    if (!window.confirm(`将${item.label}的非敏感业务设置恢复为默认值？模块启用状态不会改变。`)) return;
    resetButton.disabled = true;
    resetButton.textContent = "恢复中…";
    try {
      await saveSettings(item, config, buildDefaultValues(schema, secretFields), config.enabled, []);
      await renderSettings(item.key, "已恢复默认值，待应用。");
    } catch {
      message.className = "settings-message error";
      message.textContent = "恢复默认失败，请重新读取后重试。";
    } finally {
      resetButton.disabled = false;
      resetButton.textContent = "恢复默认";
    }
  });
  saveButton.addEventListener("click", () => void submit(false));
  saveApplyButton.addEventListener("click", () => void submit(true));
  applyButton.addEventListener("click", () => void applySavedModule(item, "已保存的配置", message));

  panel.append(statusBar, toolbar, message, form);
  settingsWorkspace.replaceChildren(panel);
}

function renderDedicatedSettings(item, config) {
  const panel = element("div", "settings-panel");
  panel.append(createModuleHero(item, config.state, "模块配置", item.description));
  const notice = element("section", "panel");
  notice.append(
    element("h3", "", "专用配置"),
    element("p", "summary-copy", item.key === "brush"
      ? "图片供应商、画风和创作参数由现有图片工作台管理。可以从工作台打开专用配置。"
      : "音乐账号与登录状态由现有音乐工作台管理。可以从工作台打开专用配置。"),
  );
  const actions = element("div", "action-row");
  const open = element("button", "button primary", "打开专用工作台");
  open.type = "button";
  open.addEventListener("click", () => setView("workbench"));
  actions.append(open);
  notice.append(actions);
  panel.append(notice);
  settingsWorkspace.replaceChildren(panel);
}


function renderGlobalSettingsLoading() {
  detachActiveFrame();
  workspace.hidden = true;
  workspace.replaceChildren();
  settingsWorkspace.hidden = false;
  settingsWorkspace.replaceChildren(element("p", "settings-message", "读取全局设置…"));
}

async function renderGlobalSettings(savedMessage = "") {
  renderGlobalSettingsLoading();
  const requestId = ++settingsRequest;
  refresh.disabled = true;
  try {
    const data = await callSettingsApi("GET", "ui/global");
    if (requestId !== settingsRequest || activeView !== "global") return;
    const current = data.settings && typeof data.settings === "object" ? data.settings : {};
    const schema = data.schema?.items && typeof data.schema.items === "object" ? data.schema.items : {};
    const panel = element("div", "settings-panel");
    const message = element("p", `settings-message${savedMessage.startsWith("错误") ? " error" : savedMessage ? " success" : ""}`, savedMessage);
    message.setAttribute("aria-live", "polite");
    const form = element("form", "settings-form");
    const resourcePanel = element("section", "panel settings-block");
    resourcePanel.append(element("h3", "", "调度与资源"));
    const fields = element("div", "form-grid");
    const definitions = [
      ["queue_limit", "聊天等待总数", "所有会话合计的等待消息上限", 1, 100],
      ["session_queue_limit", "单会话等待数", "同一会话允许等待的消息上限", 1, 10],
      ["wait_seconds", "聊天等待上限", "等待资源的最长秒数", 1, 600],
    ];
    const controls = new Map();
    for (const [key, label, hint, min, max] of definitions) {
      const field = element("label", "form-field");
      field.append(element("span", "field-label", label));
      const input = element("input", "settings-input");
      input.type = "number";
      input.min = String(min);
      input.max = String(max);
      input.value = String(current[key] ?? schema[key]?.default ?? "");
      input.dataset.globalPath = key;
      field.append(input, element("small", "", hint));
      controls.set(key, input);
      fields.append(field);
    }
    resourcePanel.append(fields);
    form.append(resourcePanel);

    const modulePanel = element("section", "panel settings-block");
    modulePanel.append(element("h3", "", "模块启停"));
    const moduleHint = element("p", "summary-copy", "开关只改变启用意图；点击保存并应用后才变更运行实例。业务配置仍在各模块页面编辑。");
    modulePanel.append(moduleHint);
    const enabledInputs = new Map();
    for (const module of data.modules || []) {
      const row = element("div", "module-toggle-row");
      const identity = element("div", "module-identity");
      const logo = element("img", "module-row-logo");
      logo.src = moduleById(module.key).logo;
      logo.alt = "";
      const text = element("div");
      text.append(element("strong", "", module.label), element("p", "", moduleStates.get(module.key)?.readiness?.detail || "尚未取得业务就绪信息"));
      identity.append(logo, text);
      const toggle = element("label", "switch-field");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(module.enabled);
      checkbox.dataset.moduleKey = module.key;
      checkbox.dataset.moduleRevision = module.revision;
      const slider = element("span", "switch-track");
      const value = element("span", "switch-label", module.enabled ? "已启用" : "已关闭");
      checkbox.addEventListener("change", () => {
        value.textContent = checkbox.checked ? "已启用" : "已关闭";
        setDirty("有未保存更改");
      });
      toggle.append(checkbox, slider, value);
      enabledInputs.set(module.key, { checkbox, revision: module.revision, initial: Boolean(module.enabled) });
      row.append(identity, renderStatusTriplet(moduleStates.get(module.key), true), toggle);
      modulePanel.append(row);
    }
    form.append(modulePanel);

    let dirty = false;
    const setDirty = (text) => {
      dirty = true;
      if (!message.className.includes("error")) {
        message.className = "settings-message pending";
        message.textContent = text;
      }
    };
    for (const input of controls.values()) input.addEventListener("input", () => setDirty("有未保存更改"));
    draftGuard = () => !dirty || window.confirm("全局设置有未保存更改。放弃这些更改吗？");

    const savebar = element("div", "save-bar");
    const stateText = element("span", "save-state", "当前无未保存更改");
    stateText.dataset.saveState = "clean";
    const buttons = element("div", "action-row");
    const saveOnly = element("button", "button", "仅保存");
    saveOnly.type = "button";
    const saveApply = element("button", "button primary", "保存并应用");
    saveApply.type = "button";
    buttons.append(saveOnly, saveApply);
    savebar.append(stateText, buttons);
    form.append(savebar);

    const submit = async (apply) => {
      if (!form.reportValidity()) return;
      const changes = {};
      for (const [key, input] of controls) {
        const value = Number(input.value);
        const previous = Number(current[key]);
        if (value !== previous) changes[key] = value;
      }
      const moduleUpdates = {};
      for (const [key, entry] of enabledInputs) {
        if (entry.checkbox.checked !== entry.initial) {
          moduleUpdates[key] = { enabled: entry.checkbox.checked, revision: entry.revision };
        }
      }
      if (!Object.keys(changes).length && !Object.keys(moduleUpdates).length) {
        stateText.textContent = "没有待保存的修改";
        message.className = "settings-message";
        message.textContent = "没有待保存的修改。";
        return;
      }
      saveOnly.disabled = true;
      saveApply.disabled = true;
      stateText.textContent = apply ? "正在保存并应用…" : "正在保存…";
      try {
        const result = await callSettingsApi("POST", "ui/global", {
          revision: data.revision,
          changes,
          modules: moduleUpdates,
          apply: Boolean(apply),
        });
        dirty = false;
        if (result?.failures?.length) throw new Error(result.failures[0].message || "部分模块应用失败");
        await refreshStatus();
        await renderGlobalSettings(apply ? "已保存并应用。" : "已保存，待应用。");
      } catch (error) {
        message.className = "settings-message error";
        message.textContent = `错误：${error?.message || "保存或应用失败"}。当前编辑仍保留，请重新读取后比较修改。`;
        stateText.textContent = "保存或应用失败";
        saveOnly.disabled = false;
        saveApply.disabled = false;
      }
    };
    saveOnly.addEventListener("click", () => void submit(false));
    saveApply.addEventListener("click", () => void submit(true));
    form.addEventListener("submit", (event) => event.preventDefault());
    panel.append(message, form);
    settingsWorkspace.replaceChildren(panel);
    refresh.disabled = false;
  } catch {
    if (requestId !== settingsRequest) return;
    const fallback = element("div", "empty-state");
    fallback.append(
      element("h3", "", "无法读取全局设置"),
      element("p", "error", "请检查 Dashboard 登录态与知伴模块状态；敏感值不会出现在错误信息中。"),
    );
    settingsWorkspace.replaceChildren(fallback);
  }
  settingsRequest = Math.max(settingsRequest, requestId);
  refresh.disabled = false;
}

async function callSettingsApi(method, endpoint, payload) {
  const bridge = window.ZhibanBridge;
  if (!bridge || typeof bridge.apiGet !== "function" || typeof bridge.apiPost !== "function") {
    throw new Error("plugin page bridge unavailable");
  }
  const result = method === "GET"
    ? await bridge.apiGet(endpoint)
    : await bridge.apiPost(endpoint, payload || {});
  return unwrapApiPayload(result);
}

async function saveSettings(item, config, changes, enabled, clearSecrets) {
  const payload = buildConfigSavePayload(config.revision, enabled, changes, clearSecrets);
  const result = await callSettingsApi("POST", `ui/config/${item.key}`, payload);
  if (result?.requires_reload) pendingApply.add(item.key);
  else pendingApply.delete(item.key);
  return result;
}

async function renderSettings(key, message = "") {
  const item = modules.find((entry) => entry.key === key) || modules[0];
  const requestId = ++settingsRequest;
  detachActiveFrame();
  workspace.replaceChildren();
  workspace.hidden = true;
  settingsWorkspace.hidden = false;
  settingsWorkspace.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "settings-message";
  loading.textContent = "读取模块配置…";
  settingsWorkspace.append(loading);
  refresh.disabled = true;
  try {
    const config = await callSettingsApi("GET", `ui/config/${item.key}`);
    if (requestId !== settingsRequest || activeView !== "settings" || activeKey !== item.key) return;
    config.state = { ...(config.state || {}), ...(moduleStates.get(item.key) || {}) };
    config.requires_reload = Boolean(config.requires_reload || pendingApply.has(item.key));
    const schema = moduleSchema(config.schema);
    if (!Object.keys(schema || {}).length && config.has_dedicated_page && ["brush", "music"].includes(item.key) && item.page) {
      renderDedicatedSettings(item, config);
    } else if (!Object.keys(schema || {}).length) {
      const fallback = document.createElement("div");
      fallback.className = "empty-state";
      const heading = document.createElement("h3");
      heading.textContent = "此模块暂未提供网页配置表单";
      const copy = document.createElement("p");
      copy.textContent = "请在 AstrBot → 插件 → 知伴 中编辑该模块设置。配置读取和保存需要受保护的模块接口。";
      fallback.append(heading, copy);
      settingsWorkspace.replaceChildren(fallback);
    } else {
      renderSettingsEditor(item, config, message);
    }
  } catch {
    if (requestId !== settingsRequest) return;
    const fallback = document.createElement("div");
    fallback.className = "empty-state";
    const heading = document.createElement("h3");
    heading.textContent = "无法读取模块配置";
    const copy = document.createElement("p");
    copy.className = "error";
    copy.textContent = "请刷新页面或检查该模块状态；敏感配置不会显示在错误信息中。";
    fallback.append(heading, copy);
    settingsWorkspace.replaceChildren(fallback);
  } finally {
    if (requestId === settingsRequest) refresh.disabled = false;
  }
}

function applyHeader() {
  const group = GROUPS.find((item) => item.key === activeGroup) || GROUPS[0];
  breadcrumbGroup.textContent = group.label;
  const item = moduleById(activeKey);
  const state = moduleStates.get(item.key);
  overviewTabs.hidden = activeGroup !== "overview";
  for (const button of overviewTabs.querySelectorAll("button[data-overview-view]")) {
    button.setAttribute("aria-pressed", String(button.dataset.overviewView === (activeView === "global" ? "global" : "overview")));
  }
  groupTabs.hidden = activeGroup === "overview" || groupModules().length <= 1;
  if (activeGroup === "overview") {
    breadcrumbPage.textContent = activeView === "global" ? "全局设置" : "运行总览";
    title.textContent = activeView === "global" ? "全局设置" : "今天的知伴";
    description.textContent = activeView === "global" ? "跨模块调度、资源上限与模块启停。" : "运行状态、待办与常用功能集中在这里。";
    const attention = attentionItems().length;
    status.textContent = moduleStates.size ? `${moduleStates.size} 个模块 · ${attention} 项关注` : "读取状态…";
    status.className = `status ${attention ? "warning" : moduleStates.size ? "running" : ""}`;
    configButton.hidden = true;
    backButton.hidden = true;
    return;
  }
  breadcrumbPage.textContent = activeView === "settings" ? `${item.label}配置` : group.label;
  title.textContent = activeView === "settings" ? item.label : group.label;
  description.textContent = activeView === "settings" ? item.description : group.description;
  const readiness = readinessOf(state);
  status.textContent = `${statusLabel(state?.state)} · ${readinessLabel(readiness)}`;
  status.className = `status ${state?.state === "running" ? "running" : state?.state || readiness.state || ""}`;
  configButton.hidden = false;
  configButton.textContent = activeView === "settings" ? "返回工作台" : "配置";
  configButton.disabled = false;
  configButton.onclick = () => setView(activeView === "settings" ? "workbench" : "settings");
  backButton.hidden = true;
}

function setOverviewView(view) {
  if (draftGuard && !draftGuard()) return;
  draftGuard = null;
  activeGroup = "overview";
  activeView = view === "global" ? "global" : "overview";
  history.replaceState(null, "", `?group=overview&view=${activeView}`);
  renderNavigation();
  applyHeader();
  renderActiveView();
  scheduleStatusPoll();
}

function openGroup(groupKey, key = "", view = "workbench") {
  if (draftGuard && !draftGuard()) return;
  draftGuard = null;
  const group = GROUPS.find((item) => item.key === groupKey);
  if (!group) return;
  activeGroup = groupKey;
  const entries = groupModules(groupKey);
  activeKey = entries.some((item) => item.key === key) ? key : entries[0]?.key || "heart";
  activeView = view === "settings" ? "settings" : "workbench";
  document.documentElement.dataset.module = activeKey;
  const url = new URL(window.location.href);
  url.searchParams.set("group", activeGroup);
  url.searchParams.set("module", activeKey);
  url.searchParams.set("view", activeView);
  url.hash = "";
  history.replaceState(null, "", url);
  renderNavigation();
  applyHeader();
  renderActiveView();
  scheduleStatusPoll();
}

function selectGroup(groupKey) {
  if (groupKey === "overview") setOverviewView("overview");
  else openGroup(groupKey, "", "workbench");
}

function selectModule(key, updateUrl = true) {
  const item = modules.find((entry) => entry.key === key) || modules[0];
  if (draftGuard && !draftGuard()) return;
  draftGuard = null;
  activeKey = item.key;
  activeGroup = item.groupKey;
  activeView = "workbench";
  document.documentElement.dataset.module = item.key;
  if (updateUrl) {
    const url = new URL(window.location.href);
    url.searchParams.set("group", activeGroup);
    url.searchParams.set("module", activeKey);
    url.searchParams.set("view", activeView);
    url.hash = "";
    history.replaceState(null, "", url);
  }
  renderNavigation();
  applyHeader();
  renderActiveView();
  scheduleStatusPoll();
}

function cancelPendingFrames() {
  settingsRequest += 1;
  detachActiveFrame();
  settingsWorkspace.hidden = true;
  settingsWorkspace.replaceChildren();
  workspace.hidden = false;
}

function setView(view) {
  if (draftGuard && !draftGuard()) return;
  draftGuard = null;
  if (view === "overview" || view === "global") {
    setOverviewView(view === "global" ? "global" : "overview");
    return;
  }
  if (activeGroup === "overview") activeGroup = moduleById(activeKey).groupKey;
  activeView = view === "settings" ? "settings" : "workbench";
  const url = new URL(window.location.href);
  url.searchParams.set("group", activeGroup);
  url.searchParams.set("module", activeKey);
  url.searchParams.set("view", activeView);
  history.replaceState(null, "", url);
  renderNavigation();
  applyHeader();
  renderActiveView();
  scheduleStatusPoll();
}

function renderActiveView() {
  cancelPendingFrames();
  if (activeView === "overview") {
    renderGlobalOverview();
    return;
  }
  if (activeView === "global") {
    void renderGlobalSettings();
    return;
  }
  if (activeView === "settings") {
    void renderSettings(activeKey);
    return;
  }
  renderWorkbench(moduleById(activeKey));
}

function stateSnapshot(state) {
  return JSON.stringify(state ?? null);
}

function scheduleStatusPoll() {
  if (statusPollTimer) {
    clearTimeout(statusPollTimer);
    statusPollTimer = null;
  }
  if (document.visibilityState === "hidden" || activeView === "settings" || activeView === "global") return;
  const hasStarting = [...moduleStates.values()].some((item) => ["starting", "stopping"].includes(item.state));
  statusPollTimer = setTimeout(() => {
    statusPollTimer = null;
    void refreshStatus({ background: true });
  }, hasStarting ? 1500 : 5000);
}

async function refreshStatus({ background = false } = {}) {
  if (document.visibilityState === "hidden") return;
  try {
    const data = await callSettingsApi("GET", "ui/status");
    schedulerStatus = data.scheduler || null;
    const previousStates = new Map(moduleStates);
    const previousOrder = modules.map((item) => item.key).join("|");
    const nextModules = orderModules(moduleCatalog, data.menu_order);
    const nextStates = new Map((data.modules || []).map((item) => [item.key, item]));
    const changedKeys = new Set();
    for (const key of new Set([...previousStates.keys(), ...nextStates.keys()])) {
      if (stateSnapshot(previousStates.get(key)) !== stateSnapshot(nextStates.get(key))) changedKeys.add(key);
    }
    modules = nextModules;
    moduleStates.clear();
    for (const [key, item] of nextStates) moduleStates.set(key, item);
    const orderChanged = previousOrder !== modules.map((item) => item.key).join("|");
    if (orderChanged || changedKeys.size) renderNavigation();
    applyHeader();
    const activeItem = moduleById(activeKey);
    const previousLifecycle = previousStates.get(activeItem.key)?.state;
    const currentLifecycle = moduleStates.get(activeItem.key)?.state;
    if (activeView === "overview" && (!background || changedKeys.size)) {
      renderGlobalOverview();
    } else if (activeView === "workbench" && changedKeys.has(activeItem.key)
      && previousLifecycle !== currentLifecycle) {
      renderWorkbench(activeItem);
    } else if (activeView === "workbench" && activeItem.groupKey === "chat") {
      updateSchedulerSummary();
    }
    scheduleStatusPoll();
  } catch {
    status.textContent = "状态读取失败";
    status.className = "status failed";
    if (activeView === "overview") {
      workspace.replaceChildren(element("p", "empty-state error", "无法读取运行状态。请刷新页面或检查 Dashboard 登录态。"));
    }
    scheduleStatusPoll();
  }
}

function updateSchedulerSummary(root = settingsWorkspace) {
  for (const node of root.querySelectorAll("[data-scheduler-metric]")) {
    const key = node.dataset.schedulerMetric;
    const value = schedulerStatus?.[key];
    node.textContent = value == null
      ? "未获取"
      : key === "media_running" ? (value ? "占用" : "空闲") : String(value);
  }
}

refresh.addEventListener("click", () => {
  if (activeView === "overview") void refreshStatus();
  else if (activeView === "global") void renderGlobalSettings();
  else if (activeView === "settings") void renderSettings(activeKey);
  else if (activeFrame) activeFrame.src = activeFrame.src;
  else void refreshStatus();
});
overviewTabs.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-overview-view]");
  if (button) setOverviewView(button.dataset.overviewView);
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    if (statusPollTimer) clearTimeout(statusPollTimer);
    statusPollTimer = null;
    if (activeFrame) activeFrame.dataset.paused = "true";
  } else {
    if (activeFrame) activeFrame.dataset.paused = "false";
    void refreshStatus({ background: true });
  }
});
window.addEventListener("pagehide", () => {
  detachActiveFrame();
  if (statusPollTimer) clearTimeout(statusPollTimer);
  statusPollTimer = null;
});

const initialParams = new URLSearchParams(location.search);
const requestedGroup = initialParams.get("group");
const requestedModule = initialParams.get("module") || location.hash.slice(1);
const requestedView = initialParams.get("view");
if (requestedGroup === "overview") {
  activeGroup = "overview";
  activeView = requestedView === "global" ? "global" : "overview";
} else {
  const initialItem = moduleById(requestedModule || "memory");
  activeKey = initialItem.key;
  activeGroup = GROUPS.some((group) => group.key === requestedGroup) ? requestedGroup : initialItem.groupKey;
  activeView = requestedView === "settings" ? "settings" : "workbench";
}
renderNavigation();
applyHeader();
renderActiveView();
void refreshStatus();
