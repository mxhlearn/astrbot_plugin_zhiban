import {
  buildConfigSavePayload,
  buildDefaultValues,
  configuredSecretPathList,
  flattenSchema,
  isSensitiveField,
  normalizeSecretPath,
  normalizeProviderOptions,
  orderModules,
  parseFieldValue,
  secretPathList,
  setValueAtPath,
  unwrapApiPayload,
} from "./settings.mjs";

const moduleCatalog = [
  { key: "heart", label: "聊天互动", description: "群聊接话、唤醒与私聊上下文", page: "heart", plugin: "astrbot_plugin_angel_heart" },
  { key: "memory", label: "记忆成长", description: "长期记忆、知识检索与人格审批", page: "memory", plugin: "astrbot_plugin_livingmemory" },
  { key: "meme", label: "表情互动", description: "服务器图库检索、管理与发送", page: "meme", plugin: "astrbot_plugin_meme_manager" },
  { key: "tts", label: "语音回复", description: "BreezeBlue 语音合成、音色与回复策略", page: "tts", plugin: "astrbot_plugin_breeze_tts" },
  { key: "proactive", label: "主动问候", description: "按现有私聊策略进行主动问候", help: "主动问候由后台调度器执行。启用范围与调度参数可在知伴插件设置的「主动问候」分组中查看。" },
  { key: "brush", label: "图片创作", description: "生图、改图与供应商配置", page: "brush", plugin: "astrbot_plugin_angel_brush" },
  { key: "music", label: "音乐点播", description: "Bilibili 搜索、账号与音频发送", page: "music", plugin: "astrbot_plugin_listen_music" },
  { key: "eye", label: "历史查询", description: "群记录检索与分页查询", help: "通过原有历史查询命令或 LLM 工具检索记录；SnowLuma 版本与分页模式在知伴插件设置中配置。" },
  { key: "qzone", label: "QQ 空间", description: "动态浏览、发布与互动工具", page: "qzone", plugin: "astrbot_plugin_qzone_ultra" },
  { key: "filter", label: "内容过滤", description: "按规则处理消息中的链接", help: "内容过滤由消息发送流程自动执行；白名单域名和启用状态在知伴插件设置的「内容过滤」分组中配置。" },
];
let modules = moduleCatalog;

const nav = document.querySelector("#moduleNav");
const title = document.querySelector("#moduleTitle");
const description = document.querySelector("#moduleDescription");
const status = document.querySelector("#moduleStatus");
const workspace = document.querySelector("#moduleWorkspace");
const settingsWorkspace = document.querySelector("#settingsWorkspace");
const refresh = document.querySelector("#refreshModule");
const showModuleView = document.querySelector("#showModuleView");
const showSettingsView = document.querySelector("#showSettingsView");
const moduleStates = new Map();
const pendingApply = new Set();
let activeKey = "heart";
let activeFrame = null;
let activeFrameDetach = null;
let activeView = "module";
let settingsRequest = 0;

function detachActiveFrame() {
  if (typeof activeFrameDetach === "function") activeFrameDetach();
  activeFrameDetach = null;
  activeFrame = null;
}

function attachActiveFrame(frame, item) {
  activeFrame = frame;
  activeFrameDetach = window.ZhibanBridge?.attachFrame(frame, item.key, item.label) || null;
}

function statusLabel(value) {
  return ({ running: "运行中", failed: "启动失败", blocked: "冲突未加载", disabled: "已关闭", starting: "启动中" })[value] || "状态未知";
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
    const label = document.createElement("span");
    label.textContent = item.label;
    const dot = document.createElement("span");
    dot.className = `nav-state ${moduleStates.get(item.key)?.state || ""}`;
    dot.setAttribute("aria-hidden", "true");
    button.append(number, label, dot);
    button.addEventListener("click", () => selectModule(item.key, true));
    return button;
  }));
}

