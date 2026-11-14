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
  { key: "heart", label: "聊天互动", logo: "./logos/heart.png", description: "群聊接话、唤醒与私聊上下文", group: "聊天系统", page: "heart", plugin: "astrbot_plugin_angel_heart" },
  { key: "memory", label: "记忆成长", logo: "./logos/memory.png", description: "长期记忆、知识检索与人格审批", page: "memory", plugin: "astrbot_plugin_livingmemory" },
  { key: "meme", label: "表情互动", logo: "./logos/meme.png", description: "服务器图库检索、管理与发送", page: "meme", plugin: "astrbot_plugin_meme_manager" },
  { key: "tts", label: "语音回复", logo: "./logos/tts.png", description: "BreezeBlue 语音合成、音色与回复策略", page: "tts", plugin: "astrbot_plugin_breeze_tts" },
  { key: "proactive", label: "主动问候", logo: "./logos/proactive.png", description: "按现有私聊策略进行主动问候", group: "聊天系统", help: "主动问候由后台调度器执行。启用范围与调度参数可在知伴插件设置的「主动问候」分组中查看。" },
  { key: "brush", label: "图片创作", logo: "./logos/brush.png", description: "生图、改图与供应商配置", page: "brush", plugin: "astrbot_plugin_angel_brush" },
  { key: "music", label: "音乐点播", logo: "./logos/music.png", description: "Bilibili 搜索、账号与音频发送", page: "music", plugin: "astrbot_plugin_listen_music" },
  { key: "eye", label: "历史查询", logo: "./logos/eye.png", description: "群记录检索与分页查询", group: "聊天系统", help: "通过原有历史查询命令或 LLM 工具检索记录；SnowLuma 版本与分页模式在知伴插件设置中配置。" },
  { key: "qzone", label: "QQ 动态", logo: "./logos/qzone.png", description: "QQ 空间动态浏览、发布与互动工具", group: "QQ 社交", page: "qzone", plugin: "astrbot_plugin_qzone_ultra" },
  { key: "filter", label: "内容过滤", logo: "./logos/filter.svg", description: "按规则处理消息中的链接", group: "聊天系统", help: "内容过滤由消息发送流程自动执行；白名单域名和启用状态在知伴插件设置的「内容过滤」分组中配置。" },
  { key: "qqprofile", label: "QQ 资料", logo: "./logos/qqprofile.png", description: "QQ 状态、签名、昵称与头像管理", group: "QQ 社交", help: "通过 OneBot 管理员命令或受权限限制的模型工具管理资料，例如“设置状态 忙碌”“设置签名 …”。可选开启昵称与人格名同步。" },
];
let modules = moduleCatalog;

const nav = document.querySelector("#moduleNav");
const title = document.querySelector("#moduleTitle");
const description = document.querySelector("#moduleDescription");
const status = document.querySelector("#moduleStatus");
const workspace = document.querySelector("#moduleWorkspace");
const settingsWorkspace = document.querySelector("#settingsWorkspace");
const refresh = document.querySelector("#refreshModule");
const showOverviewView = document.querySelector("#showOverviewView");
const showModuleView = document.querySelector("#showModuleView");
const showSettingsView = document.querySelector("#showSettingsView");
const moduleStates = new Map();
const pendingApply = new Set();
let activeKey = "heart";
let activeFrame = null;
let activeFrameDetach = null;
let activeFrameReadyTimer = null;
let activeView = "module";
let settingsRequest = 0;
let statusPollTimer = null;
let settingsControlSequence = 0;

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
  return ({ running: "运行中", failed: "启动失败", blocked: "冲突未加载", disabled: "已关闭", starting: "启动中" })[value] || "状态未知";
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

