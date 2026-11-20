<template>
  <n-config-provider
    :theme="naiveTheme"
    :theme-overrides="overrides"
    :locale="zhCN"
    :date-locale="dateZhCN"
  >
    <n-global-style />
    <n-message-provider>
      <n-dialog-provider>
        <brush-panel />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, watchEffect } from 'vue'
import {
  NConfigProvider,
  NDialogProvider,
  NGlobalStyle,
  NMessageProvider,
  darkTheme,
  dateZhCN,
  zhCN,
} from 'naive-ui'
import BrushPanel from './BrushPanel.vue'
import { buildThemeOverrides, themeKey, type BridgeContext } from './theme'

const theme = inject(themeKey)!

function syncHostTheme(context?: BridgeContext | null) {
  theme.syncFromHost(context)
}

let stopContextSync: (() => void) | undefined
onMounted(() => {
  const bridge = window.AstrBotPluginPage
  syncHostTheme(bridge?.getContext?.())
  stopContextSync = bridge?.onContext?.(syncHostTheme)
})
onBeforeUnmount(() => stopContextSync?.())

watchEffect(() => {
  document.documentElement.dataset.theme = theme.mode.value
})

const naiveTheme = computed(() => (theme.isDark.value ? darkTheme : null))
const overrides = computed(() => buildThemeOverrides(theme.mode.value))
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body,
#app {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Microsoft YaHei', sans-serif;
}

/* ---------- 设计令牌（与 theme.ts tokens 对齐，供自定义元素使用） ---------- */

:root[data-theme='light'] {
  color-scheme: light;
  --bg-base: var(--bg-app, #f5f8f4);
  --sider-bg: var(--bg-sidebar, #eef5ec);
  --glass-thick-bg: var(--bg-card, #ffffff);
  --glass-regular-bg: var(--bg-card, #ffffff);
  --glass-border: var(--border-light, #dce6da);
  --glass-highlight: rgba(255, 255, 255, 0.9);
  --glass-shadow: 0 10px 28px rgba(44, 76, 56, 0.07);
  --glass-divider: var(--border-light, #dce6da);
  --accent: #2f6b4f;
  --accent-soft: #ddeedc;
  --danger: #a53f36;
  --warning: #8c5917;
  --text-1: var(--text-primary, #24382c);
  --text-2: var(--text-secondary, #617367);
  --text-3: var(--text-tertiary, #718477);
  --radius-xs: 8px;
  --radius-sm: 10px;
  --radius-md: 14px;
  --radius-lg: 20px;
  --radius-full: 999px;
}

:root[data-theme='dark'] {
  color-scheme: dark;
  --bg-base: var(--bg-app, #111811);
  --sider-bg: var(--bg-sidebar, #162117);
  --glass-thick-bg: var(--bg-card, #1b261c);
  --glass-regular-bg: var(--bg-card, #1b261c);
  --glass-border: var(--border-light, #354637);
  --glass-highlight: rgba(255, 255, 255, 0.18);
  --glass-shadow: 0 12px 30px rgba(0, 0, 0, 0.22);
  --glass-divider: var(--border-light, #354637);
  --accent: #8fc7a5;
  --accent-soft: #263a2b;
  --danger: #f49a8f;
  --warning: #f0bc67;
  --text-1: var(--text-primary, #eef5ef);
  --text-2: var(--text-secondary, #aebbad);
  --text-3: var(--text-tertiary, #8ea093);
  --radius-xs: 8px;
  --radius-sm: 10px;
  --radius-md: 14px;
  --radius-lg: 20px;
  --radius-full: 999px;
}

body {
  background: var(--bg-base);
}

#app {
  position: relative;
  z-index: 1;
}

.n-card,
.n-modal {
  border-radius: var(--radius-lg);
}
</style>