function renderFallback(item, state) {
  const section = document.createElement("div");
  section.className = "empty-state";
  const heading = document.createElement("h3");
  const copy = document.createElement("p");
  const settings = document.createElement("p");
  heading.textContent = state?.state === "failed" || state?.state === "blocked"
    ? "模块尚未就绪"
    : state?.state === "starting"
      ? "模块正在初始化"
    : state?.state === "disabled"
      ? "模块已关闭"
      : "此模块由消息流程提供服务";
  copy.textContent = state?.error
    ? `启动信息：${state.error}`
    : state?.detail || (state?.state === "disabled"
      ? "在知伴插件设置中启用该模块并重载插件。"
      : item.help || "该模块通过 AstrBot 消息事件和 LLM 工具提供功能。");
  if (state?.state === "failed" || state?.state === "blocked") copy.className = "error";
  settings.textContent = "在本应用切换到“配置”，即可修改模块开关和详细参数。";
  section.append(heading, copy, settings);
  return section;
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

  for (const [key, definition] of Object.entries(schema || {})) {
    if (!definition || typeof definition !== "object") continue;
    if (definition.invisible === true) continue;
    const fieldPath = [...path, key];
    const field = byPath.get(fieldPath.join("."));
    if (field?.kind !== "secret" && !isSensitiveField(key, definition)
      && definition.type === "object" && definition.items && typeof definition.items === "object") {
      const details = document.createElement("details");
      details.className = "settings-group";
      details.open = depth === 0;
      const summary = document.createElement("summary");
      summary.textContent = definition.description || key;
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
    const label = document.createElement("div");
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
      if (definition.type === "int") control.step = "1";
      if (definition.type === "float") control.step = "any";
      const value = getAtPath(values, [key]);
      control.value = value == null ? "" : String(value);
    }
    if (control.type !== "checkbox") control.classList.add("settings-input");
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
    const label = document.createElement("div");
    label.className = "settings-label";
    label.textContent = path[path.length - 1];
    const controls = document.createElement("div");
    controls.className = "settings-secret-cell";
    const input = document.createElement("input");
    input.className = "settings-input";
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
  applyButton.className = "settings-button";
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
  state.className = `settings-message${["failed", "blocked"].includes(config.state) ? " error" : ""}`;
  state.textContent = `当前状态：${statusLabel(config.state || moduleStates.get(item.key)?.state)}${config.state === "failed" || config.state === "blocked" ? "；配置仍可编辑，保存后可重新应用。" : ""}`;

  const form = document.createElement("form");
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
    try {
      await saveSettings(item, config, buildDefaultValues(schema, secretFields), enabledDefault(config.schema, Boolean(config.enabled)), []);
    } catch {
      message.className = "settings-message error";
      message.textContent = "错误：恢复默认失败。配置未显示在错误信息中，请重新读取后重试。";
    } finally {
      resetButton.disabled = false;
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
        const previous = getAtPath(currentSettings, path);
        if (JSON.stringify(value) !== JSON.stringify(previous)) setValueAtPath(changes, path, value);
      }
    } catch {
      message.className = "settings-message error";
      message.textContent = "错误：有字段格式不正确，请检查数字和 JSON 数组／对象。";
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
    try {
      await saveSettings(item, config, changes, enabled.checked, clearSecrets);
    } catch {
      message.className = "settings-message error";
      message.textContent = "错误：保存失败。可能配置已被更新，请重新读取后重试。";
    } finally {
      saveButton.disabled = false;
    }
  });

  applyButton.addEventListener("click", async () => {
    applyButton.disabled = true;
    try {
      await callSettingsApi("POST", `ui/apply/${item.key}`, {});
      pendingApply.delete(item.key);
      await refreshStatus();
    } catch {
      message.className = "settings-message error";
      message.textContent = "错误：模块应用失败，请查看模块状态和 AstrBot 日志。";
      applyButton.disabled = false;
    }
  });

  panel.append(toolbar, message, toggle, state, form);
  settingsWorkspace.replaceChildren(panel);
  applyButton.disabled = !config.requires_reload;
}