function renderNavigation() {
  nav.replaceChildren(...modules.map((item, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "nav-item";
    button.dataset.module = item.key;
    button.setAttribute("aria-current", item.key === activeKey ? "page" : "false");
    const number = document.createElement("span");
    number.className = "nav-number";
    number.textContent = String(index + 1).padStart(2, "0");
    const logo = document.createElement("img");
    logo.className = "nav-logo";
    logo.src = item.logo || "./logo.png";
    logo.alt = "";
    logo.setAttribute("aria-hidden", "true");
    logo.addEventListener("error", () => { logo.src = "./logo.png"; }, { once: true });
    const label = document.createElement("span");
    label.className = "nav-title";
    label.textContent = item.label;
    let category = null;
    if (item.group) {
      category = document.createElement("span");
      category.className = "nav-category";
      category.textContent = item.group;
      button.classList.add("has-group");
    }
    const dot = document.createElement("span");
    dot.className = `nav-state ${moduleStates.get(item.key)?.state || ""}`;
    dot.setAttribute("aria-hidden", "true");
    button.title = `${item.label} · ${statusLabel(moduleStates.get(item.key)?.state)}`;
    button.append(number, logo, label);
    if (category) button.append(category);
    button.append(dot);
    button.addEventListener("click", () => selectModule(item.key, true));
    return button;
  }));
}

function moduleCapabilities(item) {
  return [...new Set(String(item.description || "").split(/[、，；与]/).map((part) => part.trim()).filter(Boolean))];
}

function renderRelatedModules(item) {
  const related = modules.filter((entry) => entry.group === item.group);
  if (!item.group || related.length < 2) return null;
  const section = document.createElement("section");
  section.className = "overview-section related-modules";
  const header = document.createElement("div");
  header.className = "overview-section-heading";
  const title = document.createElement("h3");
  title.textContent = item.group;
  const lead = document.createElement("p");
  lead.textContent = item.group === "聊天系统"
    ? "回复、主动消息、历史检索和过滤共用一个入口；每项仍保留原触发方式与独立配置。"
    : "空间动态与 QQ 资料在同一入口管理，操作仍按原模块权限执行。";
  header.append(title, lead);
  const grid = document.createElement("div");
  grid.className = "related-module-grid";
  for (const member of related) {
    const card = document.createElement("article");
    card.className = "related-module-card";
    const logo = document.createElement("img");
    logo.className = "related-module-logo";
    logo.src = member.logo || "./logo.png";
    logo.alt = "";
    logo.setAttribute("aria-hidden", "true");
    logo.addEventListener("error", () => { logo.src = "./logo.png"; }, { once: true });
    const content = document.createElement("div");
    content.className = "related-module-content";
    const name = document.createElement("strong");
    name.textContent = member.label;
    const description = document.createElement("p");
    description.textContent = member.description;
    const state = document.createElement("span");
    state.className = "related-module-state " + (moduleStates.get(member.key)?.state || "unknown");
    state.textContent = statusLabel(moduleStates.get(member.key)?.state);
    content.append(name, description, state);
    const actions = document.createElement("div");
    actions.className = "related-module-actions";
    const feature = document.createElement("button");
    feature.type = "button";
    feature.className = "settings-button primary";
    feature.textContent = member.page ? "打开功能" : "查看说明";
    feature.addEventListener("click", () => {
      selectModule(member.key, true);
      setView(member.page ? "module" : "overview");
    });
    const settings = document.createElement("button");
    settings.type = "button";
    settings.className = "settings-button";
    settings.textContent = "配置";
    settings.addEventListener("click", () => {
      selectModule(member.key, true);
      setView("settings");
    });
    actions.append(feature, settings);
    card.append(logo, content, actions);
    grid.append(card);
  }
  section.append(header, grid);
  return section;
}

function createModuleFrame(item, titleText = item.label) {
  const button = document.createElement("button");
  button.className = "settings-button primary";
  button.type = "button";
  button.textContent = titleText;
  button.addEventListener("click", () => openModulePage(item));
  return button;
}

