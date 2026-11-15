import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const dashboard = new URL("../../pages/dashboard/", import.meta.url);
const read = name => readFileSync(new URL(name, dashboard), "utf8");
const appearance = read("appearance.js");
const app = read("app.js");
const index = read("index.html");
const themes = read("themes.css");

const applySource = app.match(/function applyHostTheme\(context\) \{[\s\S]*?\n  \}/)?.[0];

function apply(context, root) {
  assert.ok(applySource, "app.js must keep the host theme adapter");
  vm.runInNewContext(`${applySource}\napplyHostTheme(__context);`, {
    __context: context,
    document: { documentElement: root },
  });
}

test("appearance.js is a compatibility placeholder without theme ownership", () => {
  assert.doesNotMatch(appearance, /localStorage|LMAppearance|matchMedia|lmem_|data-style/);
  assert.doesNotMatch(appearance, /document\.|window\./);
});

test("host context is the only source of light and dark mode", () => {
  const root = { dataset: {}, style: {} };
  apply({ isDark: true }, root);
  assert.equal(root.dataset.theme, "dark");
  assert.equal(root.style.colorScheme, "dark");

  apply({ isDark: false, locale: "en" }, root);
  assert.equal(root.dataset.theme, "light");
  assert.equal(root.style.colorScheme, "light");
});

test("missing or non-boolean host context never overwrites the current theme", () => {
  const root = { dataset: { theme: "dark" }, style: { colorScheme: "dark" } };
  apply(undefined, root);
  apply({ isDark: "yes" }, root);
  apply({ locale: "zh" }, root);
  assert.equal(root.dataset.theme, "dark");
  assert.equal(root.style.colorScheme, "dark");
});

test("app.js no longer reads legacy appearance storage or exposes LMAppearance", () => {
  assert.doesNotMatch(app, /LMAppearance|lmem_theme|lmem_style|dataset\.style|prefers-color-scheme/);
  assert.match(app, /api\.bridge\.onContext/);
  assert.match(app, /applyHostTheme\(context\)/);
});

test("dashboard markup has no duplicate brand, decorative index, or appearance controls", () => {
  assert.doesNotMatch(index, /appearance-dialog|theme-toggle|data-style/);
  assert.doesNotMatch(index, /class="[^"]*page-index/);
  assert.doesNotMatch(index, /class="[^"]*sidebar-brand/);
  assert.doesNotMatch(index, /class="[^"]*sidebar-footer/);
  assert.match(index, /class="sidebar-nav"/);
  assert.match(index, /data-lang="ja"/);
});

test("themes.css contains no dashboard presets", () => {
  assert.doesNotMatch(themes, /data-style|appearance-dialog|--bg-app:|--accent:/);
});
