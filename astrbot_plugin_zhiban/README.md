# 知伴

<p align="center">
  <img src="logo.png" alt="知伴 Logo" width="104">
</p>

<p align="center">
  <strong>十一个业务模块，一个知伴。</strong><br>
  面向 AstrBot 与 OneBot v11 的浅绿色中文整合应用。
</p>

<p align="center">
  <a href="#安装与切换"><img alt="Version" src="https://img.shields.io/badge/version-0.3.5-2f6b4f?style=flat-square"></a>
  <a href="#兼容范围"><img alt="AstrBot" src="https://img.shields.io/badge/AstrBot-4.29.x-4f8f6c?style=flat-square"></a>
  <a href="#兼容范围"><img alt="OneBot" src="https://img.shields.io/badge/OneBot-v11-5b7f66?style=flat-square"></a>
  <a href="#质量与验证"><img alt="Tests" src="https://img.shields.io/badge/tests-1721%20Python%20%2B%20139%20Node-2f6b4f?style=flat-square"></a>
</p>

---

## 项目简介

知伴是 AstrBot 插件，不是 Linux 专用插件，也不是独立 OneBot 服务。它把聊天、LivingMemory、表情、语音、图片、音乐、历史查询、QQ 空间和 QQ 资料能力整合到同一个侧栏应用，并保留上游模块自身的业务实现、命令、工具、页面与数据目录。

整合层负责四件事：

1. 统一十一个模块的加载、重载、冲突检查和资源清理。
2. 用五个稳定入口组织功能，统一状态与配置体验。
3. 在 AstrBot 鉴权下代理模块 API，保护密钥与配置版本冲突。
4. 以经过清单管理的浅绿色主题和轻量导航适配上游页面。

> `0.3.5` 新增有界私聊 draft-window 回复防抖与 Anysearch 联网搜索模块；移除自研静默合并，群聊继续由聊天互动原生防抖协调。万能解析器因官方来源无法核验暂不纳入。

## 界面与导航

| 一级入口 | 二级内容 | 用途 |
| --- | --- | --- |
| **总览** | 运行总览、全局设置 | 待办、状态、队列、模块启停与资源上限 |
| **聊天系统** | 聊天互动、主动问候、历史查询 | 回应范围、问候计划、群记录检索 |
| **记忆成长** | LivingMemory | 长期记忆、知识图谱、召回、人格建议 |
| **表达创作** | 表情互动、语音回复、图片创作、音乐点播 | 图库、TTS、生图改图、音乐发送 |
| **QQ 社交** | QQ 动态、QQ 资料 | 空间动态、状态、签名、昵称与头像 |

界面统一采用：

- 浅绿背景 `#F5F8F4`、侧栏 `#EEF5EC`、白色内容区。
- 深绿主操作 `#2F6B4F`、正文 `#24382C`、次文字 `#617367`。
- 模块切换不改变整页品牌色，不堆叠大面积渐变与装饰网格。
- 桌面内导航约 196 px；AstrBot 可用宽度不足时切换顶部导航。
- 记忆成长内页使用 52 px 紧凑业务页签，标题 20–24 px，统计横排，图谱/图例/搜索保持正常流。
- 图片创作统一知伴浅绿并跟随宿主明暗；记忆与图片页面均不提供独立外观入口或本地主题缓存。
- 1440、1024、768、390 px 已完成主外壳、记忆成长与图片创作的视觉和横向溢出回归；其余工作台完成登录态进入与配置检查。
- 不支持或用户选择减少动态效果时，跨文档过渡自动关闭。

## 十一个运行模块