function renderFunctionSummary(item, state) {
  const summary = document.createElement("section");
  summary.className = `function-summary ${state?.state || ""}`;
  const main = document.createElement("div");
  main.className = "function-summary-main";
  const logo = document.createElement("img");
  logo.className = "function-summary-logo";
  logo.alt = "";
  logo.setAttribute("aria-hidden", "true");
  logo.dataset.moduleLogo = item.key;
  logo.src = item.logo || "./logo.png";
  logo.addEventListener("error", () => {
    if (logo.dataset.fallback) return;
    logo.dataset.fallback = "true";
    logo.src = "./logo.png";
  }, { once: true });
  const labelGroup = document.createElement("div");
  labelGroup.className = "function-summary-label";
  const kicker = document.createElement("p");
  kicker.className = "function-summary-kicker";
  kicker.textContent = "功能速览";
  const capabilities = document.createElement("div");
  capabilities.className = "capability-chips";
  for (const tag of moduleCapabilities(item)) {
    const chip = document.createElement("span");
    chip.className = "capability-chip";
    chip.textContent = tag;
    capabilities.append(chip);
  }
  labelGroup.append(kicker);
  main.append(logo, labelGroup, capabilities);

  const meta = document.createElement("div");
  meta.className = "function-summary-meta";
  for (const [label, value] of [["事件处理器", state?.handlers ?? 0], ["LLM 工具", state?.tools ?? 0]]) {
    const metric = document.createElement("div");
    metric.className = "function-metric";
    const number = document.createElement("strong");
    number.textContent = String(value);
    const caption = document.createElement("span");
    caption.textContent = label;
    metric.append(number, caption);
    meta.append(metric);
  }
  const settings = document.createElement("button");
  settings.className = "settings-button summary-settings";
  settings.type = "button";
  settings.textContent = "配置模块";
  settings.addEventListener("click", () => setView("settings"));
  meta.append(settings);
  summary.append(main, meta);
  return summary;
}

