import { createApp } from 'vue'
import { Icon } from '@iconify/vue'
import App from './App.vue'
import { loadThemeMode, themeKey, createThemeApi } from './theme'

// 根主题与模块标识在 Vue 挂载前同步，首帧即采用知伴绿色样式。
document.documentElement.dataset.theme = loadThemeMode()
document.documentElement.dataset.zhibanModule = 'heart'

const app = createApp(App)
app.provide(themeKey, createThemeApi())
app.component('Icon', Icon)
app.mount('#app')