| 模块 | 主要能力 | 页面 / 运行方式 |
| --- | --- | --- |
| 聊天互动（2.2.13） | 群聊接话、唤醒、上下文、私聊处理 | 天使之心页面 |
| 联网搜索（v0.3） | Anysearch 实时搜索、公开网页正文提取 | 有界联网页面、命令与可选 LLM 工具 |
| 记忆成长（2.8.2） | LivingMemory 长期记忆、知识图谱、人格审批 | LivingMemory 页面与知伴审批库 |
| 表情互动（5.3.5） | 服务器图库、分类、发送、语义检索 | 表情包管理页面 |
| 语音回复（1.3.1） | BreezeBlue TTS、音色、语速、概率 | 语音设置页面 |
| 主动问候（v1.3.0-beta.1） | 私聊主动消息与后台调度 | AstrBot 事件和计划任务 |
| 图片创作（0.2.2） | 文生图、改图、供应商配置 | 图片创作页面 |
| 音乐点播（0.1.3） | Bilibili 搜索、下载、音频发送 | 音乐账号页面 |
| 历史查询（1.0.10） | 群记录检索、分页适配 | 命令、事件与 LLM 工具 |
| QQ 动态（0.9.0） | 空间浏览、发布、评论、点赞 | QQ 空间 Ultra 页面 |
| QQ 资料（v1.1.6） | 状态、签名、昵称、头像 | 管理员命令、工具与配置页 |

上游命令、处理器、LLM 工具和数据目录继续使用原名称。知伴只开放当前模块的 API 代理，不允许子页面跨模块访问其他模块接口。

LivingMemory 是唯一长期记忆模块。AngelMemory 和内容/链接过滤不参与运行，也不进入发布包。

## 兼容范围

| 维度 | 要求 |
| --- | --- |
| AstrBot | `>=4.29.3,<4.30` |
| 消息协议 | OneBot v11，通过 AstrBot `aiocqhttp` 适配器 |
| 操作系统 | Windows、Linux；依赖因媒体与社交模块而异 |
| Python | 3.12（当前验证环境） |
| 页面访问 | AstrBot Dashboard 登录态、官方插件页面桥接 |
| QQ 动态（0.9.0） | OneBot 能力 + 有效 QQ 空间 Cookie |
| 音乐点播（0.1.3） | Bilibili 可访问性 + FFmpeg + 平台音频发送能力 |
| 语音/图片 | 对应 TTS/图片服务与凭据 |

知伴不是独立 OneBot 服务，也不替代 AstrBot、QQ 协议端或外部模型服务。

## 安装与切换

### 安装

1. 备份知伴插件目录、`data/config/astrbot_plugin_zhiban_config.json` 和相关 `data/plugin_data/`。
2. 将 `astrbot_plugin_zhiban` 放入 AstrBot 插件目录。
3. 停用独立同源业务插件，避免处理器、LLM 工具或后台任务重复注册。
4. 启用知伴并重载 AstrBot。
5. 打开 `扩展功能 → 知伴`。
6. 在 `总览 → 全局设置` 检查十一个模块，再按功能页配置外部服务。
7. 发送 `/知伴 菜单` 和 `/知伴 状态` 验证运行。

### 回退

停用知伴，恢复旧插件目录，再重新启用原插件。模块数据目录在切换期间保持原位置；不要在知伴仍运行时让同名旧插件同时写入相同数据。

### 升级

升级前备份插件与配置。替换文件、核对依赖，然后重载并检查模块状态。应用失败时不会把“保存成功”误报成“已生效”；恢复旧插件目录和配置后重新启动。

## 状态模型

知伴严格区分：

- **启用**：配置中的模块开关。
- **运行**：AstrBot 已加载模块实例、处理器、工具或页面。
- **业务就绪**：完成外部能力和配置检查。
- **未检测**：接口无法判断时显示未知，不写虚构数值。

例如：QQ 动态模块已加载但没有空间 Cookie 时，显示“运行中 · 业务未就绪”，不允许把“可发布”伪装成“已就绪”。

## 配置与数据安全

- 基础字段优先展开，配置表单支持搜索、单位和范围提示。
- 状态包含“未保存”“已保存，待应用”“已生效”“应用失败”。
- 操作为“仅保存”“保存并应用”“撤销未保存更改”。
- 保存使用配置版本校验；版本冲突不覆盖当前编辑。
- 密钥字段只返回是否配置，不返回原值。
- 留空保持原密钥，清除必须显式选择并保存。
- 草稿中的敏感信息不写入浏览器存储。
- 模块启停和跨模块资源预算只在全局设置编辑；聊天行为（回复防抖）放在“聊天系统 → 聊天互动 → 配置”，业务参数保留在各自页面。