function renderOverview(item, state) {
  const page = document.createElement("div");
  page.className = "overview-page";
  page.append(createModuleHero(item, state, "模块概览", item.description));

  const capabilities = document.createElement("section");
  capabilities.className = "overview-section overview-capabilities";
  const capabilityHeader = document.createElement("div");
  capabilityHeader.className = "overview-section-heading";
  const capabilityTitle = document.createElement("h3");
  capabilityTitle.textContent = "主要功能";
  const capabilityLead = document.createElement("p");
  capabilityLead.textContent = item.page
    ? "进入上游工作台可使用完整功能与原有操作流程。"
    : "此模块在消息流程中运行，下面列出它提供的能力。";
  capabilityHeader.append(capabilityTitle, capabilityLead);
  const chips = document.createElement("div");
  chips.className = "capability-chips";
  for (const tag of moduleCapabilities(item)) {
    const chip = document.createElement("span");
    chip.className = "capability-chip";
    chip.textContent = tag;
    chips.append(chip);
  }
  capabilities.append(capabilityHeader, chips);
  page.append(capabilities);
  const related = renderRelatedModules(item);
  if (related) page.append(related);

  const runtime = document.createElement("section");
  runtime.className = `overview-runtime ${state?.state || "unknown"}`;
  const runtimeCopy = document.createElement("div");
  runtimeCopy.className = "overview-runtime-copy";
  const runtimeLabel = document.createElement("span");
  runtimeLabel.textContent = "当前状态";
  const runtimeValue = document.createElement("strong");
  runtimeValue.textContent = statusLabel(state?.state);
  const runtimeDetail = document.createElement("p");
  runtimeDetail.textContent = state?.error
    ? `启动信息：${state.error}`
    : state?.state === "running" ? "模块已在 AstrBot 中注册并运行。" : "可在配置页检查启用状态和模块设置。";
  runtimeCopy.append(runtimeLabel, runtimeValue, runtimeDetail);
  runtime.append(runtimeCopy);

  const tiles = document.createElement("div");
  tiles.className = "overview-metrics";
  const entries = [
    ["事件处理器", String(state?.handlers ?? 0), "注册回调"],
    ["LLM 工具", String(state?.tools ?? 0), "模型可调用"],
    ["功能入口", item.page ? "上游工作台" : "消息流程", item.page ? "完整页面已集成" : "命令与事件"],
  ];
  for (const [label, value, note] of entries) {
    const tile = document.createElement("section");
    tile.className = "overview-metric";
    const title = document.createElement("p");
    title.className = "overview-metric-title";
    title.textContent = label;
    const valueText = document.createElement("strong");
    valueText.textContent = value;
    const detail = document.createElement("span");
    detail.textContent = note;
    tile.append(title, valueText, detail);
    tiles.append(tile);
  }
  runtime.append(tiles);
  page.append(runtime);

  const lower = document.createElement("div");
  lower.className = "overview-lower";
  const details = document.createElement("section");
  details.className = "overview-section overview-detail overview-detail-primary";
  const detailTitle = document.createElement("h3");
  detailTitle.textContent = "使用方式";
  const detailText = document.createElement("p");
  detailText.textContent = item.help || (item.page
    ? "此模块沿用上游功能页面，页面内的操作和数据由模块自身提供。"
    : "此模块由消息事件、命令或后台调度提供功能；详细参数可在配置页查看。");
  details.append(detailTitle, detailText);
  const entry = document.createElement("section");
  entry.className = "overview-section overview-entry";
  const entryTitle = document.createElement("h3");
  entryTitle.textContent = item.page ? "完整功能页面" : "管理入口";
  const entryText = document.createElement("p");
  entryText.textContent = item.page
    ? "功能页保留上游插件的原有布局、数据面板和操作控件。"
    : item.help || "启停和详细参数可在模块配置中管理。";
  entry.append(entryTitle, entryText);
  lower.append(details, entry);
  page.append(lower);

  const actions = document.createElement("div");
  actions.className = "overview-actions";
  const openFunction = document.createElement("button");
  openFunction.className = "settings-button primary";
  openFunction.type = "button";
  openFunction.textContent = item.page ? "进入功能页面" : "查看功能说明";
  openFunction.addEventListener("click", () => setView("module"));
  const openSettings = document.createElement("button");
  openSettings.className = "settings-button";
  openSettings.type = "button";
  openSettings.textContent = "配置模块";
  openSettings.addEventListener("click", () => setView("settings"));
  actions.append(openFunction, openSettings);
  page.append(actions);
  return page;
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

function renderSettingsEditor(item, config, savedMessage = "") {
  const schema = moduleSchema(config.schema);
  const currentSettings = config.settings && typeof config.settings === "object" ? config.settings : {};
  const panel = document.createElement("div");
  panel.className = "settings-panel";
  const hero = createModuleHero(item, config.state, "模块配置", item.description);

  const toolbar = document.createElement("div");
  toolbar.className = "settings-toolbar";
  const note = document.createElement("p");
  note.textContent = config.requires_reload
    ? "配置已保存，但模块需要重新应用后才会生效。"
    : "修改会先保存在草稿中；保存后按模块状态提示重新应用。敏感值不会显示。";
  toolbar.append(note);
  const reloadButton = document.createElement("button");
  reloadButton.className = "settings-button";
  reloadButton.type = "button";
  reloadButton.textContent = "重新读取";
  reloadButton.addEventListener("click", () => renderSettings(item.key));
  const resetButton = document.createElement("button");
  resetButton.className = "settings-button";
  resetButton.type = "button";
  resetButton.textContent = "恢复默认";
  const saveButton = document.createElement("button");
  saveButton.className = "settings-button primary";
  saveButton.type = "button";
  saveButton.textContent = "保存";
  const applyButton = document.createElement("button");
  applyButton.className = `settings-button apply-button${config.requires_reload ? " primary" : ""}`;
  applyButton.type = "button";
  applyButton.textContent = "应用更改";
  applyButton.disabled = !config.requires_reload;
  toolbar.append(reloadButton, resetButton, saveButton, applyButton);

  const message = document.createElement("p");
  message.className = `settings-message${savedMessage.startsWith("错误") ? " error" : ""}`;
  message.textContent = savedMessage || (config.requires_reload ? "有未应用的配置更改。" : "");

  const toggle = document.createElement("label");
  toggle.className = "settings-module-toggle";
  const enabled = document.createElement("input");
  enabled.type = "checkbox";
  enabled.checked = Boolean(config.enabled);
  enabled.dataset.moduleEnabled = "true";
  const enabledText = document.createElement("span");
  enabledText.textContent = `启用${item.label}`;
  toggle.append(enabled, enabledText);

  const state = document.createElement("p");
  const moduleState = config.state?.state || moduleStates.get(item.key)?.state;
  state.className = `module-runtime${["failed", "blocked"].includes(moduleState) ? " error" : ""}`;
  state.textContent = `当前状态：${statusLabel(moduleState)}${["failed", "blocked"].includes(moduleState) ? "；配置仍可编辑，保存后可重新应用。" : ""}`;
  const controlGrid = document.createElement("div");
  controlGrid.className = "module-control-grid";
  controlGrid.append(toggle, state);

  const form = document.createElement("form");
  form.className = "settings-form";
  form.addEventListener("submit", (event) => event.preventDefault());
  const secretFields = config.secret_fields || [];
  const configuredSecrets = config.configured_secrets || [];
  config._fieldMap = new Map(flattenSchema(schema, currentSettings, [], [], { secretFields, configuredSecrets })
    .map((field) => [field.path.join("."), field]));
  appendSettingsNodes(form, schema, currentSettings, config.providers || {}, config, [], 0);
  appendUnmappedSecrets(form, config, config._fieldMap);
  if (secretPathList(secretFields).length || configuredSecretPathList(configuredSecrets).length) {
    const hint = document.createElement("p");
    hint.className = "settings-message";
    hint.textContent = "密钥字段显示状态但不回显原值；留空保持原值，清除需要显式选择并保存。";
    form.prepend(hint);
  }

  resetButton.addEventListener("click", async () => {
    if (!window.confirm(`将${item.label}的非敏感设置恢复为默认值，并更新启用状态。确认继续？`)) return;
    resetButton.disabled = true;
    resetButton.textContent = "恢复中…";
    try {
      await saveSettings(item, config, buildDefaultValues(schema, secretFields), enabledDefault(config.schema, Boolean(config.enabled)), []);
    } catch {
      message.className = "settings-message error";
      message.textContent = "错误：恢复默认失败。配置未显示在错误信息中，请重新读取后重试。";
    } finally {
      resetButton.disabled = false;
      resetButton.textContent = "恢复默认";
    }
  });

  saveButton.addEventListener("click", async () => {
    const changes = {};
    try {
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
    } catch (error) {
      message.className = "settings-message error";
      const detail = typeof error?.message === "string" ? error.message : "请检查数字和 JSON 数组／对象。";
      message.textContent = `错误：${detail}`;
      return;
    }

    const clearSecrets = [...form.querySelectorAll('[data-secret-clear-path][aria-pressed="true"]')]
      .map((button) => button.dataset.secretClearPath)
      .filter((path) => !getAtPath(changes, normalizeSecretPath(path).split(".")));
    if (!Object.keys(changes).length && !clearSecrets.length && enabled.checked === Boolean(config.enabled)) {
      message.className = "settings-message";
      message.textContent = "没有待保存的修改。";
      return;
    }
    saveButton.disabled = true;
    saveButton.textContent = "保存中…";
    try {
      await saveSettings(item, config, changes, enabled.checked, clearSecrets);
    } catch {
      message.className = "settings-message error";
      message.textContent = "错误：保存失败。可能配置已被更新，请重新读取后重试。";
    } finally {
      saveButton.disabled = false;
      saveButton.textContent = "保存";
    }
  });

  applyButton.addEventListener("click", async () => {
    applyButton.disabled = true;
    applyButton.textContent = "应用中…";
    try {
      await callSettingsApi("POST", `ui/apply/${item.key}`, {});
      pendingApply.delete(item.key);
      await refreshStatus();
    } catch {
      message.className = "settings-message error";
      message.textContent = "错误：模块应用失败，请查看模块状态和 AstrBot 日志。";
      applyButton.disabled = false;
      applyButton.textContent = "应用更改";
    }
  });

  panel.append(hero, toolbar, message, controlGrid, form);
  settingsWorkspace.replaceChildren(panel);
  applyButton.disabled = !config.requires_reload;
}

function renderDedicatedSettings(item, config) {
  const panel = document.createElement("div");
  panel.className = "settings-panel";
  const hero = createModuleHero(item, config.state, "模块配置", item.description);
  const controls = document.createElement("div");
  controls.className = "settings-toolbar";
  const moduleToggle = document.createElement("label");
  moduleToggle.className = "settings-module-toggle";
  const enabled = document.createElement("input");
  enabled.type = "checkbox";
  enabled.checked = Boolean(config.enabled);
  const toggleLabel = document.createElement("span");
  toggleLabel.textContent = `启用${item.label}`;
  moduleToggle.append(enabled, toggleLabel);
  const status = document.createElement("p");
  status.className = "module-runtime";
  status.textContent = `当前状态：${statusLabel(config.state?.state || moduleStates.get(item.key)?.state)}`;
  const save = document.createElement("button");
  save.className = "settings-button primary";
  save.type = "button";
  save.textContent = "保存开关";
  save.addEventListener("click", async () => {
    save.disabled = true;
    save.textContent = "保存中…";
    try {
      await saveSettings(item, config, {}, enabled.checked, []);
    } catch {
      status.className = "settings-message error";
      status.textContent = "错误：保存失败，请重新读取后重试。";
      save.disabled = false;
      save.textContent = "保存开关";
    }
  });
  const apply = document.createElement("button");
  apply.className = `settings-button apply-button${config.requires_reload ? " primary" : ""}`;
  apply.type = "button";
  apply.textContent = "应用更改";
  apply.disabled = !config.requires_reload;
  apply.addEventListener("click", async () => {
    apply.disabled = true;
    apply.textContent = "应用中…";
    try {
      await callSettingsApi("POST", `ui/apply/${item.key}`, {});
      pendingApply.delete(item.key);
      await refreshStatus();
    } catch {
      status.className = "settings-message error";
      status.textContent = "错误：模块应用失败，请查看模块状态和 AstrBot 日志。";
      apply.disabled = false;
      apply.textContent = "应用更改";
    }
  });
  controls.append(save, apply);
  const info = document.createElement("p");
  info.className = "settings-message";
  info.textContent = item.key === "brush"
    ? "该模块通过现有图片创作面板管理供应商和画风配置。"
    : "该模块通过现有音乐账号面板管理账号与登录。";
  const frame = createModuleFrame(item, `${item.label}配置`);
  const controlGrid = document.createElement("div");
  controlGrid.className = "module-control-grid";
  controlGrid.append(moduleToggle, status);
  panel.append(hero, controlGrid, controls, info, frame);
  settingsWorkspace.replaceChildren(panel);
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
  await renderSettings(item.key, result?.requires_reload ? "配置已保存；请点击“应用更改”使其生效。" : "配置已保存。");
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

function setView(view) {
  activeView = view;
  const url = new URL(window.location.href);
  url.searchParams.set("module", activeKey);
  url.searchParams.set("view", view);
  history.replaceState(null, "", url);
  if (view === "settings" && statusPollTimer) {
    clearTimeout(statusPollTimer);
    statusPollTimer = null;
  }
  showOverviewView.setAttribute("aria-pressed", String(view === "overview"));
  showModuleView.setAttribute("aria-pressed", String(view === "module"));
  showSettingsView.setAttribute("aria-pressed", String(view === "settings"));
  renderActiveView();
  scheduleStatusPoll();
}

function openModulePage(item) {
  if (!item?.page) return;
  window.location.href = new URL("modules/" + item.page + "/index.html", document.baseURI).href;
}

function renderActiveView() {
  const item = modules.find((entry) => entry.key === activeKey) || modules[0];
  const state = moduleStates.get(item.key);
  if (activeView === "settings") {
    renderSettings(item.key);
    return;
  }
  if (activeView === "module" && item.page && (!state || state.state === "running")) {
    openModulePage(item);
    return;
  }
  settingsRequest += 1;
  detachActiveFrame();
  settingsWorkspace.hidden = true;
  settingsWorkspace.replaceChildren();
  workspace.hidden = false;
  workspace.replaceChildren();
  if (activeView === "overview") {
    workspace.append(renderOverview(item, state));
    refresh.disabled = false;
    return;
  }
  workspace.append(renderFunctionSummary(item, state));
  workspace.append(renderFallback(item, state));
  refresh.disabled = false;
}

function selectModule(key, updateHash) {
  const item = modules.find((entry) => entry.key === key) || modules[0];
  activeKey = item.key;
  document.documentElement.dataset.module = item.key;
  if (updateHash) history.replaceState(null, "", `#${item.key}`);
  for (const button of nav.querySelectorAll("button[data-module]")) {
    button.setAttribute("aria-current", button.dataset.module === activeKey ? "page" : "false");
  }

  const state = moduleStates.get(item.key);
  title.textContent = `${String(modules.indexOf(item) + 1).padStart(2, "0")} · ${item.label}`;
  description.textContent = item.description;
  status.textContent = statusLabel(state?.state);
  status.className = `status ${state?.state || ""}`;
  renderActiveView();
  scheduleStatusPoll();
}

function stateSnapshot(state) {
  return JSON.stringify(state ?? null);
}

function scheduleStatusPoll() {
  if (statusPollTimer) {
    clearTimeout(statusPollTimer);
    statusPollTimer = null;
  }
  if (activeView === "settings" || ![...moduleStates.values()].some((item) => item.state === "starting")) return;
  statusPollTimer = setTimeout(() => {
    statusPollTimer = null;
    void refreshStatus();
  }, 1200);
}

async function refreshStatus() {
  try {
    const data = await callSettingsApi("GET", "ui/status");
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

    const activeItem = modules.find((item) => item.key === activeKey) || modules[0];
    activeKey = activeItem.key;
    const activeState = moduleStates.get(activeKey);
    title.textContent = `${String(modules.indexOf(activeItem) + 1).padStart(2, "0")} · ${activeItem.label}`;
    description.textContent = activeItem.description;
    status.textContent = statusLabel(activeState?.state);
    status.className = `status ${activeState?.state || ""}`;
    for (const button of nav.querySelectorAll("button[data-module]")) {
      button.setAttribute("aria-current", button.dataset.module === activeKey ? "page" : "false");
    }
    if (activeView !== "settings" && changedKeys.has(activeKey)) renderActiveView();
    scheduleStatusPoll();
  } catch {
    status.textContent = "状态读取失败";
    status.className = "status failed";
  }
}

refresh.addEventListener("click", () => {
  if (activeView === "settings") renderSettings(activeKey);
  else if (activeFrame) activeFrame.src = activeFrame.src;
  else refreshStatus();
});
showModuleView.addEventListener("click", () => setView("module"));
showOverviewView.addEventListener("click", () => setView("overview"));
showSettingsView.addEventListener("click", () => setView("settings"));
window.addEventListener("hashchange", () => selectModule(location.hash.slice(1), false));
window.addEventListener("pagehide", () => {
  detachActiveFrame();
  if (statusPollTimer) clearTimeout(statusPollTimer);
  statusPollTimer = null;
});

const initialParams = new URLSearchParams(location.search);
const requestedView = initialParams.get("view");
if (["overview", "module", "settings"].includes(requestedView)) activeView = requestedView;
showOverviewView.setAttribute("aria-pressed", String(activeView === "overview"));
showModuleView.setAttribute("aria-pressed", String(activeView === "module"));
showSettingsView.setAttribute("aria-pressed", String(activeView === "settings"));
renderNavigation();
selectModule(location.hash.slice(1) || initialParams.get("module") || "heart", false);
refreshStatus();
