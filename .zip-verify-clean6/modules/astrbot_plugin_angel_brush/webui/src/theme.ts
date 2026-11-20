/**
 * 图片创作主题：沿用知伴的浅绿设计 token。
 * 宿主提供 isDark 时跟随宿主；没有宿主上下文时默认浅色。
 * 页面不保存独立主题，也不提供页面内主题切换。
 * 首帧固定浅绿；只有宿主明确传入 isDark 时才采用深色。
 */
import type { GlobalThemeOverrides } from 'naive-ui'
import type { ComputedRef, InjectionKey, Ref } from 'vue'
import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark'

export interface BridgeContext {
  isDark?: boolean
}

export interface ThemeApi {
  mode: Ref<ThemeMode>
  isDark: ComputedRef<boolean>
  syncFromHost: (context?: BridgeContext | null) => void
}

export const themeKey: InjectionKey<ThemeApi> = Symbol('app-theme')

let sharedTheme: ThemeApi | undefined

export function createThemeApi(): ThemeApi {
  if (sharedTheme) return sharedTheme
  const mode = ref<ThemeMode>('light')
  sharedTheme = {
    mode,
    isDark: computed(() => mode.value === 'dark'),
    syncFromHost(context) {
      if (typeof context?.isDark === 'boolean') {
        mode.value = context.isDark ? 'dark' : 'light'
      }
    },
  }
  return sharedTheme
}

/** 与主应用 views/知伴/index.html 的 --zb-* 令牌保持一致。 */
const palette = {
  light: {
    bgPage: '#f5f8f4',
    bgSider: '#eef5ec',
    bgCard: '#ffffff',
    bgHover: '#e7f0e7',
    bgActive: '#ddeedc',
    border: '#dce6da',
    borderStrong: '#bdcfbb',
    text1: '#24382c',
    text2: '#617367',
    text3: '#718477',
    textDisabled: '#9aa69c',
    primary: '#2f6b4f',
    primaryHover: '#3d7c5e',
    primaryPressed: '#24563f',
    primarySoft: '#ddeedc',
    onPrimary: '#ffffff',
    infoSoft: '#eef5ec',
    success: '#2f6b4f',
    successSoft: '#e7f0e7',
    warning: '#8c5917',
    warningSoft: '#faf0d9',
    danger: '#a53f36',
    dangerSoft: '#fbe9e6',
    shadow: '0 10px 28px rgba(44, 76, 56, 0.07)',
  },
  dark: {
    bgPage: '#111811',
    bgSider: '#162117',
    bgCard: '#1b261c',
    bgHover: '#223226',
    bgActive: '#263a2b',
    border: '#354637',
    borderStrong: '#506255',
    text1: '#eef5ef',
    text2: '#aebbad',
    text3: '#8ea093',
    textDisabled: '#77857a',
    primary: '#8fc7a5',
    primaryHover: '#b3d9c1',
    primaryPressed: '#6eaa85',
    primarySoft: '#263a2b',
    onPrimary: '#111811',
    infoSoft: '#263a2b',
    success: '#8fc7a5',
    successSoft: '#223226',
    warning: '#f0bc67',
    warningSoft: '#352b19',
    danger: '#f49a8f',
    dangerSoft: '#3b211e',
    shadow: '0 12px 30px rgba(0, 0, 0, 0.22)',
  },
} as const

