import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDefaultValues,
  buildConfigSavePayload,
  configuredSecretPathList,
  flattenSchema,
  isSensitiveField,
  numericConstraints,
  normalizeProviderOptions,
  orderModules,
  parseFieldValue,
  setValueAtPath,
  unwrapApiPayload,
  validateNumericValue,
} from "../astrbot_plugin_zhiban/views/知伴/settings.mjs";

test("module navigation follows configured order and appends unknown omissions", () => {
  const modules = [{ key: "heart" }, { key: "memory" }, { key: "meme" }];
  assert.deepEqual(orderModules(modules, ["meme", "memory", "meme", "unknown"]), [
    modules[2], modules[1], modules[0],
  ]);
  assert.deepEqual(orderModules(modules, []), modules);
});

test("provider options accept AstrBot id and label objects", () => {
  assert.deepEqual(normalizeProviderOptions({
    chat_completion: [{ id: "chat-1", label: "主模型" }],
    embedding: [{ id: "embed-1", label: "向量模型" }],
    rerank: [{ id: "embed-1", label: "重复项" }, { id: "rerank-1", label: "重排模型" }],
  }, "chat_completion"), [
    { id: "chat-1", label: "主模型" },
  ]);
  assert.deepEqual(normalizeProviderOptions({
    chat_completion: [{ id: "chat-1", label: "主模型" }],
    embedding: [{ id: "embed-1", label: "向量模型" }],
    rerank: [{ id: "embed-1", label: "重复项" }, { id: "rerank-1", label: "重排模型" }],
  }, "embedding"), [
    { id: "embed-1", label: "向量模型" },
  ]);
  assert.deepEqual(normalizeProviderOptions({
    chat_completion: [{ id: "chat-1", label: "主模型" }],
    embedding: [{ id: "embed-1", label: "向量模型" }],
    rerank: [{ id: "rerank-1", label: "重排模型" }],
  }, "rerank"), [
    { id: "rerank-1", label: "重排模型" },
  ]);
});

test("schema reset restores nested defaults and omits secret values", () => {
  const schema = {
    api_key: { type: "string", default: "", secret: true },
    enabled: { type: "bool", default: false },
    settings: {
      type: "object",
      items: {
        timeout: { type: "int", default: 45 },
        accessToken: { type: "string", default: "" },
        nested: { type: "object", items: { rate: { type: "float", default: 1.25 } } },
      },
    },
  };
  const current = {
    api_key: "do-not-clear",
    enabled: true,
    settings: { timeout: 10, accessToken: "hidden", nested: { rate: 0.5 } },
  };

  assert.deepEqual(buildDefaultValues(schema, ["settings.accessToken"]), {
    enabled: false,
    settings: { timeout: 45, nested: { rate: 1.25 } },
  });
  assert.ok(flattenSchema(schema, current).some((field) => field.kind === "secret"));
});

test("redacted backend secret metadata marks fields without exposing values", () => {
  const [field] = flattenSchema(
    { api_key: { type: "string", description: "API Key" } },
    { api_key: "" },
    [],
    [],
    { secretFields: ["settings.api_key"], configuredSecrets: { "settings.api_key": true } },
  );
  assert.equal(field.kind, "secret");
  assert.equal(field.configured, true);
  assert.equal(JSON.stringify(field).includes("api_key-value"), false);
  assert.deepEqual(buildDefaultValues({ api_key: { type: "string", default: "" } }, ["settings.api_key"]), {});
  assert.deepEqual(configuredSecretPathList([
    { path: "api_key", configured: true },
    { path: "client_secret", configured: false },
  ]), ["api_key"]);
});

test("sensitive names and schema flags are detected", () => {
  assert.equal(isSensitiveField("apiKey"), true);
  assert.equal(isSensitiveField("group_password"), true);
  assert.equal(isSensitiveField("max_tokens"), false);
  assert.equal(isSensitiveField("provider_id"), false);
  assert.equal(isSensitiveField("custom", { secret: true }), true);
});

test("schema values parse with strict numeric and JSON types", () => {
  assert.equal(parseFieldValue("12", "int"), 12);
  assert.equal(parseFieldValue("0.75", "float"), 0.75);
  assert.deepEqual(parseFieldValue('["a", "b"]', "list"), ["a", "b"]);
  assert.throws(() => parseFieldValue("2.5", "int"));
  assert.throws(() => parseFieldValue("", "float"));
  assert.throws(() => parseFieldValue("[]", "dict"));

  const target = {};
  setValueAtPath(target, ["settings", "timeout"], 12);
  assert.deepEqual(target, { settings: { timeout: 12 } });
});

test("numeric schema ranges are read from slider metadata and validated", () => {
  const schema = { type: "int", slider: { min: 10, max: 200, step: 5 } };
  assert.deepEqual(numericConstraints(schema), { min: 10, max: 200, step: 5 });
  assert.deepEqual(numericConstraints({ type: "float", min: 0, max: 1 }), { min: 0, max: 1, step: "any" });
  assert.throws(() => validateNumericValue(9, schema, "评论最大长度"), /不能小于 10/);
  assert.throws(() => validateNumericValue(201, schema, "评论最大长度"), /不能大于 200/);
  assert.doesNotThrow(() => validateNumericValue(100, schema, "评论最大长度"));
});

test("API wrappers normalize success and reject error payloads", () => {
  assert.deepEqual(unwrapApiPayload({ status: "ok", data: { value: 1 } }), { value: 1 });
  assert.deepEqual(unwrapApiPayload({ value: 2 }), { value: 2 });
  assert.throws(() => unwrapApiPayload({ status: "error", message: "bad request" }), /bad request/);
});

test("save payload follows the revision, partial changes, and explicit secret-clear contract", () => {
  assert.deepEqual(buildConfigSavePayload("rev-2", false, { nested: { limit: 5 } }, ["api_key", "api_key"]), {
    revision: "rev-2",
    enabled: false,
    changes: { nested: { limit: 5 } },
    clear_secrets: ["api_key"],
  });
});

test("secret schema metadata reveals only configured state", () => {
  const [field] = flattenSchema(
    { api_key: { type: "string", secret: true, configured: true } },
    { api_key: "secret-value" },
  );
  assert.deepEqual(field, {
    kind: "secret",
    key: "api_key",
    path: ["api_key"],
    definition: { type: "string", description: undefined, hint: undefined },
    configured: true,
  });
  assert.equal(JSON.stringify(field).includes("secret-value"), false);
});
