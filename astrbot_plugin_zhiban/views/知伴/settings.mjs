const SENSITIVE_NAME = /(apikey|accesstoken|refreshtoken|authtoken|clientsecret|privatekey|accesskey|password|passwd|credential|cookie|authorization|secret|token)$/i;

export function isSensitiveField(key, definition = {}) {
  const normalized = String(key).replace(/[^a-z0-9]/gi, "");
  return definition.secret === true || SENSITIVE_NAME.test(normalized);
}

export function cloneValue(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

export function orderModules(modules, order = []) {
  const byKey = new Map(modules.map((item) => [item.key, item]));
  const result = [];
  for (const key of order) {
    const item = byKey.get(key);
    if (item && !result.includes(item)) result.push(item);
  }
  for (const item of modules) {
    if (!result.includes(item)) result.push(item);
  }
  return result;
}

export function normalizeProviderOptions(providers = {}, kind = "chat_completion") {
  const unique = new Map();
  const values = providers?.[kind] || [];
  for (const value of values) {
    const option = typeof value === "string" ? { id: value, label: value } : value;
    if (!option || typeof option.id !== "string" || !option.id) continue;
    unique.set(option.id, { id: option.id, label: String(option.label || option.id) });
  }
  return [...unique.values()];
}

function fallbackFor(type) {
  if (type === "bool") return false;
  if (type === "int") return 0;
  if (type === "float") return 0;
  if (type === "list" || type === "template_list") return [];
  if (type === "dict" || type === "object") return {};
  return "";
}

export function normalizeSecretPath(value) {
  return String(value).split(".").filter((part) => part && part !== "settings").join(".");
}

export function secretPathList(values) {
  if (Array.isArray(values)) {
    return values.map((value) => typeof value === "string" ? value : value?.path)
      .filter((value) => typeof value === "string" && value.length > 0);
  }
  if (values && typeof values === "object") {
    return Object.entries(values).filter(([, enabled]) => Boolean(enabled)).map(([key]) => key);
  }
  return [];
}

export function configuredSecretPathList(values) {
  if (Array.isArray(values)) {
    return values
      .filter((value) => typeof value === "string" || value?.configured !== false)
      .map((value) => typeof value === "string" ? value : value?.path)
      .filter((value) => typeof value === "string" && value.length > 0);
  }
  if (values && typeof values === "object") {
    return Object.entries(values).filter(([, configured]) => Boolean(configured)).map(([key]) => key);
  }
  return [];
}

function pathSet(values) {
  return new Set(secretPathList(values).map(normalizeSecretPath));
}

function hasPath(paths, dottedPath) {
  const withoutSettings = String(dottedPath).split(".").filter((part) => part !== "settings").join(".");
  return paths.has(dottedPath) || paths.has(withoutSettings);
}

export function buildDefaultValues(schema, secretFields = []) {
  const secretPaths = pathSet(secretFields);
  function visit(node, prefix) {
    const result = {};
    for (const [key, definition] of Object.entries(node || {})) {
      if (!definition || typeof definition !== "object") continue;
      const path = [...prefix, key];
      if (isSensitiveField(key, definition) || hasPath(secretPaths, path.join("."))) continue;
      if (definition.type === "object") {
        result[key] = visit(definition.items || {}, path);
      } else {
        result[key] = Object.hasOwn(definition, "default")
          ? cloneValue(definition.default)
          : fallbackFor(definition.type);
      }
    }
    return result;
  }
  // Secret paths are always omitted from reset patches so the server preserves them.
  return visit(schema, []);
}

export function flattenSchema(schema, values = {}, prefix = [], result = [], options = {}) {
  const secretPaths = pathSet(options.secretFields);
  const configuredSecrets = pathSet(configuredSecretPathList(options.configuredSecrets));
  for (const [key, definition] of Object.entries(schema || {})) {
    if (!definition || typeof definition !== "object") continue;
    const path = [...prefix, key];
    const pathKey = path.join(".");
    if (isSensitiveField(key, definition) || hasPath(secretPaths, pathKey)) {
      const safeDefinition = {
        type: definition.type,
        description: definition.description,
        hint: definition.hint,
      };
      result.push({
        kind: "secret",
        key,
        path,
        definition: safeDefinition,
        configured: hasPath(configuredSecrets, pathKey)
          || Boolean(definition.configured ?? values?.[key]?.configured ?? values?.[key]),
      });
    } else if (definition.type === "object" && definition.items && typeof definition.items === "object") {
      result.push({ kind: "group", key, path, definition });
      flattenSchema(definition.items, values?.[key] || {}, path, result, options);
    } else {
      result.push({ kind: "field", key, path, definition, value: values?.[key] });
    }
  }
  return result;
}

export function parseFieldValue(raw, type) {
  if (type === "bool") return Boolean(raw);
  if (type === "int") {
    if (String(raw).trim() === "") throw new Error("请输入整数");
    const value = Number(raw);
    if (!Number.isInteger(value)) throw new Error("请输入整数");
    return value;
  }
  if (type === "float") {
    if (String(raw).trim() === "") throw new Error("请输入有效数字");
    const value = Number(raw);
    if (!Number.isFinite(value)) throw new Error("请输入有效数字");
    return value;
  }
  if (type === "list" || type === "template_list" || type === "dict") {
    const value = JSON.parse(String(raw || (type === "dict" ? "{}" : "[]")));
    const valid = type === "dict"
      ? Boolean(value) && typeof value === "object" && !Array.isArray(value)
      : Array.isArray(value);
    if (!valid) throw new Error(type === "dict" ? "请输入 JSON 对象" : "请输入 JSON 数组");
    return value;
  }
  return String(raw ?? "");
}

export function setValueAtPath(target, path, value) {
  let cursor = target;
  for (const part of path.slice(0, -1)) {
    if (!cursor[part] || typeof cursor[part] !== "object") cursor[part] = {};
    cursor = cursor[part];
  }
  cursor[path[path.length - 1]] = value;
}

export function unwrapApiPayload(payload) {
  if (payload && payload.status === "error") {
    throw new Error(typeof payload.message === "string" ? payload.message : "请求失败");
  }
  return payload && Object.hasOwn(payload, "data") ? payload.data : payload;
}

export function buildConfigSavePayload(revision, enabled, changes = {}, clearSecrets = []) {
  return {
    revision,
    enabled: Boolean(enabled),
    changes: cloneValue(changes) || {},
    clear_secrets: [...new Set(clearSecrets.map(String).filter(Boolean))],
  };
}
