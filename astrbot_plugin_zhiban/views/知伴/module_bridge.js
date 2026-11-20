// 知伴模块桥接；内容变更会自动更新 cache key。
(() => {
  const CHANNEL = 'astrbot-plugin-page';
  const modules = [
    { key: 'heart', label: '聊天互动', logo: 'heart.png', page: true, group: '聊天系统', groupKey: 'chat' },
    { key: 'search', label: '联网搜索', logo: 'search.png', page: true, group: '聊天系统', groupKey: 'chat' },
    { key: 'memory', label: '记忆成长', logo: 'memory.png', page: true, group: '记忆成长', groupKey: 'memory' },
    { key: 'meme', label: '表情互动', logo: 'meme.png', page: true, group: '表达创作', groupKey: 'creative' },
    { key: 'tts', label: '语音回复', logo: 'tts.png', page: true, group: '表达创作', groupKey: 'creative' },
    { key: 'proactive', label: '主动问候', logo: 'proactive.png', page: false, group: '聊天系统', groupKey: 'chat' },
    { key: 'brush', label: '图片创作', logo: 'brush.png', page: true, group: '表达创作', groupKey: 'creative' },
    { key: 'music', label: '音乐点播', logo: 'music.png', page: true, group: '表达创作', groupKey: 'creative' },
    { key: 'eye', label: '历史查询', logo: 'eye.png', page: false, group: '聊天系统', groupKey: 'chat' },
    { key: 'qzone', label: 'QQ 动态', logo: 'qzone.png', page: true, group: 'QQ 社交', groupKey: 'social' },
    { key: 'qqprofile', label: 'QQ 资料', logo: 'qqprofile.png', page: false, group: 'QQ 社交', groupKey: 'social' },
  ];
  const groups = [
    { key: 'overview', label: '总览' },
    { key: 'chat', label: '聊天系统' },
    { key: 'memory', label: '记忆成长' },
    { key: 'creative', label: '表达创作' },
    { key: 'social', label: 'QQ 社交' },
  ];
  const apiNames = { heart: 'astrbot_plugin_angel_heart', search: 'astrbot_plugin_anysearch', memory: 'astrbot_plugin_livingmemory', meme: 'meme_manager', tts: 'astrbot_plugin_breeze_tts', brush: 'astrbot_plugin_angel_brush', music: 'astrbot_plugin_listen_music', eye: 'astrbot_plugin_angel_eye', qzone: 'astrbot_plugin_qzone_ultra', qqprofile: 'astrbot_plugin_qqprofile' };
  const appPluginName = 'astrbot_plugin_zhiban';
  const moduleScript = document.currentScript || document.querySelector('script[data-module-key]');
  const moduleKey = moduleScript?.dataset.moduleKey;
  const current = modules.find((item) => item.key === moduleKey);
  if (!current) return;
  const viewRoot = new URL('.', moduleScript.src);
  const moduleRoot = new URL(`modules/${moduleKey}/`, viewRoot);
  const initialRoute = window.__zhibanRoute && typeof window.__zhibanRoute === 'object'
    ? window.__zhibanRoute : {};
  const initialPath = String(initialRoute.path || 'index.html').replace(/^\/+/, '');
  const initialBase = initialPath.includes('/') ? initialPath.slice(0, initialPath.lastIndexOf('/') + 1) : '';
  const rootElement = document.documentElement;
  const embedded = rootElement.dataset.zhibanEmbedded === 'true'
    || rootElement.dataset.zhibanHostFrame === 'true'
    || new URL(window.location.href).searchParams.get('embedded') === 'frame';
  const original = window.AstrBotPluginView || window.AstrBotPluginPage;

  function routeBasePath(value) {
    const path = String(value || '').trim().replace(/^\/+/, '');
    if (!path || path.includes('\\') || path.split('/').some((part) => !part || part === '.' || part === '..')) return '';
    return path.endsWith('.html') ? path.slice(0, path.lastIndexOf('/') + 1) : (path.endsWith('/') ? path : path + '/');
  }

  function modulePageRoot(route = initialRoute) {
    const base = routeBasePath(route?.base || route?.path || initialBase || '');
    return base ? new URL(`modules/${moduleKey}/${base}`, viewRoot) : moduleRoot;
  }

  function moduleContext(context) {
    return {
      ...(context || {}),
      pluginName: apiNames[moduleKey],
      displayName: '知伴',
      pageName: moduleKey,
      pageTitle: current.label,
      locale: context?.locale || 'zh-CN',
      subpage: context?.subpage || initialRoute.subpage || '',
      subpageHash: context?.subpageHash || initialRoute.subpageHash || initialRoute.hash || '',
      query: context?.query && typeof context.query === 'object'
        ? { ...initialRoute.query, ...context.query }
        : { ...(initialRoute.query || {}) },
      hash: String(context?.hash || initialRoute.hash || initialRoute.subpageHash || ''),
      path: String(context?.path || initialRoute.path || ''),
    };
  }

  const ROUTE_QUERY_KEY_RE = /^[a-z][a-z0-9_]{0,40}$/i;
  const RESERVED_ROUTE_QUERY_KEYS = new Set(['asset_token', 'embedded', 'zhiban_panel', 'theme']);

  function moduleRelativePath(url) {
    let pathname;
    try {
      pathname = decodeURIComponent(String(url?.pathname || ''));
    } catch {
      return '';
    }
    if (!pathname || pathname.includes('\\') || pathname.includes('\0') ||
        pathname.includes('://') || pathname.includes('?') || pathname.includes('#') ||
        /(?:^|\/)\.{1,2}(?:\/|$)/.test(pathname)) return '';
    const marker = `/modules/${moduleKey}/`;
    const markerIndex = pathname.indexOf(marker);
    if (markerIndex < 0) return '';
    let path = pathname.slice(markerIndex + marker.length);
    if (path.endsWith('/')) path += 'index.html';
    if (!path || path.length > 240 || path.split('/').some((part) => !part || part === '.' || part === '..')) return '';
    return path;
  }

  function resolveModuleTarget(target, options = {}) {
    const pageRoot = modulePageRoot();
    const rawTarget = String(target || '').trim();
    if (!rawTarget || rawTarget.includes('\\')) return null;
    const absolute = /^(?:[a-z][a-z0-9+.-]*:|\/\/|\/)/i.test(rawTarget);
    const rawPathText = rawTarget.split(/[?#]/, 1)[0];
    let decodedRawPath = rawPathText;
    try {
      decodedRawPath = decodeURIComponent(rawPathText);
    } catch {
      return null;
    }
    // Relative ../ links are valid from a nested page and are contained by
    // the two controlled bases below. Absolute signed URLs must never contain
    // traversal segments before URL normalization.
    if (absolute && /(?:^|\/)\.{1,2}(?:\/|$)/.test(decodedRawPath)) return null;

    // data-module-target values are module-relative; ordinary anchors are
    // page-relative. Try both controlled bases, but always reject URLs outside
    // this exact module root (never cross-module or sandbox escape).
    // data-module-target is explicitly module-root relative. Ordinary href /
    // data-nav-target values stay page relative, which lets a nested page link
    // back to ../settings/index.html without escaping this module root.
    const explicitModulePath = rawTarget.startsWith('#') || options.moduleRelative === true;
    const bases = explicitModulePath ? [moduleRoot] : [moduleRoot, pageRoot];
    for (const base of bases) {
      const candidate = rawTarget.startsWith('#') ? `${initialPath}${rawTarget}` : rawTarget;
      let url;
      try { url = new URL(candidate, base); } catch { continue; }
      if (url.origin !== moduleRoot.origin) continue;
      const path = moduleRelativePath(url);
      if (!path) continue;
      const query = {};
      let count = 0;
      for (const [key, value] of url.searchParams) {
        if (!ROUTE_QUERY_KEY_RE.test(key) || RESERVED_ROUTE_QUERY_KEYS.has(key) || count >= 8) continue;
        const text = String(value ?? '');
        if (text.length > 240 || /[\r\n\0]/u.test(text)) continue;
        query[key] = text;
        count += 1;
      }
      const hash = url.hash.replace(/^#/, '');
      if (hash.length > 120 || /[\s<>"']/u.test(hash)) continue;
      return { path, hash, query };
    }
    return null;
  }

  function navigateModule(target) {
    if (!embedded) return false;
    const route = resolveModuleTarget(target);
    if (!route) return false;
    const token = context.appReadyToken || rootElement.dataset.appReadyToken || '';
    if (!token) return false;
    const wireRoute = { path: route.path, hash: route.hash, query: route.query };
    if (!/^[a-z0-9][a-z0-9/_-]*\.html$/i.test(wireRoute.path) ||
        wireRoute.path.split('/').some((part) => !part || part === '.' || part === '..')) {
      return false;
    }
    send('navigate', { module: moduleKey, token, ...wireRoute });
    return true;
  }

  function routeFromLink(link) {
    if (!link || link.target === '_blank' || link.hasAttribute('download')) return null;
    const href = link.getAttribute('href') || '';
    if (!href || href.startsWith('javascript:') || href.startsWith('#')) return null;
    const route = resolveModuleTarget(href);
    if (!route || !(route.path.endsWith('.html') || route.path.endsWith('/'))) return null;
    return route;
  }

  function installRouteBridge() {
    if (!embedded) return;
    // The bridge owns only the fallback path. Module pages that bind their own
    // controls call ZhibanModule.navigate directly; intercepting those clicks
    // here would consume them twice and could swallow a failed navigation.
    document.addEventListener('click', (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const control = event.target?.closest?.('a[data-zhiban-nav-bound], button[data-zhiban-nav-bound]');
      if (control) return;
      const link = event.target?.closest?.('a[href], button[data-module-target]');
      if (!link || link.target === '_blank' || link.hasAttribute('download')) return;
      const target = link.dataset.moduleTarget || link.getAttribute('href') || '';
      const route = resolveModuleTarget(target);
      if (!route || !(route.path.endsWith('.html') || route.path.endsWith('/'))) return;
      event.preventDefault();
      navigateModule(target);
    });
    const applyHash = () => {
      const hash = moduleContext(context).subpageHash;
      if (!hash) return;
      const target = document.getElementById(hash) || document.querySelector(`[data-settings-tab="${CSS.escape(hash)}"]`);
      if (target) setTimeout(() => target.scrollIntoView({ block: 'start', behavior: 'auto' }), 40);
    };
    window.addEventListener('hashchange', () => {
      const hash = String(window.location.hash || '').replace(/^#/, '');
      if (!hash || !embedded) return;
      navigateModule(`#${hash}`);
    });
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', applyHash, { once: true });
    else applyHash();
  }

  const HOST_PALETTE = {
    light: {
      '--bg-app': '#f5f8f4', '--bg-base': '#f5f8f4', '--bg-sidebar': '#eef5ec',
      '--bg-card': '#ffffff', '--bg-hover': '#e7f0e7', '--bg-active': '#ddeedc',
      '--bg-input': '#ffffff', '--bg-overlay': 'rgba(255,255,255,.94)', '--bg-tint': '#eef5ec',
      '--bg-toolbar': '#ffffff', '--bg-table-head': '#eef5ec', '--screen-overlay': 'rgba(30,50,38,.24)',
      '--graph-surface': '#f8fbf7', '--border-light': '#dce6da', '--border-normal': '#bdcfbb',
      '--border-color': '#dce6da', '--border-focus': '#2f6b4f', '--text-primary': '#24382c',
      '--text-secondary': '#617367', '--text-tertiary': '#718477', '--text-inverse': '#ffffff',
      '--accent': '#2f6b4f', '--accent-color': '#2f6b4f', '--accent-light': '#ddeedc',
      '--accent-hover': '#24563f', '--signal': '#9dc7ac', '--signal-soft': '#e8f3e7',
      '--coral': '#9b5c46', '--cyan': '#3f7661', '--gold': '#b07b36',
      '--success': '#2f6b4f', '--success-light': '#ddeedc', '--warning': '#8a5a1f',
      '--warning-light': '#f7ecd9', '--danger': '#b0443f', '--danger-light': '#f8e4e1',
      '--danger-hover': '#8f342f', '--node-topic': '#78a94b', '--node-person': '#2a9e96',
      '--node-fact': '#c58c2a', '--node-summary': '#df6d62', '--node-other': '#74868a',
      '--primary-color': '#2f6b4f', '--primary': '#2f6b4f', '--link-color': '#2f6b4f',
    },
    dark: {
      '--bg-app': '#111811', '--bg-base': '#111811', '--bg-sidebar': '#162117',
      '--bg-card': '#1b261c', '--bg-hover': '#243528', '--bg-active': '#2a3f2d',
      '--bg-input': '#1b261c', '--bg-overlay': 'rgba(17,24,17,.95)', '--bg-tint': '#162117',
      '--bg-toolbar': '#1b261c', '--bg-table-head': '#162117', '--screen-overlay': 'rgba(0,0,0,.55)',
      '--graph-surface': '#131c14', '--border-light': '#354637', '--border-normal': '#4b6150',
      '--border-color': '#354637', '--border-focus': '#8fc7a5', '--text-primary': '#eef5ef',
      '--text-secondary': '#aebbad', '--text-tertiary': '#91a394', '--text-inverse': '#101611',
      '--accent': '#8fc7a5', '--accent-color': '#8fc7a5', '--accent-light': '#263a2b',
      '--accent-hover': '#b3d9c1', '--signal': '#b3d9c1', '--signal-soft': '#263a2b',
      '--coral': '#d79a84', '--cyan': '#6fb59a', '--gold': '#d3a35b',
      '--success': '#8fc7a5', '--success-light': '#203427', '--warning': '#e4b066',
      '--warning-light': '#3b2d19', '--danger': '#f08b84', '--danger-light': '#3c211f',
      '--danger-hover': '#f6aaa4', '--node-topic': '#8fbe62', '--node-person': '#56b8ae',
      '--node-fact': '#d9a64c', '--node-summary': '#e88276', '--node-other': '#92a4a8',
      '--primary-color': '#8fc7a5', '--primary': '#8fc7a5', '--link-color': '#8fc7a5',
    },
  };

  function paletteCss(selector, palette) {
    const vars = Object.entries(palette).map(([key, value]) => `${key}:${value}!important`).join(';');
    return `${selector}{${vars}}`;
  }

  function applyHostTheme(next) {
    if (typeof next?.isDark !== 'boolean' || !rootElement?.dataset) return;
    rootElement.dataset.theme = next.isDark ? 'dark' : 'light';
    if (rootElement.style) rootElement.style.colorScheme = rootElement.dataset.theme;
  }

  function installFirstPaintTheme() {
    if (!rootElement?.dataset) return;
    rootElement.dataset.zhibanEmbedded = embedded ? 'true' : 'shell';
    if (!document.getElementById('zhiban-first-paint')) {
      const early = document.createElement('style');
      early.id = 'zhiban-first-paint';
      early.textContent = [
        paletteCss('html[data-zhiban-embedded="true"]', HOST_PALETTE.light),
        paletteCss('html[data-zhiban-embedded="true"][data-theme="dark"]', HOST_PALETTE.dark),
        'html[data-zhiban-embedded="true"] { color-scheme:light;background:var(--bg-app)!important;color:var(--text-primary)!important; }',
        'html[data-zhiban-embedded="true"][data-theme="dark"] { color-scheme:dark; }',
        'html[data-zhiban-embedded="true"] body { background:var(--bg-app)!important;color:var(--text-primary)!important;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif!important; }',
        'html[data-zhiban-embedded="true"] :is(.n-button--primary-type,.btn-primary,.button-primary,.el-button--primary,.ant-btn-primary) { background:var(--accent)!important;border-color:var(--accent)!important;color:var(--text-inverse)!important; }',
      ].join('\n');
      (document.head || document.documentElement).append(early);
    }
  }
  installFirstPaintTheme();

  function modulePath(endpoint) {
    let value = String(endpoint || '').trim().replace(/^\/+/, '');
    if (!value || value.indexOf(String.fromCharCode(92)) >= 0 || value.includes('://') || value.includes('?') || value.includes('#') || value.split('/').some((part) => !part || part === '.' || part === '..')) throw new Error('模块 API 路径无效');
    if (value === 'bridge/auth_token') return '';
    const ownName = apiNames[moduleKey];
    if (value.startsWith(ownName + '/')) value = value.slice(ownName.length + 1);
    else if (value === ownName || value === appPluginName || value.startsWith(appPluginName + '/') || Object.entries(apiNames).some(([key, name]) => key !== moduleKey && (value === name || value.startsWith(name + '/')))) throw new Error('模块 API 范围不匹配');
    return value;
  }

  function proxyEndpoint(endpoint) {
    const path = modulePath(endpoint);
    return path ? 'ui/module_api/' + moduleKey + '/' + path : '';
  }

  const contextHandlers = new Set();
  const pendingRequests = new Map();
  const sseHandlers = new Map();
  let context = moduleContext({});
  let requestCounter = 0;
  let subscriptionCounter = 0;
  let bridgeReadySent = false;
  let appReadySent = false;
  let resolveReady = null;
  let rejectReady = null;
  let readyTimer = null;
  const READY_TIMEOUT_MS = 12000;
  const REQUEST_TIMEOUT_MS = 60000;
  const TRANSFER_TIMEOUT_MS = 120000;

  const readyPromise = new Promise((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });

  function targetOrigin() {
    return window.location.origin === 'null' ? '*' : window.location.origin;
  }

  function send(kind, payload, transfer) {
    if (window.parent === window) return;
    window.parent.postMessage(
      { channel: CHANNEL, kind, ...(payload || {}) },
      targetOrigin(),
      transfer || [],
    );
  }

  function emitBridgeReady() {
    if (!embedded || bridgeReadySent) return;
    bridgeReadySent = true;
    send('ready', { module: moduleKey });
  }

  function settleReady(nextContext) {
    context = moduleContext({ ...context, ...(nextContext || {}) });
    applyHostTheme(context);
    if (context.appReadyToken) rootElement.dataset.appReadyToken = context.appReadyToken;
    if (readyTimer) window.clearTimeout(readyTimer);
    readyTimer = null;
    if (resolveReady) {
      const resolve = resolveReady;
      resolveReady = null;
      rejectReady = null;
      resolve(context);
    }
    for (const handler of contextHandlers) {
      try { handler(context); } catch (error) { console.error('[知伴] context handler failed:', error); }
    }
  }

  function makeRequest(action, payload, timeoutMs = REQUEST_TIMEOUT_MS) {
    if (!embedded) throw new Error('当前页面不在知伴工作台内');
    requestCounter += 1;
    const requestId = `zhiban_req_${requestCounter}`;
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        pendingRequests.delete(requestId);
        reject(new Error(`模块请求超时（阶段：${action}）`));
      }, timeoutMs);
      pendingRequests.set(requestId, {
        resolve: (data) => { window.clearTimeout(timer); pendingRequests.delete(requestId); resolve(data); },
        reject: (error) => { window.clearTimeout(timer); pendingRequests.delete(requestId); reject(error); },
      });
      send('request', { requestId, action, ...(payload || {}) });
    });
  }

  async function ready() {
    if (!embedded) {
      if (typeof original?.ready === 'function') return moduleContext(await original.ready());
      throw new Error('AstrBot 页面桥接不可用，请从知伴工作台进入');
    }
    emitBridgeReady();
    if (resolveReady && !readyTimer) {
      readyTimer = window.setTimeout(() => {
        const reject = rejectReady;
        resolveReady = null;
        rejectReady = null;
        readyTimer = null;
        reject?.(new Error('知伴工作台桥接超时（阶段：桥接握手）'));
      }, READY_TIMEOUT_MS);
    }
    return readyPromise;
  }

  const bridged = {
    async ready() { return ready(); },
    getContext() { return moduleContext(context); },
    getLocale() { return moduleContext(context).locale; },
    getI18n() { return context.i18n || {}; },
    onContext(handler) {
      if (typeof handler !== 'function') return () => {};
      contextHandlers.add(handler);
      return () => contextHandlers.delete(handler);
    },
    apiGet(endpoint, params) {
      const path = modulePath(endpoint);
      if (!path) return Promise.resolve({ token: '' });
      if (!embedded) return original.apiGet(proxyEndpoint(endpoint), params);
      return makeRequest('api:get', { endpoint: path, params });
    },
    apiPost(endpoint, body) {
      const path = modulePath(endpoint);
      if (!embedded) return original.apiPost(proxyEndpoint(endpoint), body);
      return makeRequest('api:post', { endpoint: path, body });
    },
    async upload(endpoint, file) {
      const path = modulePath(endpoint);
      if (!embedded) return original.upload(proxyEndpoint(endpoint), file);
      const buffer = await file.arrayBuffer();
      return makeRequest('files:upload', {
        endpoint: path,
        fileName: file.name || 'upload.bin',
        fileType: file.type || 'application/octet-stream',
        fileLastModified: file.lastModified || Date.now(),
        fileBuffer: buffer,
      }, TRANSFER_TIMEOUT_MS);
    },
    download(endpoint, params, filename) {
      const path = modulePath(endpoint);
      if (!embedded) return original.download(proxyEndpoint(endpoint), params, filename);
      return makeRequest('files:download', { endpoint: path, params, filename }, TRANSFER_TIMEOUT_MS);
    },
    subscribeSSE(endpoint, handlers, params) {
      const path = modulePath(endpoint);
      if (!embedded) return original.subscribeSSE(proxyEndpoint(endpoint), handlers, params);
      subscriptionCounter += 1;
      const subscriptionId = `zhiban_sub_${subscriptionCounter}`;
      sseHandlers.set(subscriptionId, handlers || {});
      return makeRequest('sse:subscribe', { endpoint: path, subscriptionId, params })
        .catch((error) => { sseHandlers.delete(subscriptionId); throw error; })
        .then(() => subscriptionId);
    },
    async unsubscribeSSE(subscriptionId) {
      if (!embedded) return original.unsubscribeSSE(subscriptionId);
      try {
        return await makeRequest('sse:unsubscribe', { subscriptionId }, 15000);
      } finally {
        sseHandlers.delete(subscriptionId);
      }
    },
  };
  window.AstrBotPluginView = window.AstrBotPluginPage = bridged;

  window.addEventListener('message', (event) => {
    if (event.source !== window.parent) return;
    const message = event.data;
    if (!message || message.channel !== CHANNEL) return;
    if (message.kind === 'context') {
      settleReady(message.context || {});
      return;
    }
    if (message.kind === 'navigation:error') {
      if (message.module !== moduleKey) return;
      const detail = {
        stage: sanitizeDetail(message.stage || '导航'),
        message: sanitizeDetail(message.message || '模块子页面无效'),
      };
      try { window.dispatchEvent(new CustomEvent('zhiban:navigation-error', { detail })); } catch { /* Compatibility. */ }
      if (typeof window.MemeUI?.showPageError === 'function') window.MemeUI.showPageError(new Error(detail.message));
      return;
    }
    if (message.kind === 'response') {
      const pending = pendingRequests.get(message.requestId);
      if (!pending) return;
      if (message.ok) pending.resolve(message.data);
      else pending.reject(new Error(message.error || '模块请求失败'));
      return;
    }
    if (message.kind === 'sse_state') {
      const handlers = sseHandlers.get(message.subscriptionId);
      if (!handlers) return;
      if (message.state === 'open') handlers.onOpen?.();
      else handlers.onError?.();
      return;
    }
    if (message.kind === 'sse_message') {
      const handlers = sseHandlers.get(message.subscriptionId);
      if (!handlers) return;
      let parsed = null;
      try { parsed = JSON.parse(message.data); } catch { /* Keep raw text. */ }
      handlers.onMessage?.({
        raw: message.data,
        parsed,
        eventType: message.eventType || 'message',
        lastEventId: message.lastEventId || '',
      });
    }
  });

  const style = document.createElement('style');
  style.id = 'zhiban-shell-style';
  style.textContent = `
    html[data-zhiban-shell="true"] { --bg-app:#f5f8f4!important;--bg-sidebar:#eef5ec!important;--bg-card:#ffffff!important;--bg-hover:#e7f0e7!important;--accent-light:#ddeedc!important;--graph-surface:#f8fbf7!important;--border-light:#dce6da!important;--border-normal:#bdcfbb!important;--text-primary:#24382c!important;--text-secondary:#617367!important;--text-tertiary:#718477!important;--text-inverse:#ffffff!important;--accent:#2f6b4f!important;--accent-hover:#24563f!important;--signal:#b7d7bd!important;--cyan:#3f7661!important;--coral:#9b5c46!important;--primary-color:#2f6b4f!important;--primary:#2f6b4f!important;--accent-color:#2f6b4f!important;--link-color:#2f6b4f!important; }
    :root { --zb-side:#eef5ec;--zb-bg:#f5f8f4;--zb-white:#fff;--zb-soft:#ddeedc;--zb-green:#2f6b4f;--zb-text:#24382c;--zb-muted:#617367;--zb-line:#dce6da; }
    :root[data-theme="dark"] { --zb-side:#162117;--zb-bg:#111811;--zb-white:#1b261c;--zb-soft:#263a2b;--zb-green:#8fc7a5;--zb-text:#eef5ef;--zb-muted:#aebbad;--zb-line:#354637; }
    html[data-zhiban-shell="true"] body { padding-left:196px!important;background:var(--zb-bg)!important;color:var(--zb-text)!important; }
    #zhiban-module-nav { position:fixed;inset:0 auto 0 0;z-index:2147483000;display:flex;flex-direction:column;width:196px;height:100vh;padding:22px 13px 16px;border-right:1px solid var(--zb-line);background:var(--zb-side);color:var(--zb-text);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;box-shadow:4px 0 18px rgba(42,70,48,.05); }
    #zhiban-module-nav * { box-sizing:border-box;letter-spacing:0; }
    #zhiban-module-nav .zb-brand { display:flex;align-items:center;gap:10px;padding:0 11px 23px;color:var(--zb-green);text-decoration:none; }
    #zhiban-module-nav .zb-brand img { width:40px;height:40px;flex:0 0 40px;border-radius:11px;object-fit:contain;background:var(--zb-white); }
    #zhiban-module-nav .zb-brand strong { display:block;font-size:20px;font-weight:650;line-height:1.25; }
    #zhiban-module-nav .zb-brand small { display:block;color:var(--zb-muted);font-size:10px;font-weight:400;letter-spacing:1.4px; }
    #zhiban-module-nav .zb-primary,#zhiban-module-nav .zb-list { display:grid;gap:6px; }
    #zhiban-module-nav .zb-primary a,#zhiban-module-nav .zb-module { display:flex;align-items:center;gap:10px;min-height:42px;padding:9px 12px;border-radius:9px;color:var(--zb-muted);text-decoration:none;font-weight:520; }
    #zhiban-module-nav .zb-primary a:hover,#zhiban-module-nav .zb-module:hover { background:color-mix(in srgb,var(--zb-soft) 58%,transparent); }
    #zhiban-module-nav .zb-primary a[aria-current="page"],#zhiban-module-nav .zb-module[aria-current="page"] { background:var(--zb-soft);color:var(--zb-green);font-weight:650; }
    #zhiban-module-nav .zb-primary-icon { display:grid;width:20px;height:20px;flex:0 0 20px;place-items:center;border:1.5px solid currentColor;border-radius:6px;font-size:9px;line-height:1; }
    #zhiban-module-nav .zb-section-label { margin:19px 10px 7px;color:var(--zb-muted);font-size:10px;font-weight:600; }
    #zhiban-module-nav .zb-module { min-height:38px;padding:7px 10px;font-size:13px; }
    #zhiban-module-nav .zb-module-mark { display:grid;width:26px;height:26px;flex:0 0 26px;place-items:center;overflow:hidden;border:1px solid var(--zb-line);border-radius:7px;background:var(--zb-white);color:var(--zb-green);font-size:10px;font-weight:650; }#zhiban-module-nav .zb-module-mark img { display:block;width:22px;height:22px;object-fit:contain;border-radius:5px; }
    #zhiban-module-nav .zb-state { width:7px;height:7px;margin-left:auto;border-radius:50%;background:var(--zb-muted); }
    #zhiban-module-nav .zb-state.running { background:#2f8b58;box-shadow:0 0 0 3px rgba(47,139,88,.12); }
    #zhiban-module-nav .zb-state.not_ready,#zhiban-module-nav .zb-state.unknown { background:#b47a20;box-shadow:0 0 0 3px rgba(180,122,32,.12); }
    #zhiban-module-nav .zb-state.failed,#zhiban-module-nav .zb-state.blocked { background:#b4473d; }
    #zhiban-business-notice { position:fixed;right:18px;bottom:18px;z-index:2147482999;max-width:min(420px,calc(100vw - 230px));padding:12px 14px;border:1px solid #d9c89e;border-radius:10px;background:#fff9ea;color:#6f4d12;box-shadow:0 10px 30px rgba(62,49,20,.14);font:12px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }
    #zhiban-business-notice strong { display:block;margin-bottom:2px;font-size:13px; }
    #zhiban-module-nav .zb-actions { display:flex;gap:7px;margin-top:13px; }
    #zhiban-module-nav .zb-actions a { flex:1;display:flex;justify-content:center;min-height:34px;padding:6px 9px;border:1px solid var(--zb-line);border-radius:8px;background:var(--zb-white);color:var(--zb-text);text-decoration:none;font-size:11px; }
    #zhiban-module-nav .zb-footer { margin-top:auto;padding:13px 10px 0;border-top:1px solid var(--zb-line);color:var(--zb-muted);font-size:10px; }
    #zhiban-module-nav .zb-footer strong { display:block;color:var(--zb-green);font-size:10px; }
    html[data-zhiban-shell="true"] .card.promo,
    html[data-zhiban-shell="true"] .card.invite {
      border:1px solid #dce6da!important;
      background:#edf4e9!important;
      background-image:none!important;
      color:#24382c!important;
      box-shadow:none!important;
    }
    html[data-zhiban-shell="true"] .card.promo button,
    html[data-zhiban-shell="true"] .card.invite button { border-color:#dce6da!important;background:#fff!important;color:#2f6b4f!important; }
    @media(prefers-reduced-motion:reduce){::view-transition-old(root),::view-transition-new(root){animation:none!important}html[data-navigating="true"] body::after{animation:none!important}}
    @media(max-width:1100px){html[data-zhiban-shell="true"] body{padding-left:0!important;padding-top:116px!important}#zhiban-module-nav{right:0;bottom:auto;width:auto;height:auto;min-height:0;padding:10px 12px;border-right:0;border-bottom:1px solid var(--zb-line)}#zhiban-module-nav .zb-brand{padding:0 4px 9px}#zhiban-module-nav .zb-brand img{width:32px;height:32px;flex-basis:32px}#zhiban-module-nav .zb-brand strong{font-size:17px}#zhiban-module-nav .zb-brand small,#zhiban-module-nav .zb-section-label,#zhiban-module-nav .zb-footer{display:none}#zhiban-module-nav .zb-primary{grid-template-columns:repeat(5,minmax(0,1fr));gap:3px}#zhiban-module-nav .zb-primary a{justify-content:center;min-height:38px;padding:6px 2px;font-size:10px;text-align:center}#zhiban-module-nav .zb-primary-icon{display:none}#zhiban-module-nav .zb-list{display:none}#zhiban-module-nav .zb-actions{position:absolute;top:14px;right:12px;margin:0}#zhiban-module-nav .zb-actions a{min-width:44px;min-height:28px;padding:3px 6px;font-size:10px}}
    @media(max-width:600px){html[data-zhiban-shell="true"] body{padding-top:164px!important}#zhiban-module-nav .zb-primary{grid-template-columns:repeat(3,minmax(0,1fr))}#zhiban-module-nav .zb-primary a{font-size:10px;line-height:1.35}}
    @view-transition { navigation: auto; }
    ::view-transition-old(root) { animation: zb-module-out .12s ease both; }
    ::view-transition-new(root) { animation: zb-module-in .16s ease both; }
    @keyframes zb-module-out { to { opacity: .35; } }
    @keyframes zb-module-in { from { opacity: .35; } to { opacity: 1; } }
    html[data-navigating="true"] { cursor: progress; }
    html[data-navigating="true"] body::after { position:fixed;top:0;left:0;z-index:2147483647;width:34%;height:2px;content:"";pointer-events:none;background:#2f6b4f;animation:zb-module-progress .75s ease-in-out infinite alternate; }
    @keyframes zb-module-progress { from { transform:translateX(-20%); } to { transform:translateX(215%); } }
    html[data-zhiban-shell="true"] .n-button--primary-type,
    html[data-zhiban-shell="true"] .btn-primary,
    html[data-zhiban-shell="true"] .button-primary,
    html[data-zhiban-shell="true"] .el-button--primary,
    html[data-zhiban-shell="true"] .ant-btn-primary { background:#2f6b4f!important;border-color:#2f6b4f!important;color:#fff!important; }
    html[data-zhiban-shell="true"] .n-button--primary-type:hover,
    html[data-zhiban-shell="true"] .btn-primary:hover,
    html[data-zhiban-shell="true"] .button-primary:hover,
    html[data-zhiban-shell="true"] .el-button--primary:hover,
    html[data-zhiban-shell="true"] .ant-btn-primary:hover { background:#24563f!important;border-color:#24563f!important; }
    html[data-zhiban-shell="true"] .n-radio-button--checked,
    html[data-zhiban-shell="true"] .n-checkbox-box--checked { border-color:#2f6b4f!important; }
    html[data-zhiban-shell="true"] .n-radio-button--checked .n-radio__label { color:#2f6b4f!important; }
    html[data-zhiban-shell="true"] .n-menu-item-content--selected { background:#e8f1e7!important; }
    html[data-zhiban-shell="true"] .n-menu-item-content--selected .n-menu-item-content-header { color:#2f6b4f!important; }
    html[data-zhiban-shell="true"] :is(input,textarea,select):focus { border-color:#2f6b4f!important; }
    html[data-zhiban-shell="true"] a[role="tab"][aria-selected="true"] { color:#2f6b4f!important;border-color:#2f6b4f!important; }
  `;
  document.head.append(style);

  function shellUrl(view, key) {
    const item = modules.find((entry) => entry.key === key) || current;
    const url = new URL('index.html', viewRoot);
    url.searchParams.set('group', view === 'overview' ? 'overview' : item.groupKey);
    url.searchParams.set('module', key);
    url.searchParams.set('view', view);
    return url.href;
  }

  function destination(item, view = 'workbench') {
    if (view === 'settings' || !item.page) return shellUrl(view, item.key);
    return new URL('modules/' + item.key + '/index.html', viewRoot).href;
  }

  function groupDestination(groupKey) {
    if (groupKey === 'overview') return shellUrl('overview', moduleKey);
    const target = modules.find((item) => item.groupKey === groupKey && item.page) || modules.find((item) => item.groupKey === groupKey);
    return target ? destination(target) : shellUrl('overview', moduleKey);
  }

  let navigationStarted = false;
  const prefetchedTargets = new Set();
  const STATUS_CACHE_KEY = 'zhiban-status-cache-v1';
  const STATUS_CACHE_TTL_MS = 5000;
  const STATUS_CACHE_PREFIX = 'zhiban-status:';

  function readStatusCache() {
    let raw = null;
    try { raw = sessionStorage.getItem(STATUS_CACHE_KEY); } catch { /* opaque sandbox origin */ }
    if (!raw && window.name.startsWith(STATUS_CACHE_PREFIX)) raw = window.name.slice(STATUS_CACHE_PREFIX.length);
    try {
      const value = JSON.parse(raw || 'null');
      if (!value || Date.now() - Number(value.savedAt || 0) > STATUS_CACHE_TTL_MS) return null;
      return value;
    } catch { return null; }
  }

  function writeStatusCache(order, states) {
    const raw = JSON.stringify({
      savedAt: Date.now(),
      menuOrder: order.map((item) => item.key),
      modules: [...states.values()],
    });
    try { sessionStorage.setItem(STATUS_CACHE_KEY, raw); } catch { /* opaque sandbox origin */ }
    window.name = STATUS_CACHE_PREFIX + raw;
  }

  function routeSignature(value) {
    const url = new URL(value, location.href);
    const path = decodeURIComponent(url.pathname).replace(/\/_t\/[^/]+\//, '/_t/:token/');
    const params = [...url.searchParams.entries()]
      .filter(([key]) => !['asset_token', 'theme', 'embedded'].includes(key))
      .sort(([a], [b]) => a.localeCompare(b));
    return url.origin + path + '?' + new URLSearchParams(params).toString();
  }

  function sameNavigationTarget(target) {
    return routeSignature(target) === routeSignature(location.href);
  }

  function prefetchTarget(target) {
    const url = new URL(target, location.href);
    const href = url.href;
    if (sameNavigationTarget(href) || prefetchedTargets.has(href)) return;
    prefetchedTargets.add(href);
    const link = document.createElement('link');
    link.rel = 'prefetch';
    link.as = 'document';
    link.href = href;
    document.head.append(link);
  }

  function navigateShell(target) {
    const url = new URL(target, location.href);
    if (sameNavigationTarget(url.href)) return false;
    if (navigationStarted) return false;
    navigationStarted = true;
    document.documentElement.dataset.navigating = 'true';
    document.documentElement.setAttribute('aria-busy', 'true');
    window.location.replace(url.href);
    return true;
  }

  function bindPrefetch(anchor) {
    const warm = () => prefetchTarget(anchor.href);
    anchor.addEventListener('pointerenter', warm, { once: true });
    anchor.addEventListener('focus', warm, { once: true });
    anchor.addEventListener('touchstart', warm, { once: true, passive: true });
  }

  function renderNavigation(order, states) {
    document.documentElement.dataset.zhibanShell = 'true';
    const existing = document.getElementById('zhiban-module-nav');
    const root = existing || document.createElement('aside');
    root.id = 'zhiban-module-nav';
    root.setAttribute('aria-label', '知伴侧栏');
    const brand = document.createElement('a');
    brand.className = 'zb-brand';
    brand.href = shellUrl('overview', moduleKey);
    const brandLogo = document.createElement('img');
    brandLogo.src = new URL('logo.png', viewRoot).href;
    brandLogo.alt = '';
    const brandText = document.createElement('span');
    const brandName = document.createElement('strong');
    brandName.textContent = '知伴';
    const brandNote = document.createElement('small');
    brandNote.textContent = '陪伴 · 自然生长';
    brandText.append(brandName, brandNote);
    brand.append(brandLogo, brandText);
    const primary = document.createElement('nav');
    primary.className = 'zb-primary';
    primary.setAttribute('aria-label', '知伴一级功能');
    const marks = { overview: '▦', chat: '◇', memory: '◉', creative: '✧', social: '○' };
    for (const group of groups) {
      const link = document.createElement('a');
      link.href = groupDestination(group.key);
      if (group.key === current.groupKey) link.setAttribute('aria-current', 'page');
      const mark = document.createElement('span');
      mark.className = 'zb-primary-icon';
      mark.textContent = marks[group.key];
      const label = document.createElement('span');
      label.textContent = group.label;
      link.append(mark, label);
      bindPrefetch(link);
      primary.append(link);
    }
    const sectionLabel = document.createElement('div');
    sectionLabel.className = 'zb-section-label';
    sectionLabel.textContent = current.group;
    const list = document.createElement('nav');
    list.className = 'zb-list';
    list.setAttribute('aria-label', current.group + '模块');
    const related = order.filter((item) => item.groupKey === current.groupKey);
    for (const item of related) {
      const link = document.createElement('a');
      link.className = 'zb-module';
      link.href = destination(item);
      link.setAttribute('aria-current', item.key === moduleKey ? 'page' : 'false');
      const mark = document.createElement('span');
      mark.className = 'zb-module-mark';
      const markImage = document.createElement('img');
      markImage.src = new URL('logos/' + item.logo, viewRoot).href;
      markImage.alt = '';
      markImage.setAttribute('aria-hidden', 'true');
      markImage.addEventListener('error', () => {
        markImage.remove();
        mark.textContent = item.label.slice(0, 1);
      }, { once: true });
      mark.append(markImage);
      const label = document.createElement('span');
      label.textContent = item.label;
      const state = document.createElement('span');
      const readyName = states.get(item.key)?.readiness?.state;
      const stateName = readyName === 'ready' ? 'running' : readyName || states.get(item.key)?.state || '';
      state.className = 'zb-state ' + stateName;
      state.setAttribute('aria-label', states.get(item.key)?.readiness?.label || stateName || '状态未知');
      link.append(mark, label, state);
      bindPrefetch(link);
      list.append(link);
    }
    const actions = document.createElement('div');
    actions.className = 'zb-actions';
    const settingsLink = document.createElement('a');
    settingsLink.href = shellUrl('settings', moduleKey);
    settingsLink.textContent = '配置当前模块';
    bindPrefetch(settingsLink);
    actions.append(settingsLink);
    const footer = document.createElement('div');
    footer.className = 'zb-footer';
    const footerStrong = document.createElement('strong');
    footerStrong.textContent = 'AstrBot · OneBot 11';
    footer.append(footerStrong, document.createTextNode('十一个模块，一个知伴'));
    root.replaceChildren(brand, primary, sectionLabel, list, actions, footer);
    if (!existing) {
      document.body.prepend(root);
      root.addEventListener('click', (event) => {
        const anchor = event.target.closest?.('a[href]');
        if (!anchor || anchor.target === '_blank') return;
        const target = new URL(anchor.href, location.href);
        if (target.origin !== location.origin) return;
        event.preventDefault();
        navigateShell(target.href);
      });
    }
    renderReadinessNotice(states.get(moduleKey));
  }

  function renderReadinessNotice(moduleState) {
    const readiness = moduleState?.readiness || {};
    if (!['not_ready', 'failed'].includes(readiness.state) || document.getElementById('zhiban-business-notice')) return;
    const notice = document.createElement('aside');
    notice.id = 'zhiban-business-notice';
    const title = document.createElement('strong');
    title.textContent = current.label + '业务未就绪';
    const detail = document.createElement('span');
    detail.textContent = readiness.detail || '请完成模块配置后再使用相关业务功能。';
    notice.append(title, detail);
    document.body.append(notice);
  }

  function installEmbeddedTheme() {
    if (!embedded) return;
    rootElement.dataset.zhibanEmbedded = 'true';
    if (document.getElementById('zhiban-embedded-theme')) return;
    const style = document.createElement('style');
    style.id = 'zhiban-embedded-theme';
    style.textContent = `
      :root {
        --zb-embed-bg: #f5f8f4;
        --zb-embed-surface: #ffffff;
        --zb-embed-soft: #ddeedc;
        --zb-embed-green: #2f6b4f;
        --zb-embed-green-dark: #24563f;
        --zb-embed-text: #24382c;
        --zb-embed-muted: #617367;
        --zb-embed-line: #dce6da;
      }
      html, body { background: var(--bg-app, var(--zb-embed-bg)) !important; color: var(--text-primary, var(--zb-embed-text)) !important; }
      body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif !important; }
      a { color: var(--zb-embed-green); }
      button, input, select, textarea { font-family: inherit !important; }
      button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible { outline-color: var(--zb-embed-green) !important; }
      :is(.card, .panel, .modal, .modal-content, .dialog, .settings-card, .config-card, .page-card) {
        border-color: var(--zb-embed-line) !important;
      }
      @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; } }
    `;
    document.head.append(style);
  }

  function sanitizeDetail(value) {
    return String(value || '')
      .replace(/asset_token=[^&\s]+/gi, 'asset_token=***')
      .replace(/Bearer\s+[^\s]+/gi, 'Bearer ***')
      .replace(/sk-[A-Za-z0-9_-]{8,}/g, 'sk-***')
      .slice(0, 240);
  }

  function installRuntimeErrorForwarding() {
    if (!embedded || window.__zhibanRuntimeErrorsBound) return;
    window.__zhibanRuntimeErrorsBound = true;
    const benignRuntimeWarning = (detail) => /ResizeObserver loop (?:completed|limit exceeded)|Script error\.|AbortError|The operation was aborted/i.test(String(detail || ''));
    window.addEventListener('error', (event) => {
      // Resource load errors have a DOM target; they are not script failures.
      if (event?.target && event.target !== window) return;
      const detail = event?.error?.message || event?.message || '模块脚本执行失败';
      if (benignRuntimeWarning(detail)) return;
      sendAppError('runtime', detail);
    });
    window.addEventListener('unhandledrejection', (event) => {
      const reason = event?.reason;
      const detail = reason?.message || String(reason || '模块异步任务失败');
      if (benignRuntimeWarning(detail)) return;
      sendAppError('runtime', detail);
    });
  }

  function meaningfulUiMounted() {
    const appRoot = document.querySelector('#app, #root, [data-zhiban-ui]');
    if (appRoot && appRoot.childElementCount > 0) return true;
    const main = document.querySelector('main, .shell, .layout');
    if (main && (main.childElementCount > 0 || (main.textContent || '').trim().length > 20)) return true;
    const body = document.body;
    if (!body) return false;
    return (body.textContent || '').trim().length > 40
      && Boolean(body.querySelector('button, input, select, textarea, nav, form'));
  }

  function waitForUiMount(timeoutMs = 15000) {
    const begin = async () => {
      if (document.readyState === 'loading') {
        await new Promise((resolve) => document.addEventListener('DOMContentLoaded', resolve, { once: true }));
      }
      return new Promise((resolve, reject) => {
        let settled = false;
        let observer = null;
        let interval = null;
        let deadline = null;
        const cleanup = () => {
          observer?.disconnect();
          if (interval) window.clearInterval(interval);
          if (deadline) window.clearTimeout(deadline);
        };
        const finish = () => {
          if (settled || !meaningfulUiMounted()) return;
          settled = true;
          cleanup();
          const afterPaint = () => resolve();
          if (typeof window.requestAnimationFrame === 'function') {
            window.requestAnimationFrame(() => window.requestAnimationFrame(afterPaint));
          } else {
            window.setTimeout(afterPaint, 0);
          }
        };
        observer = new MutationObserver(finish);
        if (document.body) observer.observe(document.body, { childList: true, subtree: true, attributes: true });
        interval = window.setInterval(finish, 250);
        deadline = window.setTimeout(() => {
          if (settled) return;
          settled = true;
          cleanup();
          reject(new Error('业务界面未完成挂载（阶段：界面挂载）'));
        }, timeoutMs);
        finish();
      });
    };
    return begin();
  }

  function sendAppError(stage, message) {
    if (!embedded) return;
    send('app:error', {
      module: moduleKey,
      token: context.appReadyToken || rootElement.dataset.appReadyToken || '',
      stage,
      message: sanitizeDetail(message),
    });
  }

  function notifyAppReady() {
    if (!embedded || appReadySent) return;
    const token = context.appReadyToken || rootElement.dataset.appReadyToken || (moduleKey + '-' + Date.now());
    appReadySent = true;
    rootElement.dataset.appReadyToken = token;
    rootElement.dataset.appReady = 'true';
    send('app:ready', {
      module: moduleKey,
      token,
      title: current.label,
    });
  }

  const moduleApi = {
    ready: () => bridged.ready(),
    notifyReady: notifyAppReady,
    reportError: sendAppError,
    isEmbedded: embedded,
    navigate: navigateModule,
    onContext(handler) {
      const unsubscribe = bridged.onContext(handler);
      if (typeof handler === 'function') {
        try { handler(moduleContext(context)); } catch { /* Keep subscription active. */ }
      }
      return unsubscribe;
    },
  };
  Object.defineProperty(moduleApi, "route", { get: () => moduleContext(context) });
  window.ZhibanModule = moduleApi;

  async function startEmbedded() {
    installEmbeddedTheme();
    installRuntimeErrorForwarding();
    installRouteBridge();
    try {
      await bridged.ready();
    } catch (error) {
      sendAppError('bridge', error?.message || error);
      return;
    }
    try {
      await waitForUiMount(15000);
      notifyAppReady();
    } catch (error) {
      sendAppError('mount', error?.message || error);
    }
  }

  async function startStandalone() {
    const cached = readStatusCache();
    let order = modules;
    let states = new Map();
    if (cached && Array.isArray(cached.modules)) {
      states = new Map(cached.modules.map((item) => [item.key, item]));
      if (Array.isArray(cached.menuOrder)) {
        const rank = new Map(cached.menuOrder.map((key, index) => [key, index]));
        order = [...modules].sort((a, b) => (rank.get(a.key) ?? 999) - (rank.get(b.key) ?? 999));
      }
    }
    renderNavigation(order, states);
    if (typeof original?.ready === 'function') {
      try { await original.ready(); } catch { /* Keep the page usable if the direct SDK is unavailable. */ }
    }
    if (cached) return;
    try {
      const result = await original.apiGet('ui/status');
      const payload = result?.data?.modules ? result.data : result?.data || result;
      states = new Map((payload.modules || []).map((item) => [item.key, item]));
      if (Array.isArray(payload.menu_order)) {
        const rank = new Map(payload.menu_order.map((key, index) => [key, index]));
        order = [...modules].sort((a, b) => (rank.get(a.key) ?? 999) - (rank.get(b.key) ?? 999));
      }
      writeStatusCache(order, states);
    } catch { /* Keep navigation available if the status request fails. */ }
    renderNavigation(order, states);
  }

  emitBridgeReady();
  const start = () => { void (embedded ? startEmbedded() : startStandalone()); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
