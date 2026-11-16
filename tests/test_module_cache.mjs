import assert from "node:assert/strict";
import test from "node:test";

import { ModulePageCache } from "../astrbot_plugin_zhiban/views/知伴/module_cache.mjs";

function moduleKey(cache, value) {
  return cache.key({
    originPath: "/plugin/_t/token",
    theme: "light",
    moduleKey: value,
    route: { path: "index.html", hash: "", query: {} },
  });
}

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

test("cache defaults bound entries and bytes", () => {
  const cache = new ModulePageCache({ now: () => 0 });
  assert.equal(cache.ttlMs, 30000);
  assert.equal(cache.maxEntries, 6);
  assert.equal(cache.maxBytes, 2 * 1024 * 1024);
  assert.equal(cache.maxEntryBytes, 512 * 1024);

  for (let index = 0; index < 7; index += 1) {
    assert.equal(cache.set(`default-${index}`, String(index), "module"), true);
  }
  assert.equal(cache.size, 6);
  assert.equal(cache.get("default-0"), "");
  assert.equal(cache.get("default-6"), "6");
  assert.equal(cache.bytes, 6);
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
  assert.equal(cache.size, 0);
  assert.equal(cache.bytes, 0);
});

test("overwriting a key does not evict another entry", () => {
  const cache = new ModulePageCache({ maxEntries: 2, maxBytes: 100, now: () => 0 });
  const a = moduleKey(cache, "a");
  const b = moduleKey(cache, "b");
  assert.equal(cache.set(a, "aa", "a"), true);
  assert.equal(cache.set(b, "bb", "b"), true);
  assert.equal(cache.get(a), "aa");

  assert.equal(cache.set(a, "AAAA", "a"), true);
  assert.equal(cache.size, 2);
  assert.equal(cache.bytes, 6);
  assert.equal(cache.get(a), "AAAA");
  assert.equal(cache.get(b), "bb");
});

test("module-scoped clear keeps other modules and the global epoch", () => {
  const cache = new ModulePageCache({ maxBytes: 100, now: () => 0 });
  const memeArgs = { originPath: "/plugin/_t/token", theme: "light", moduleKey: "meme", route: { path: "index.html", hash: "", query: {} } };
  const ttsArgs = { ...memeArgs, moduleKey: "tts" };
  const memeKey = cache.key(memeArgs);
  const ttsKey = cache.key(ttsArgs);
  assert.equal(cache.set(memeKey, "meme page", "meme"), true);
  assert.equal(cache.set(ttsKey, "tts page", "tts"), true);
  const before = cache.epoch;

  cache.clear("meme");
  assert.equal(cache.epoch, before);
  assert.equal(cache.key(ttsArgs), ttsKey);
  assert.equal(cache.size, 1);
  assert.equal(cache.bytes, 8);
  assert.equal(cache.get(memeKey), "");
  assert.equal(cache.get(ttsKey), "tts page");
});

test("global clear invalidates old keys and releases all entries", () => {
  const cache = new ModulePageCache({ maxBytes: 100, now: () => 0 });
  const memeArgs = { originPath: "/plugin/_t/token", theme: "light", moduleKey: "meme", route: { path: "index.html", hash: "", query: {} } };
  const ttsArgs = { ...memeArgs, moduleKey: "tts" };
  const memeKey = cache.key(memeArgs);
  const ttsKey = cache.key(ttsArgs);
  cache.set(memeKey, "meme", "meme");
  cache.set(ttsKey, "tts", "tts");
  const before = cache.epoch;

  cache.clear();
  assert.equal(cache.epoch, before + 1);
  assert.equal(cache.size, 0);
  assert.equal(cache.bytes, 0);
  assert.equal(cache.get(memeKey), "");
  assert.equal(cache.get(ttsKey), "");

  const freshKey = cache.key(memeArgs);
  assert.notEqual(freshKey, memeKey);
  assert.equal(cache.set(freshKey, "fresh", "meme"), true);
  assert.equal(cache.get(freshKey), "fresh");
});

test("get purges every expired entry, not only the requested one", () => {
  let now = 0;
  const cache = new ModulePageCache({ ttlMs: 50, maxBytes: 100, now: () => now });
  const a = moduleKey(cache, "a");
  const b = moduleKey(cache, "b");
  cache.set(a, "A", "a");
  cache.set(b, "B", "b");
  now = 60;

  assert.equal(cache.get(a), "");
  assert.equal(cache.size, 0);
  assert.equal(cache.bytes, 0);
  assert.equal(cache.get(b), "");
});