function alpha(hex: string, opacity: number): string {
  const value = hex.replace('#', '')
  const full = value.length === 3 ? value.split('').map((c) => c + c).join('') : value
  const r = Number.parseInt(full.slice(0, 2), 16)
  const g = Number.parseInt(full.slice(2, 4), 16)
  const b = Number.parseInt(full.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${opacity})`
}

export function buildThemeOverrides(mode: ThemeMode): GlobalThemeOverrides {
  const c = palette[mode]
  const focusRing = `0 0 0 2px ${alpha(c.primary, 0.2)}`
  const errorRing = `0 0 0 2px ${alpha(c.danger, 0.2)}`
  const warningRing = `0 0 0 2px ${alpha(c.warning, 0.2)}`

  return {
    common: {
      primaryColor: c.primary,
      primaryColorHover: c.primaryHover,
      primaryColorPressed: c.primaryPressed,
      primaryColorSuppl: c.primaryHover,
      infoColor: c.primary,
      infoColorHover: c.primaryHover,
      infoColorPressed: c.primaryPressed,
      infoColorSuppl: c.primaryHover,
      successColor: c.success,
      successColorHover: c.primaryHover,
      successColorPressed: c.primaryPressed,
      successColorSuppl: c.primaryHover,
      warningColor: c.warning,
      warningColorHover: mode === 'dark' ? '#f7cd85' : '#a66b1e',
      warningColorPressed: mode === 'dark' ? '#dba64d' : '#744a12',
      warningColorSuppl: mode === 'dark' ? '#f7cd85' : '#a66b1e',
      errorColor: c.danger,
      errorColorHover: mode === 'dark' ? '#ffb3a9' : '#bd4f44',
      errorColorPressed: mode === 'dark' ? '#e07f74' : '#8a332b',
      errorColorSuppl: mode === 'dark' ? '#ffb3a9' : '#bd4f44',
      textColorBase: c.text1,
      textColor1: c.text1,
      textColor2: c.text2,
      textColor3: c.text3,
      textColorDisabled: c.textDisabled,
      placeholderColor: c.text3,
      placeholderColorDisabled: c.textDisabled,
      bodyColor: c.bgPage,
      cardColor: c.bgCard,
      modalColor: c.bgCard,
      popoverColor: c.bgCard,
      tableColor: c.bgCard,
      inputColor: c.bgCard,
      inputColorDisabled: c.bgHover,
      actionColor: c.bgSider,
      tabColor: c.bgSider,
      tagColor: c.bgSider,
      borderColor: c.border,
      dividerColor: c.border,
      hoverColor: c.bgHover,
      pressedColor: c.bgActive,
      closeColorHover: c.bgHover,
      closeColorPressed: c.bgActive,
      closeIconColor: c.text3,
      closeIconColorHover: c.text1,
      closeIconColorPressed: c.text1,
      borderRadius: '10px',
      borderRadiusSmall: '8px',
      fontSize: '15px',
      boxShadow1: c.shadow,
      boxShadow2: c.shadow,
      boxShadow3: c.shadow,
    },
    Button: {
      borderRadiusTiny: '999px',
      borderRadiusSmall: '999px',
      borderRadiusMedium: '999px',
      borderRadiusLarge: '999px',
      textColor: c.text2,
      textColorHover: c.primary,
      textColorPressed: c.primaryPressed,
      textColorFocus: c.primary,
      textColorDisabled: c.textDisabled,
      textColorText: c.text2,
      textColorTextHover: c.primary,
      textColorTextPressed: c.primaryPressed,
      textColorTextFocus: c.primary,
      textColorTextDisabled: c.textDisabled,
      textColorGhost: c.text2,
      textColorGhostHover: c.primary,
      textColorGhostPressed: c.primaryPressed,
      textColorGhostFocus: c.primary,
      textColorGhostDisabled: c.textDisabled,
      border: `1px solid ${c.border}`,
      borderHover: `1px solid ${c.primary}`,
      borderPressed: `1px solid ${c.primaryPressed}`,
      borderFocus: `1px solid ${c.primary}`,
      borderDisabled: `1px solid ${c.borderStrong}`,
      colorHover: c.bgHover,
      colorPressed: c.bgActive,
      colorFocus: c.bgHover,
      colorPrimary: c.primary,
      colorHoverPrimary: c.primaryHover,
      colorPressedPrimary: c.primaryPressed,
      colorFocusPrimary: c.primaryHover,
      colorDisabledPrimary: c.borderStrong,
      textColorPrimary: c.onPrimary,
      textColorHoverPrimary: c.onPrimary,
      textColorPressedPrimary: c.onPrimary,
      textColorFocusPrimary: c.onPrimary,
      textColorDisabledPrimary: c.onPrimary,
      textColorTextPrimary: c.primary,
      textColorTextHoverPrimary: c.primaryHover,
      textColorTextPressedPrimary: c.primaryPressed,
      textColorTextFocusPrimary: c.primaryHover,
      textColorTextDisabledPrimary: c.textDisabled,
      borderPrimary: `1px solid ${c.primary}`,
      borderHoverPrimary: `1px solid ${c.primaryHover}`,
      borderPressedPrimary: `1px solid ${c.primaryPressed}`,
      borderFocusPrimary: `1px solid ${c.primaryHover}`,
      borderDisabledPrimary: `1px solid ${c.borderStrong}`,
      rippleColor: c.primary,
      rippleColorPrimary: c.primary,
    },
    Input: {
      color: c.bgCard,
      colorHover: c.bgCard,
      colorFocus: c.bgCard,
      colorDisabled: c.bgHover,
      textColor: c.text1,
      textColorDisabled: c.textDisabled,
      placeholderColor: c.text3,
      placeholderColorDisabled: c.textDisabled,
      caretColor: c.primary,
      border: `1px solid ${c.border}`,
      borderHover: `1px solid ${c.primaryHover}`,
      borderFocus: `1px solid ${c.primary}`,
      borderDisabled: `1px solid ${c.borderStrong}`,
      boxShadowFocus: focusRing,
      borderError: `1px solid ${c.danger}`,
      borderHoverError: `1px solid ${c.danger}`,
      borderFocusError: `1px solid ${c.danger}`,
      boxShadowFocusError: errorRing,
      caretColorError: c.danger,
      borderWarning: `1px solid ${c.warning}`,
      borderHoverWarning: `1px solid ${c.warning}`,
      borderFocusWarning: `1px solid ${c.warning}`,
      boxShadowFocusWarning: warningRing,
      caretColorWarning: c.warning,
      iconColor: c.text3,
      iconColorHover: c.primary,
      iconColorPressed: c.primaryPressed,
      iconColorDisabled: c.textDisabled,
      clearColor: c.text3,
      clearColorHover: c.text1,
      clearColorPressed: c.primaryPressed,
      suffixTextColor: c.text2,
    },
    Select: {
      menuBoxShadow: c.shadow,
    },
    Card: {
      color: c.bgCard,
      colorModal: c.bgCard,
      colorPopover: c.bgCard,
      colorEmbedded: c.bgSider,
      colorEmbeddedModal: c.bgSider,
      colorEmbeddedPopover: c.bgSider,
      textColor: c.text2,
      titleTextColor: c.text1,
      borderColor: c.border,
      actionColor: c.bgSider,
      boxShadow: c.shadow,
      borderRadius: '14px',
    },
    Modal: {
      color: c.bgCard,
      textColor: c.text2,
      boxShadow: c.shadow,
    },
    Popover: {
      color: c.bgCard,
      textColor: c.text2,
      dividerColor: c.border,
      boxShadow: c.shadow,
      borderRadius: '12px',
    },
    Tabs: {
      tabTextColorLine: c.text1,
      tabTextColorActiveLine: c.primary,
      tabTextColorHoverLine: c.primary,
      tabTextColorDisabledLine: c.textDisabled,
      barColor: c.primary,
      tabBorderColor: c.border,
      paneTextColor: c.text2,
      tabFontWeightActive: '600',
      tabFontWeight: '500',
    },
    Switch: {
      railColor: c.borderStrong,
      railColorActive: c.primary,
      buttonColor: c.bgCard,
      iconColor: c.text3,
      textColor: c.onPrimary,
      boxShadowFocus: focusRing,
    },
    Alert: {
      borderRadius: '12px',
      border: `1px solid ${c.border}`,
      color: c.bgSider,
      titleTextColor: c.text1,
      contentTextColor: c.text2,
      iconColor: c.text2,
      colorInfo: c.infoSoft,
      borderInfo: `1px solid ${c.border}`,
      titleTextColorInfo: c.text1,
      contentTextColorInfo: c.text2,
      iconColorInfo: c.primary,
      colorSuccess: c.successSoft,
      borderSuccess: `1px solid ${c.border}`,
      titleTextColorSuccess: c.text1,
      contentTextColorSuccess: c.text2,
      iconColorSuccess: c.success,
      colorWarning: c.warningSoft,
      borderWarning: `1px solid ${alpha(c.warning, 0.35)}`,
      titleTextColorWarning: c.text1,
      contentTextColorWarning: c.text2,
      iconColorWarning: c.warning,
      colorError: c.dangerSoft,
      borderError: `1px solid ${alpha(c.danger, 0.3)}`,
      titleTextColorError: c.text1,
      contentTextColorError: c.text2,
      iconColorError: c.danger,
    },
    Empty: {
      textColor: c.text3,
      iconColor: c.borderStrong,
      extraTextColor: c.text2,
    },
    Form: {
      labelTextColor: c.text1,
      asteriskColor: c.danger,
      feedbackTextColor: c.text3,
      feedbackTextColorError: c.danger,
      feedbackTextColorWarning: c.warning,
    },
    Tag: {
      borderRadius: '999px',
      color: c.bgSider,
      textColor: c.text2,
      border: `1px solid ${c.border}`,
      colorInfo: c.infoSoft,
      textColorInfo: c.primary,
      borderInfo: `1px solid ${c.border}`,
      colorSuccess: c.successSoft,
      textColorSuccess: c.success,
      borderSuccess: `1px solid ${c.border}`,
      colorWarning: c.warningSoft,
      textColorWarning: c.warning,
      borderWarning: `1px solid ${alpha(c.warning, 0.35)}`,
      colorError: c.dangerSoft,
      textColorError: c.danger,
      borderError: `1px solid ${alpha(c.danger, 0.3)}`,
    },
  }
}
