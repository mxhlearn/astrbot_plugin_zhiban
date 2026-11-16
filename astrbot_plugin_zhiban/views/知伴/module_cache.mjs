/** Small, bounded in-memory cache for authenticated module HTML. */
export class ModulePageCache {
  constructor({ ttlMs = 30000, maxEntries = 12, now = () => Date.now() } = {}) {
    this.ttlMs = Number(ttlMs) > 0 ? Number(ttlMs) : 30000;
    this.maxEntries = Number(maxEntries) > 0 ? Number(maxEntries) : 12;
    this.now = typeof now === "function" ? now : () => Date.now();
    this.entries = new Map();
    this.epochValue = 0;
  }

  get epoch() {
    return this.epochValue;
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

  get(key) {
    const entry = this.entries.get(key);
    if (!entry) return "";
    if (this.now() - entry.at > this.ttlMs) {
      this.entries.delete(key);
      return "";
    }
    // Refresh insertion order so the least recently used entry is evicted.
    this.entries.delete(key);
    this.entries.set(key, entry);
    return entry.source;
  }

  set(key, source, moduleKey = "") {
    if (!key || typeof source !== "string") return false;
    if (this.entries.size >= this.maxEntries) {
      const oldest = this.entries.keys().next().value;
      if (oldest) this.entries.delete(oldest);
    }
    this.entries.set(key, {
      at: this.now(),
      moduleKey: String(moduleKey || ""),
      source,
    });
    return true;
  }

  clear(moduleKey = "") {
    this.epochValue += 1;
    const target = String(moduleKey || "");
    for (const [key, entry] of [...this.entries]) {
      if (!target || entry.moduleKey === target) this.entries.delete(key);
    }
  }

  get size() {
    return this.entries.size;
  }
}