test("set purges every expired entry before adding a new one", () => {
  let now = 0;
  const cache = new ModulePageCache({ ttlMs: 50, maxBytes: 100, now: () => now });
  const a = moduleKey(cache, "a");
  const b = moduleKey(cache, "b");
  const c = moduleKey(cache, "c");
  cache.set(a, "A", "a");
  cache.set(b, "B", "b");
  now = 60;

  assert.equal(cache.set(c, "C", "c"), true);
  assert.equal(cache.size, 1);
  assert.equal(cache.bytes, 1);
  assert.equal(cache.get(a), "");
  assert.equal(cache.get(b), "");
  assert.equal(cache.get(c), "C");
});

test("purgeExpired releases unaccessed stale entries without timers", () => {
  let now = 0;
  const cache = new ModulePageCache({ ttlMs: 50, maxBytes: 100, now: () => now });
  cache.set(moduleKey(cache, "a"), "A", "a");
  cache.set(moduleKey(cache, "b"), "B", "b");

  now = 50;
  assert.equal(cache.purgeExpired(), 0);
  assert.equal(cache.size, 2);
  now = 51;
  assert.equal(cache.purgeExpired(), 2);
  assert.equal(cache.size, 0);
  assert.equal(cache.bytes, 0);
});

test("maxBytes and maxEntryBytes boundaries drive LRU byte accounting", () => {
  const cache = new ModulePageCache({ ttlMs: 1000, maxEntries: 10, maxBytes: 6, maxEntryBytes: 4, now: () => 0 });
  assert.equal(cache.set("a", "aaaa", "m"), true);
  assert.equal(cache.bytes, 4);
  assert.equal(cache.set("b", "bb", "m"), true);
  assert.equal(cache.bytes, 6);

  assert.equal(cache.get("a"), "aaaa");
  assert.equal(cache.set("c", "c", "m"), true);
  assert.equal(cache.get("b"), "");
  assert.equal(cache.get("a"), "aaaa");
  assert.equal(cache.get("c"), "c");
  assert.equal(cache.size, 2);
  assert.equal(cache.bytes, 5);

  assert.equal(cache.set("d", "dddd", "m"), true);
  assert.equal(cache.get("a"), "");
  assert.equal(cache.get("c"), "c");
  assert.equal(cache.get("d"), "dddd");
  assert.equal(cache.size, 2);
  assert.equal(cache.bytes, 5);

  const entryBound = new ModulePageCache({ ttlMs: 1000, maxEntries: 4, maxBytes: 100, maxEntryBytes: 4, now: () => 0 });
  assert.equal(entryBound.set("x", "abcd", "m"), true);
  assert.equal(entryBound.set("y", "abcde", "m"), false);
  assert.equal(entryBound.size, 1);
  assert.equal(entryBound.bytes, 4);
  assert.equal(entryBound.get("x"), "abcd");

  const totalBound = new ModulePageCache({ ttlMs: 1000, maxEntries: 4, maxBytes: 3, maxEntryBytes: 8, now: () => 0 });
  assert.equal(totalBound.set("x", "abc", "m"), true);
  assert.equal(totalBound.set("y", "abcd", "m"), false);
  assert.equal(totalBound.size, 1);
  assert.equal(totalBound.bytes, 3);
  assert.equal(totalBound.get("x"), "abc");
});

test("oversized entries are rejected without throwing or disturbing existing data", () => {
  const cache = new ModulePageCache({ ttlMs: 1000, maxEntries: 3, maxBytes: 100, maxEntryBytes: 5, now: () => 0 });
  assert.equal(cache.set("ok", "ok", "m"), true);
  let accepted;
  assert.doesNotThrow(() => {
    accepted = cache.set("huge", "x".repeat(6), "m");
  });
  assert.equal(accepted, false);
  assert.equal(cache.get("huge"), "");
  assert.equal(cache.size, 1);
  assert.equal(cache.bytes, 2);
  assert.equal(cache.get("ok"), "ok");

  const utf8 = new ModulePageCache({ ttlMs: 1000, maxEntries: 3, maxBytes: 100, maxEntryBytes: 4, now: () => 0 });
  assert.equal(utf8.set("emoji", "😀", "m"), true);
  assert.equal(utf8.bytes, 4);
  assert.equal(utf8.set("emoji-plus", "😀a", "m"), false);
  assert.equal(utf8.size, 1);
  assert.equal(utf8.get("emoji"), "😀");
});