数据目录：

| 数据 | 位置 / 原则 |
| --- | --- |
| 知伴配置 | AstrBot 插件配置系统 |
| LivingMemory | 原 `data/plugin_data/astrbot_plugin_livingmemory/` |
| 各业务模块 | 保留原插件数据目录 |
| 人格审批 | `data/plugin_data/astrbot_plugin_zhiban/memory/persona.sqlite3` |
| 密钥与供应商 | 不进入源码、发布 ZIP 或测试夹具 |
| 用户画像、聊天与记忆 | 不进入 Git，不随发布包分发 |

旧配置只在未配置时只读导入。已有知伴配置优先，不会在升级时被旧设置覆盖。

## 页面与低占用设计

AstrBot 4.29.3 的插件页面使用 `allow-scripts allow-forms allow-downloads` sandbox；内层文档 origin 为 `null`。知伴由登录态父页读取签名模块 HTML，再以保留签名资源基址的 `srcdoc` 内容面板载入，避免直接嵌套受 `X-Frame-Options` / `frame-ancestors` 限制的签名响应。

当前策略：

- 五个入口和模块侧栏只在知伴外壳中维护一份。
- 同一入口重复点击不重建，快速切换会中止旧页面请求并忽略旧 ready 事件。
- 当前模块通过签名 HTML + `srcdoc` 内容面板载入；首帧主题和 adapter 位于业务脚本之前。
- 顶层模块请求由受限 host broker 转发；真实桥接 ready 事件控制加载层，超时会显示可操作错误态。
- 宿主只接受已注册 frame 的 source 与 `null`/同源 envelope，再以受 source 校验保护的 `postMessage("*")` 返回响应。
- 可见状态页每 5 秒更新；隐藏页面、配置页和全局设置页停止知伴轮询。
- 状态快照最多复用 5 秒，只含模块状态、菜单顺序和调度摘要。
- 不增加框架、网络字体或重型动画依赖。

该设计兼顾切换反馈与低占用，但没有宣称上游模块内部没有自己的刷新任务。第三方页面的独立轮询需按模块源码分别验收。

## 资源与性能边界

- 验收关注重复点击、快速切换、页面往返、隐藏页暂停轮询与旧 frame 清理。
- 主进程工作集包含 AstrBot 宿主和已启用模块，不作为插件增量指标。
- 活动 frame 与监听的长期回收仍需在目标环境重复压测。
- Linux、SnowLuma、完整 OneBot 收发与目标部署资源上限仍需在目标环境验收。

## 命令

- `/知伴 菜单`：显示按预设使用频率排列的模块菜单。
- `/知伴 状态`：显示调度器、模块生命周期和错误状态。
- `/知伴 人格建议`：列出当前会话待审批建议。
- `/知伴 批准 编号`、`/知伴 拒绝 编号`：管理员审批。
- `/知伴 回滚`：恢复当前会话上一人格版本。

各上游模块原有命令与 LLM 工具继续可用。

## 质量与验证

知伴 0.3.5 的验证范围：

