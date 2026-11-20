/**
 * 聊天互动主题：沿用知伴的绿色设计 token。
 * - A 色（边框/分隔线）唯一真相源：tokens.light/dark.divider
 * - 背景/侧栏/卡片三色统一：bgPage / bgSider / bgCard
 */
import type { GlobalThemeOverrides } from 'naive-ui'
import type { ComputedRef, InjectionKey, Ref } from 'vue'
import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark'


export interface ThemeApi {
  mode: Ref<ThemeMode>
  isDark: ComputedRef<boolean>
  toggle: () => void
}

export const themeKey: InjectionKey<ThemeApi> = Symbol('app-theme')

export function loadThemeMode(): ThemeMode {
  // 知伴外壳决定主题，聊天页不维护第二套主题来源。
  if (typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark') return 'dark'
  return 'light'
}

export function createThemeApi(): ThemeApi {
  const mode = ref<ThemeMode>(loadThemeMode())
  return {
    mode,
    isDark: computed(() => mode.value === 'dark'),
    toggle: () => {},
  }
}

const brand = {
  light: { base: '#2f6b4f', hover: '#3d7c5e', pressed: '#24563f', suppl: '#3d7c5e' },
  dark: { base: '#8fc7a5', hover: '#b3d9c1', pressed: '#6eaa85', suppl: '#b3d9c1' },
}

// A 色与面色：亮/暗各一套，theme.ts 为唯一真相源，App.vue 的 CSS 变量需与此对齐
const tokens = {
  light: {
    bgPage: '#f5f8f4',
    bgSider: '#eef5ec',
    bgCard: '#ffffff',
    divider: '#dce6da',
  },
  dark: {
    bgPage: '#111811',
    bgSider: '#162117',
    bgCard: '#1b261c',
    divider: '#354637',
  },
} as const

export function buildThemeOverrides(mode: ThemeMode): GlobalThemeOverrides {
  const c = brand[mode]
  const t = tokens[mode]
  return {
    common: {
      primaryColor: c.base,
      primaryColorHover: c.hover,
      primaryColorPressed: c.pressed,
      primaryColorSuppl: c.suppl,
      fontSize: '15px',
      borderRadius: '10px',
      borderRadiusSmall: '8px',
      bodyColor: t.bgPage,
      cardColor: t.bgCard,
      modalColor: t.bgCard,
      popoverColor: t.bgCard,
      dividerColor: t.divider,
      borderColor: t.divider,
    },
    Button: {
      borderRadius: '999px',
    },
    Layout: {
      color: t.bgPage,
      siderColor: t.bgSider,
    },
    Card: {
      color: t.bgCard,
      colorEmbedded: t.bgCard,
      borderColor: t.divider,
    },
  }
}
