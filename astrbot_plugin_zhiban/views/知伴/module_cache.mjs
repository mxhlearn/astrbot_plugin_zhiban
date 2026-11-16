/** Small, bounded in-memory cache for authenticated module HTML. */
const DEFAULT_TTL_MS = 30000;
const DEFAULT_MAX_ENTRIES = 6;
const DEFAULT_MAX_BYTES = 2 * 1024 * 1024;
const DEFAULT_MAX_ENTRY_BYTES = 512 * 1024;

const utf8Encoder = typeof globalThis.TextEncoder === "function"
  ? new globalThis.TextEncoder()
  : null;

/**
 * Estimate retained HTML bytes from the UTF-8 encoding of the source string.
 * This is deliberately an estimate: it excludes key strings, Map/object
 * overhead, and browser/runtime heap overhead.
 */
function estimateUtf8Bytes(value) {
  if (utf8Encoder) return utf8Encoder.encode(value).byteLength;

  // Conservative UTF-8 fallback for runtimes without TextEncoder. Unpaired
  // surrogates are counted as the three-byte replacement character.
  let bytes = 0;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code <= 0x7f) {
      bytes += 1;
    } else if (code <= 0x7ff) {
      bytes += 2;
    } else if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        bytes += 4;
        index += 1;
      } else {
        bytes += 3;
      }
    } else {
      bytes += 3;
    }
  }
  return bytes;
}

function positiveInteger(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 1 ? Math.floor(number) : fallback;
}

function positiveSize(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 1 ? Math.floor(number) : fallback;
}

export class ModulePageCache {
  constructor({
    ttlMs = DEFAULT_TTL_MS,
    maxEntries = DEFAULT_MAX_ENTRIES,
    maxBytes = DEFAULT_MAX_BYTES,
    maxEntryBytes = DEFAULT_MAX_ENTRY_BYTES,
    now = () => Date.now(),
  } = {}) {
    this.ttlMs = positiveSize(ttlMs, DEFAULT_TTL_MS);
    this.maxEntries = positiveInteger(maxEntries, DEFAULT_MAX_ENTRIES);
    this.maxBytes = positiveSize(maxBytes, DEFAULT_MAX_BYTES);
    this.maxEntryBytes = positiveSize(maxEntryBytes, DEFAULT_MAX_ENTRY_BYTES);
    this.now = typeof now === "function" ? now : () => Date.now();
    this.entries = new Map();
    this.bytesValue = 0;
    this.epochValue = 0;
  }

  get epoch() {
    return this.epochValue;
  }

  /** Total estimated UTF-8 source bytes currently retained. */
  get bytes() {
    return this.bytesValue;
  }

  get size() {
    return this.entries.size;
  }

  key({ originPath = "", theme = "light", moduleKey = "", route = {} } = {}) {
    return JSON.stringify([
      String(originPath),
      String(theme),
      String(moduleKey),
      String(route.path || ""),
      String(route.hash || ""),
      route.query && typeof route.query === "object" ? route.query : {},
      this.epochValue,
    ]);
  }

  _deleteEntry(key) {
    const entry = this.entries.get(key);
    if (!entry) return false;
    this.entries.delete(key);
    this.bytesValue -= entry.bytes;
    if (this.bytesValue < 0) this.bytesValue = 0;
    return true;
  }

  _purgeExpired(now) {
    let removed = 0;
    for (const [key, entry] of this.entries) {
      if (now - entry.at > this.ttlMs) {
        this._deleteEntry(key);
        removed += 1;
      }
    }
    return removed;
  }

  /**
   * Explicit maintenance hook for callers that want to release stale entries
   * without waiting for a get/set. No timers are created by this cache.
   */
  purgeExpired() {
    return this._purgeExpired(this.now());
  }

  get(key) {
    const now = this.now();
    // Expired entries elsewhere still occupy the entry and byte budgets.
    this._purgeExpired(now);
    const entry = this.entries.get(key);
    if (!entry) return "";
    // Refresh insertion order so the least recently used entry is evicted.
    this.entries.delete(key);
    this.entries.set(key, entry);
    return entry.source;
  }

  set(key, source, moduleKey = "") {
    if (!key || typeof source !== "string") return false;

    const now = this.now();
    this._purgeExpired(now);

    // Every UTF-8 sequence is at least one byte per UTF-16 code unit, so this
    // cheap check avoids encoding very large rejected inputs.
    const hardLimit = Math.min(this.maxEntryBytes, this.maxBytes);
    if (source.length > hardLimit) return false;

    const bytes = estimateUtf8Bytes(source);
    if (bytes > this.maxEntryBytes || bytes > this.maxBytes) return false;

    // Remove the previous value first. Overwriting an existing key must not
    // count toward the entry limit or evict a different key.
    this._deleteEntry(key);
    this.entries.set(key, {
      at: now,
      moduleKey: String(moduleKey || ""),
      source,
      bytes,
    });
    this.bytesValue += bytes;

    while (this.entries.size > this.maxEntries || this.bytesValue > this.maxBytes) {
      const oldest = this.entries.keys().next().value;
      if (oldest === undefined) break;
      this._deleteEntry(oldest);
    }
    return true;
  }

  clear(moduleKey = "") {
    const target = String(moduleKey || "");
    if (!target) {
      this.epochValue += 1;
      this.entries.clear();
      this.bytesValue = 0;
      return;
    }

    // Local invalidation must not change the global epoch: keys for other
    // modules remain valid and reachable. Purge stale entries as maintenance.
    this._purgeExpired(this.now());
    for (const [key, entry] of this.entries) {
      if (entry.moduleKey === target) this._deleteEntry(key);
    }
  }
}