- **Python**：2,955 项测试通过（根测试 186 + 图片模块 12 + 表情模块 1,542 + 记忆模块 1,187 + 联网搜索模块 28），7 项跳过，另有 127 个子测试通过（根 34 + 表情 93）。
- **Node**：139 项测试通过（根桥接/前端 45 + 表情前端 94）。
- **构建**：资源清单、ZIP 和 SHA-256 校验流程可用；具体文件数以构建产物为准。
- **统计口径**：知伴 Token 仅计知伴可识别的 Provider 最终响应；AstrBot 全局 Token 来自只读 `provider_stats`，包含非知伴调用，两者不混算；缺 usage 显示“未统计/暂无”，不伪报 0。
- **页面**：登录态下检查五入口、总览、全局设置、十一个模块入口和配置页。
- **响应式**：1440/1024/768/390 px 的主外壳、记忆成长与图片创作通过；模块配置页在登录态下可打开。
- **竞态**：快速并发切换停留在最后目标，没有旧页面覆盖。
- **主题**：主应用浅色/深色切换即时传递到记忆成长和图片创作；两页均无独立外观入口或旧本地缓存。
- **切换**：20 次一级入口往返后仅保留 1 个工作台 frame，无串页；浏览器 HTML 缓存按 LRU/字节上限验收，不作 JS heap 或 RSS 等量证明。
- **同负载观测**：本机旧/新安装态各 20 轮一级切换约 20.0s / 19.8s；宿主重启后的 Private/WorkingSet 为约 3.157/0.571 GB 与 3.193/0.608 GB，未证明进程 RSS 降低。浏览器顶层 Performance 指标受宿主 frame 边界限制，不能代表 iframe 内部 JS heap。
- **加载体验**：同一模块路由复用已就绪 frame；模块 HTML 使用 30 秒内、最多 6 条且估算不超过 2 MiB（单条 512 KiB）的浏览器内存缓存；UTF-8 字节为估算，不等同 JS heap。过期项由低频维护清理，进入分组后仅串行预取可见分组的受认证 HTML，最多 1 个请求在途，离开页面/分组或节省流量时取消；父加载条在 iframe 插入后移除，刷新/应用/失败会失效。
- **回复防抖**：采用 `reply_merge` 1.4.2 的 draft-window 机制替换此前自研静默合并。当前仅接管私聊，群聊继续由聊天互动（AngelHeart）唯一负责，避免双层防抖。每窗口默认最多 4 轮草稿调用、8 条补充、16 KiB 文本和 30 秒；无标记/超时退回等待，不丢弃正常最终回复。草稿只用于专用控制标记判断与最终提示词注入，不写入长期记忆或作为聊天内容展示；流式回复已经发出的片段无法撤回。草稿调用会产生额外 Provider 费用，并与最终回复分别计量。
- **资源预算**：聊天、媒体、后台维护默认各 1 个并发，媒体与后台共享重资源预算；模块启动/清理、TTS 合成、图片生成/编辑、音乐交付、QQ 空间 daemon 启停已接入。记忆衰减/整合/备份、FAISS 实际写盘、索引重建，以及表情描述、向量生成、语义检索和自动收集重建只在真实重任务区间取维护票；空闲等待、防抖窗口和轻量轮询不持票。其他模块的非重轮询和未被识别为资源密集的定时任务仍按上游实现运行，不宣称全部后台任务已纳入。 Anysearch 搜索/正文提取默认并发 2、请求超时 20 秒、单响应 1 MiB、文本缓存 120 秒且最多 64 条/2 MiB；缺 API Key 显示未配置且不发起请求。
- **安全**：密钥脱敏、版本冲突、显式清除、保存/应用状态均有回归。
- **未执行**：真实 QQ 空间发布、真实联系人消息、付费图片/语音生成、真实资料修改。

### 本机登录态验收矩阵

