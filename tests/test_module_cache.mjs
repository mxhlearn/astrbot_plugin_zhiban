import assert from "node:assert/strict";
import test from "node:test";

import { ModulePageCache } from "../astrbot_plugin_zhiban/views/知伴/module_cache.mjs";

test("cache key separates module, route, theme and epoch", () => {
  const cache = new ModulePageCache({ now: () => 0 });
  const base = { originPath: "/plugin/_t/token", theme: "light", moduleKey: "meme", route: { path: "catalog/index.html", hash: "", query: {} } };
  const key = cache.key(base);
  assert.notEqual(key, cache.key({ ...base, moduleKey: "tts" }));
  assert.notEqual(key, cache.key({ ...base, route: { ...base.route, hash: "x" } }));
  assert.notEqual(key, cache.key({ ...base, theme: "dark" }));
  cache.clear();
  assert.notEqual(key, cache.key(base));
});

test("cache expires and refreshes LRU order", () => {
  let now = 100;
  const cache = new ModulePageCache({ ttlMs: 50, maxEntries: 2, now: () => now });
  const a = cache.key({ moduleKey: "a" });
  const b = cache.key({ moduleKey: "b" });
  assert.equal(cache.set(a, "A", "a"), true);
  assert.equal(cache.set(b, "B", "b"), true);
  assert.equal(cache.get(a), "A");
  cache.set(cache.key({ moduleKey: "c" }), "C", "c");
  assert.equal(cache.size, 2);
  assert.equal(cache.get(b), "");
  assert.equal(cache.get(a), "A");
  now = 200;
  assert.equal(cache.get(a), "");
});

test("module-scoped clear removes only that module and bumps epoch", () => {
  const cache = new ModulePageCache();
  const memeKey = cache.key({ moduleKey: "meme" });
  const ttsKey = cache.key({ moduleKey: "tts" });
  cache.set(memeKey, "meme", "meme");
  cache.set(ttsKey, "tts", "tts");
  const before = cache.epoch;
  cache.clear("meme");
  assert.equal(cache.epoch, before + 1);
  assert.equal(cache.get(memeKey), "");
  assert.equal(cache.get(ttsKey), "tts");
});