function renderDedicatedSettings(item, config) {
  const panel = document.createElement("div");
  panel.className = "settings-panel";
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
  status.className = "settings-message";
  status.textContent = `当前状态：${statusLabel(config.state || moduleStates.get(item.key)?.state)}`;
  const save = document.createElement("button");
  save.className = "settings-button primary";
  save.type = "button";
  save.textContent = "保存开关";
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await saveSettings(item, config, {}, enabled.checked, []);
    } catch {
      status.className = "settings-message error";
      status.textContent = "错误：保存失败，请重新读取后重试。";
      save.disabled = false;
    }
  });
  const apply = document.createElement("button");
  apply.className = "settings-button";
  apply.type = "button";
  apply.textContent = "应用更改";
  apply.disabled = !config.requires_reload;
  apply.addEventListener("click", async () => {
    apply.disabled = true;
    try {
      await callSettingsApi("POST", `ui/apply/${item.key}`, {});
      pendingApply.delete(item.key);
      await refreshStatus();
    } catch {
      status.className = "settings-message error";
      status.textContent = "错误：模块应用失败，请查看模块状态和 AstrBot 日志。";
      apply.disabled = false;
    }
  });
  controls.append(moduleToggle, save, apply);
  const info = document.createElement("p");
  info.className = "settings-message";
  info.textContent = item.key === "brush"
    ? "该模块通过现有图片创作面板管理供应商和画风配置。"
    : "该模块通过现有音乐账号面板管理账号与登录。";
  const frame = document.createElement("iframe");
  frame.className = "module-frame";
  frame.title = `${item.label}配置`;
  frame.loading = "lazy";
  frame.referrerPolicy = "no-referrer";
  frame.dataset.module = item.key;
  frame.src = `modules/${item.page}/index.html`;
  panel.append(status, controls, info, frame);
  attachActiveFrame(frame, item);
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
  showModuleView.setAttribute("aria-pressed", String(view === "module"));
  showSettingsView.setAttribute("aria-pressed", String(view === "settings"));
  renderActiveView();
}

function renderActiveView() {
  const item = modules.find((entry) => entry.key === activeKey) || modules[0];
  const state = moduleStates.get(item.key);
  if (activeView === "settings") {
    renderSettings(item.key);
    return;
  }
  settingsRequest += 1;
  detachActiveFrame();
  settingsWorkspace.hidden = true;
  settingsWorkspace.replaceChildren();
  workspace.hidden = false;
  workspace.replaceChildren();
  if (item.page && (!state || state.state === "running")) {
    const frame = document.createElement("iframe");
    frame.className = "module-frame";
    frame.title = item.label;
    frame.loading = "lazy";
    frame.referrerPolicy = "no-referrer";
    frame.dataset.module = item.key;
    frame.src = `modules/${item.page}/index.html`;
    workspace.append(frame);
    attachActiveFrame(frame, item);
  } else {
    workspace.append(renderFallback(item, state));
  }
  refresh.disabled = false;
}

function selectModule(key, updateHash) {
  const item = modules.find((entry) => entry.key === key) || modules[0];
  activeKey = item.key;
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
}

async function refreshStatus() {
  try {
    const data = await callSettingsApi("GET", "ui/status");
    modules = orderModules(moduleCatalog, data.menu_order);
    moduleStates.clear();
    for (const item of data.modules || []) moduleStates.set(item.key, item);
    renderNavigation();
    selectModule(activeKey, false);
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
showSettingsView.addEventListener("click", () => setView("settings"));
window.addEventListener("hashchange", () => selectModule(location.hash.slice(1), false));
window.addEventListener("pagehide", detachActiveFrame);

renderNavigation();
selectModule(location.hash.slice(1) || "heart", false);
refreshStatus();