| 范围 | 本次结果 |
| --- | --- |
| 总览、五个一级入口、全局设置 | 通过；导航选中与标题即时更新 |
| 聊天互动、记忆成长、表情互动、语音回复、图片创作、音乐点播、QQ 动态 | 七个工作台均完成页面读取、桥接握手、业务界面挂载 |
| 记忆成长 | 页面可打开；未配置语言模型 Provider 时显示“业务未就绪”和具体 Provider 名称，不伪报图谱数据 |
| 表情互动 | 表情管理、资源广场、语义化、设置中心均可达；设置深链与 9 个一级标签逐项通过；未配置视觉/向量模型时按钮禁用并说明原因 |
| 图片创作 | 通过；无供应商时显示空态与新增入口，不把未配置误报为加载失败 |
| 语音回复 / 音乐点播 | 页面可打开；未配置 API Key / Bilibili 登录 / FFmpeg 时显示对应限制 |
| QQ 动态 | 通过；Cookie 失效时显示“业务未就绪”，工作台与配置入口仍可用 |
| 模块配置 | 七个模块配置页均可打开；敏感值不回显 |
| 设置深链刷新 | 通过；刷新后保持 `meme/settings#config-group-semantic-models`，关闭弹窗后不被旧 hash 重新打开 |
| 快速切换 | 连续切换后停留在最后目标，只保留一个工作台 frame |
| 未配置/未测试 | 图片供应商、语音 API Key、Bilibili 登录、QQ 空间 Cookie、记忆语言模型 Provider 未配置；真实发布、付费生成、真实资料修改和 Linux 部署未执行 |

## AI 辅助开发

本项目开发使用了 AI 编程助手，主要模型及大致作用如下：

- **GPT-6 Astra**：用于跨模块架构梳理、复杂调用链与生命周期/资源预算审阅，以及导航、统计和安装态问题的诊断与验收方案。
- **DeepSeek V4.1 Flash**：用于回复防抖、Anysearch 联网搜索、缓存与调度等代码实现，并执行定向/全量测试、构建、安装同步和实机页面复验。

模型名称仅说明开发过程；AstrBot 运行时使用部署者自行配置的 Provider，与上述开发工具相互独立。AI 输出经过测试、构建和项目所有者审查，但不构成生产环境的保证。

## 开发模式

开发模式为“保留上游业务，在知伴宿主内适配生命周期、配置、状态和界面”，不重写业务逻辑，也不把不同模块的数据库强行合并。

| 文件 | 职责 |
| --- | --- |
| `main.py` | 插件入口、Web API、全局设置、聊天准入与业务就绪 |
| `runtime.py` | 模块加载、重载、冲突检测、处理器/工具清理 |
| `catalog.py` | 十模块与五个一级入口的元数据 |
| `settings_service.py` | 配置版本、校验、密钥脱敏与保存 |
| `scheduling.py` | 队列、超时和媒体串行 |
| `memory_control.py` | 人格建议审批 |
| `views/知伴/app.js` | 五入口外壳、总览、全局设置和配置表单 |
| `views/知伴/module_bridge.js` | 上游页面侧栏、主题、API 代理和页面适配 |
| `ui_assets.py` | 页面资源路径安全与 HTML 桥接注入 |
| `build_views.py` | 生成页面资源、注入受控桥接、写入适配清单 |
| `package_release.py` | 发布 ZIP、AST 检查、逐文件哈希 |

资源审计规则：未适配的非 HTML 上游资源必须逐字节一致；所有 `index.html` 适配统一由构建函数注入；主题覆盖位于 `module_bridge.js` 的明确范围。`.zhiban_generated_assets.json` 记录生成文件、SDK/桥接注入和跨文档过渡适配，并随发布包提供。

### 本地命令

