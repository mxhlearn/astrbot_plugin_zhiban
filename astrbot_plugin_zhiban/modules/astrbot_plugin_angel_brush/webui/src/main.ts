import { createApp } from 'vue'
import { Icon } from '@iconify/vue'
import App from './App.vue'
import { createThemeApi, themeKey } from './theme'

const theme = createThemeApi()
document.documentElement.dataset.theme = 'light'
document.documentElement.dataset.zhibanModule = 'brush'

// 宿主上下文若已就绪，在挂载前同步一次，避免先蓝后绿或深浅色跳变。
try {
  theme.syncFromHost(window.AstrBotPluginPage?.getContext?.())
} catch {
  /* 宿主尚未注入时保持首帧知伴浅绿 */
}
document.documentElement.dataset.theme = theme.mode.value

const app = createApp(App)
app.provide(themeKey, createThemeApi())
app.component('Icon', Icon)
app.mount('#app')
