/**
 * AstrBot Plugin Page Bridge API 封装
 * 后端路由已带插件名前缀，这里 endpoint 传相对路径。
 *
 * 页面运行在 AstrBot 工作台的沙箱 iframe 中时，只允许通过宿主注入的
 * window.AstrBotPluginPage 访问后端。这里不再回退到直接 fetch：
 * 沙箱内没有同源凭据，绕过宿主也会破坏鉴权与消息校验边界。
 */

interface BridgeContext {
  pluginName: string
  displayName: string
  pageName: string
  pageTitle: string
  locale: string
  i18n: Record<string, unknown>
  isDark?: boolean
}

interface Bridge {
  ready(): Promise<BridgeContext>
  getContext(): BridgeContext
  getLocale(): string
  getI18n(): Record<string, unknown>
  onContext(handler: (context: BridgeContext) => void): () => void
  apiGet(endpoint: string, params?: Record<string, unknown>): Promise<unknown>
  apiPost(endpoint: string, body?: unknown): Promise<unknown>
  upload(endpoint: string, file: File): Promise<unknown>
  download(endpoint: string, params?: Record<string, unknown>, filename?: string): Promise<void>
}

declare global {
  interface Window {
    AstrBotPluginPage?: Bridge
  }
}

export const BRIDGE_UNAVAILABLE_MESSAGE = '页面桥接未就绪，请从 AstrBot 知伴工作台进入'
export const BRIDGE_READY_TIMEOUT_MS = 15000

let bridgeReady = false
let bridgeContext: BridgeContext | null = null

/**
 * 每次调用时重新读取，兼容宿主在 Vue 挂载之后才注入 bridge 的情况。
 */
function getBridge(): Bridge | null {
  if (typeof window !== 'undefined' && window.AstrBotPluginPage) {
    return window.AstrBotPluginPage
  }
  return null
}

function plain<T>(value: T): T {
  return value === undefined ? value : (JSON.parse(JSON.stringify(value)) as T)
}

function requireBridge(): Bridge {
  const bridge = getBridge()
  if (!bridge) throw new Error(BRIDGE_UNAVAILABLE_MESSAGE)
  return bridge
}

export function useBridge() {
  async function init(): Promise<BridgeContext | null> {
    if (bridgeReady && bridgeContext) return bridgeContext

    const bridge = getBridge()
    if (!bridge) {
      console.warn('[Bridge] AstrBotPluginPage 不可用，页面以受限状态运行')
      return null
    }

    try {
      let timer: number | undefined
      const timeout = new Promise<never>((_, reject) => {
        timer = window.setTimeout(
          () => reject(new Error('页面桥接初始化超时')),
          BRIDGE_READY_TIMEOUT_MS,
        )
      })
      try {
        bridgeContext = await Promise.race([bridge.ready(), timeout])
      } finally {
        if (timer !== undefined) window.clearTimeout(timer)
      }
      bridgeReady = true
      return bridgeContext
    } catch (e) {
      console.error('[Bridge] 初始化失败:', e)
      bridgeReady = false
      bridgeContext = null
      return null
    }
  }

  async function apiGet<T = unknown>(endpoint: string, params?: Record<string, unknown>): Promise<T> {
    const bridge = requireBridge()
    return (await bridge.apiGet(endpoint, plain(params))) as T
  }

  async function apiPost<T = unknown>(endpoint: string, body?: unknown): Promise<T> {
    const bridge = requireBridge()
    return (await bridge.apiPost(endpoint, plain(body))) as T
  }

  return { init, apiGet, apiPost }
}
