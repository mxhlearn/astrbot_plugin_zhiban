(() => {
  const modules = [
    { key: 'heart', label: '聊天互动', logo: 'heart.png', page: true, group: '聊天系统' },
    { key: 'memory', label: '记忆成长', logo: 'memory.png', page: true },
    { key: 'meme', label: '表情互动', logo: 'meme.png', page: true },
    { key: 'tts', label: '语音回复', logo: 'tts.png', page: true },
    { key: 'proactive', label: '主动问候', logo: 'proactive.png', page: false, group: '聊天系统' },
    { key: 'brush', label: '图片创作', logo: 'brush.png', page: true },
    { key: 'music', label: '音乐点播', logo: 'music.png', page: true },
    { key: 'eye', label: '历史查询', logo: 'eye.png', page: false, group: '聊天系统' },
    { key: 'qzone', label: 'QQ 动态', logo: 'qzone.png', page: true, group: 'QQ 社交' },
    { key: 'filter', label: '内容过滤', logo: 'filter.svg', page: false, group: '聊天系统' },
    { key: 'qqprofile', label: 'QQ 资料', logo: 'qqprofile.png', page: false, group: 'QQ 社交' },
  ];
  const apiNames = { heart: 'astrbot_plugin_angel_heart', memory: 'astrbot_plugin_livingmemory', meme: 'meme_manager', tts: 'astrbot_plugin_breeze_tts', brush: 'astrbot_plugin_angel_brush', music: 'astrbot_plugin_listen_music', eye: 'astrbot_plugin_angel_eye', qzone: 'astrbot_plugin_qzone_ultra', filter: 'astrbot_plugin_link_filter', qqprofile: 'astrbot_plugin_qqprofile' };
  const appPluginName = 'astrbot_plugin_zhiban';
  const moduleScript = document.currentScript;
  const moduleKey = moduleScript?.dataset.moduleKey;
  const viewRoot = new URL('.', moduleScript.src);
  const current = modules.find((item) => item.key === moduleKey);
  const original = window.AstrBotPluginView || window.AstrBotPluginPage;
  if (!current || !original) return;

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

  function moduleContext(context) {
    return { ...(context || {}), pluginName: apiNames[moduleKey], displayName: '知伴', pageName: moduleKey, pageTitle: current.label, locale: context?.locale || 'zh-CN' };
  }

  const bridged = Object.create(original);
  Object.assign(bridged, {
    async ready() { if (typeof original.ready === 'function') await original.ready(); return moduleContext(original.getContext?.()); },
    getContext() { return moduleContext(original.getContext?.()); },
    getLocale() { return moduleContext(original.getContext?.()).locale; },
    getI18n() { return original.getI18n?.() || {}; },
    onContext(handler) {
      if (typeof handler !== 'function' || typeof original.onContext !== 'function') return () => {};
      return original.onContext((context) => handler(moduleContext(context)));
    },
    apiGet(endpoint, params) { const path = proxyEndpoint(endpoint); return path ? original.apiGet(path, params) : Promise.resolve({ token: '' }); },
    apiPost(endpoint, body) { return original.apiPost(proxyEndpoint(endpoint), body); },
    upload(endpoint, file) { return original.upload(proxyEndpoint(endpoint), file); },
    download(endpoint, params, filename) { return original.download(proxyEndpoint(endpoint), params, filename); },
    subscribeSSE(endpoint, handlers, params) { return original.subscribeSSE(proxyEndpoint(endpoint), handlers, params); },
    unsubscribeSSE(subscriptionId) { return original.unsubscribeSSE(subscriptionId); },
  });
  window.AstrBotPluginView = window.AstrBotPluginPage = bridged;

  const style = document.createElement('style');
  style.textContent = '#zhiban-module-nav{position:fixed;right:16px;bottom:16px;z-index:2147483000;font:13px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif;color:#24302e}#zhiban-module-nav *{box-sizing:border-box;letter-spacing:0}#zhiban-module-nav .zb-trigger{display:flex;align-items:center;gap:8px;min-height:42px;padding:7px 12px;border:1px solid #d5e0dc;border-radius:22px;background:#fff;box-shadow:0 4px 18px #17221b26;color:#24302e;cursor:pointer}#zhiban-module-nav .zb-trigger img{width:26px;height:26px;object-fit:contain;border-radius:6px}#zhiban-module-nav .zb-panel{position:absolute;right:0;bottom:52px;width:min(340px,calc(100vw - 24px));max-height:min(70vh,620px);overflow:auto;border:1px solid #d5e0dc;border-radius:12px;background:#fff;box-shadow:0 12px 36px #17221b30;padding:14px}#zhiban-module-nav .zb-heading{display:flex;align-items:center;gap:10px;margin:0 0 12px;font-size:14px;font-weight:650}#zhiban-module-nav .zb-heading img{width:30px;height:30px;object-fit:contain}#zhiban-module-nav .zb-links{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-bottom:12px}#zhiban-module-nav .zb-links a{display:flex;justify-content:center;align-items:center;min-height:34px;border:1px solid #d5e0dc;border-radius:7px;color:#263a37;text-decoration:none;background:#f8faf8}#zhiban-module-nav .zb-links a[aria-current=true]{border-color:#548e80;background:#e9f4ef;color:#205a4e}#zhiban-module-nav .zb-list{display:grid;gap:3px}#zhiban-module-nav .zb-module{display:flex;align-items:center;gap:9px;min-height:38px;padding:5px 8px;border-radius:7px;color:#263a37;text-decoration:none}#zhiban-module-nav .zb-module:hover{background:#edf4f0}#zhiban-module-nav .zb-module[aria-current=true]{background:#e7f0ed;font-weight:600}#zhiban-module-nav .zb-module img{width:25px;height:25px;object-fit:contain;flex:none}#zhiban-module-nav .zb-state{width:7px;height:7px;margin-left:auto;border-radius:50%;background:#8b9994}#zhiban-module-nav .zb-state.running{background:#32a36b}#zhiban-module-nav .zb-state.failed,#zhiban-module-nav .zb-state.blocked{background:#d34c42}:root[data-theme=dark] #zhiban-module-nav{color:#edf2ed}:root[data-theme=dark] #zhiban-module-nav .zb-trigger,:root[data-theme=dark] #zhiban-module-nav .zb-panel{background:#202720;border-color:#3b473d;color:#edf2ed}:root[data-theme=dark] #zhiban-module-nav .zb-links a,:root[data-theme=dark] #zhiban-module-nav .zb-module{background:#202720;border-color:#3b473d;color:#edf2ed}:root[data-theme=dark] #zhiban-module-nav .zb-links a[aria-current=true],:root[data-theme=dark] #zhiban-module-nav .zb-module[aria-current=true]{background:#2b3e35;color:#c9f1df}';
  style.textContent += '#zhiban-module-nav .zb-group{margin-left:auto;color:#71827b;font-size:10px;font-weight:500;white-space:nowrap}#zhiban-module-nav .zb-state{margin-left:6px}';

  function shellUrl(view, key) {
    const url = new URL('index.html', viewRoot);
    url.searchParams.set('module', key);
    url.searchParams.set('view', view);
    return url.href;
  }

  function destination(item) {
    if (!item.page) return shellUrl('overview', item.key);
    return new URL('modules/' + item.key + '/index.html', viewRoot).href;
  }

  function renderNavigation(order, states) {
    const root = document.createElement('div');
    root.id = 'zhiban-module-nav';
    const trigger = document.createElement('button');
    trigger.className = 'zb-trigger';
    trigger.type = 'button';
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-label', '打开知伴模块菜单');
    trigger.title = '知伴模块菜单';
    const brand = document.createElement('img');
    brand.src = new URL('logo.png', viewRoot).href;
    brand.alt = '';
    brand.setAttribute('aria-hidden', 'true');
    const triggerText = document.createElement('span');
    triggerText.textContent = '知伴 · ' + current.label;
    trigger.append(brand, triggerText);

    const panel = document.createElement('section');
    panel.className = 'zb-panel';
    panel.hidden = true;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', '知伴模块菜单');
    const heading = document.createElement('h2');
    heading.className = 'zb-heading';
    const headingLogo = document.createElement('img');
    headingLogo.src = new URL('logos/' + current.logo, viewRoot).href;
    headingLogo.alt = '';
    headingLogo.setAttribute('aria-hidden', 'true');
    const headingText = document.createElement('span');
    headingText.textContent = current.label;
    heading.append(headingLogo, headingText);

    const viewLinks = document.createElement('nav');
    viewLinks.className = 'zb-links';
    for (const [view, label] of [['overview', '概览'], ['module', '功能'], ['settings', '配置']]) {
      const link = document.createElement('a');
      link.href = view === 'module' ? destination(current) : shellUrl(view, moduleKey);
      link.textContent = label;
      link.setAttribute('aria-current', view === 'module' ? 'true' : 'false');
      viewLinks.append(link);
    }

    const list = document.createElement('nav');
    list.className = 'zb-list';
    for (const item of order) {
      const link = document.createElement('a');
      link.className = 'zb-module';
      link.href = destination(item);
      link.setAttribute('aria-current', item.key === moduleKey ? 'true' : 'false');
      const logo = document.createElement('img');
      logo.src = new URL('logos/' + item.logo, viewRoot).href;
      logo.alt = '';
      logo.setAttribute('aria-hidden', 'true');
      const label = document.createElement('span');
      label.textContent = item.label;
      const group = document.createElement('span');
      group.className = 'zb-group';
      group.textContent = item.group || '';
      const state = document.createElement('span');
      const stateName = states.get(item.key)?.state || '';
      state.className = 'zb-state ' + stateName;
      state.setAttribute('aria-label', stateName || '状态未知');
      link.append(logo, label, group, state);
      list.append(link);
    }

    panel.append(heading, viewLinks, list);
    root.append(trigger, panel);
    document.head.append(style);
    document.body.append(root);
    trigger.addEventListener('click', () => {
      panel.hidden = !panel.hidden;
      trigger.setAttribute('aria-expanded', String(!panel.hidden));
    });
    document.addEventListener('click', (event) => {
      if (!root.contains(event.target)) {
        panel.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        panel.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
      }
    });
  }

  async function start() {
    await bridged.ready();
    let order = modules;
    let states = new Map();
    try {
      const result = await original.apiGet('ui/status');
      const payload = result?.data?.modules ? result.data : result?.data || result;
      states = new Map((payload.modules || []).map((item) => [item.key, item]));
      if (Array.isArray(payload.menu_order)) {
        const rank = new Map(payload.menu_order.map((key, index) => [key, index]));
        order = [...modules].sort((a, b) => (rank.get(a.key) ?? 999) - (rank.get(b.key) ?? 999));
      }
    } catch { /* Keep navigation available if the status request fails. */ }
    renderNavigation(order, states);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => void start(), { once: true });
  else void start();
})();