~~~~powershell
python build_schema.py
python build_views.py
python -m pytest tests -q
node --test tests/*.mjs
python package_release.py
~~~~

运行行为、配置或接口发生变化时递增 `metadata.yaml` 版本，并补齐测试、构建和安装副本校验。部署前应检查目标实例的配置、数据目录与备份策略。

## 来源许可与移植边界

### 直接整合模块

以下项目是知伴内的实际业务实现。版本、名称和上游地址以各模块 `metadata.yaml` 为准，许可见模块随附文件。

| 模块（快照版本） | 参考项目 | 整合内容 | 许可 |
| --- | --- | --- | --- |
| 聊天互动（2.2.13） | [kawayiYokami/astrbot_plugin_angel_heart](https://github.com/kawayiYokami/astrbot_plugin_angel_heart) | 天使之心聊天流程和页面 | AGPL v3 |
| 记忆成长（2.8.2） | [lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) | LivingMemory 页面、长期记忆和检索 | AGPL v3 |
| 联网搜索（v0.3） | [AgIzT/astrbot_plugin_anysearch](https://github.com/AgIzT/astrbot_plugin_anysearch) | 实时搜索、公开网页正文提取与有界联网工具 | MIT |
| 回复防抖（1.4.2） | [Ye1xiaotian/astrbot_plugin_reply_merge](https://github.com/Ye1xiaotian/astrbot_plugin_reply_merge) | 私聊 draft-window 防抖与最终提示词注入 | MIT |
| 表情互动（5.3.5） | [anka-afk/astrbot_plugin_meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) | 图库、语义检索和发送 | MIT |
| 语音回复（1.3.1） | [hangdingding/AstrBot-breezetts](https://github.com/hangdingding/AstrBot-breezetts) | BreezeBlue TTS | 未发现 LICENSE，待核实 |
| 主动问候（v1.3.0-beta.1） | [Pancakes-Labs/astrbot_plugin_proactive_chat](https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat) | 私聊问候与持久化任务 | AGPL v3 |
| 图片创作（0.2.2） | [kawayiYokami/astrbot_plugin_angel_brush](https://github.com/kawayiYokami/astrbot_plugin_angel_brush) | 生图、改图与图片页面 | 未发现 LICENSE，待核实 |
| 音乐点播（0.1.3） | [57Darling02/astrbot_plugin_listen_music](https://github.com/57Darling02/astrbot_plugin_listen_music) | Bilibili 搜索和音频发送 | 未发现 LICENSE，待核实 |
| 历史查询（1.0.10） | [kawayiYokami/astrbot_plugin_angel_eye](https://github.com/kawayiYokami/astrbot_plugin_angel_eye) | 群聊记录工具 | LICENSE 与 README 冲突，待核实 |
| QQ 动态（0.9.0） | [diaomin66/astrbot_plugin_qzone_ultra](https://github.com/diaomin66/astrbot_plugin_qzone_ultra) | 空间页面、发布与守护进程 | MIT；随包字体许可待核实 |
| QQ 资料（v1.1.6） | [Zhalslar/astrbot_plugin_qqprofile](https://github.com/Zhalslar/astrbot_plugin_qqprofile) | 状态、签名、昵称和头像 | AGPL v3 |

### 架构与体验参考

- [AstrBot](https://github.com/AstrBotDevs/AstrBot)：宿主生命周期、鉴权、插件页面与桥接模式。
- 上述业务项目的原有功能结构、页面语义和业务工作流；知伴不宣称原创它们。
- 五个一级入口、统一状态、配置安全、浅绿色设计系统、受控主题适配与页面切换属于知伴整合层。

本仓库已公开，但其中整合了多个上游项目，许可证状态包含 AGPL v3、MIT、缺失与待澄清项。使用、再分发或商业部署前，请按各模块 `metadata.yaml` 与随附许可证逐项核实；公开可见不等于额外授权。本说明不是法律意见。

## 项目结构

~~~~text
astrbot_plugin_zhiban/
  main.py                 插件入口、全局设置与业务就绪
  runtime.py              十模块生命周期和资源清理
  catalog.py              五入口和十模块元数据
  settings_service.py     配置版本与密钥安全
  scheduling.py           聊天队列和媒体串行
  memory_control.py       人格建议审批
  views/知伴/             侧栏应用、配置和桥接
  modules/                十一个运行模块、资源和许可证
  _conf_schema.json       配置 schema
  metadata.yaml           版本、平台与宿主兼容范围
tests/                    生命周期、配置、桥接、资源和状态回归
build_schema.py           汇总 schema
build_views.py            生成页面与适配清单
package_release.py        ZIP、哈希与发布文件清单
~~~~


> **万能解析器状态**：原候选 `Zhalslar/astrbot_plugin_parser` 与账号当前均返回 404；GitHub 搜索只出现无法确认归属的第三方同名仓库，因此本版本未安装或部署解析器，也未从教程或陌生镜像执行脚本。待可信上游地址、维护归属和许可证明确后再单独验收。
