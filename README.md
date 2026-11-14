<!-- markdownlint-disable MD033 MD041 -->
<div align="center">

<img src="astrbot_plugin_zhiban/logo.png" alt="知伴 Logo" width="112">

# 知伴

**把分散的 AstrBot QQ 机器人能力，整理成一个真正可用的中文应用。**

[![Version](https://img.shields.io/badge/version-0.3.1-2f6b4f?style=flat-square)](astrbot_plugin_zhiban/metadata.yaml)
[![AstrBot](https://img.shields.io/badge/AstrBot-4.29.x-4f8f6c?style=flat-square)](astrbot_plugin_zhiban/metadata.yaml)
[![OneBot](https://img.shields.io/badge/OneBot-v11-5b7f66?style=flat-square)](#兼容矩阵)
[![Python](https://img.shields.io/badge/Python-3.12-3f7560?style=flat-square)](#本地开发)
[![Tests](https://img.shields.io/badge/tests-97%20Python%20%2B%2017%20Node-2f6b4f?style=flat-square)](#质量与验证)
[![License](https://img.shields.io/badge/license-mixed%20%2F%20review%20required-8c5917?style=flat-square)](astrbot_plugin_zhiban/README.md#来源许可与移植边界)

[快速开始](#快速开始) · [功能模块](#十个运行模块) · [界面](#界面) · [安装](astrbot_plugin_zhiban/README.md#安装与切换) · [完整文档](astrbot_plugin_zhiban/README.md)

</div>

> **知伴**是运行于 AstrBot 的整合应用，面向 OneBot v11（`aiocqhttp`）QQ 机器人。它把聊天、长期记忆、表情、语音、图片、音乐、历史检索、QQ 空间和 QQ 资料整理成同一个侧栏入口，同时保留各上游模块的业务实现、命令、工具与数据目录。

## 为什么是知伴

维护多套机器人插件时，常见问题不是“功能少”，而是入口分散、开关重复、状态含糊、密钥危险、页面风格割裂和资源边界失控。知伴在不重写上游业务逻辑的前提下，把这些问题统一到一层轻量宿主中：

| 问题 | 知伴的处理 |
| --- | --- |
| 功能分散在十个插件 | 五个一级入口、十个内部模块、一个侧栏应用 |
| “开着”不代表“能用” | 启用、运行、业务就绪三层状态 |
| 配置入口与宿主设置重复 | 总览集中启停与调度，各模块保留业务配置 |
| 密钥可能回显或误覆盖 | 脱敏、版本冲突检测、显式清除、保存后应用 |
| 页面风格不一致 | 浅绿色品牌主题与受控上游样式适配 |
| 每次切换都整页重载 | 路由去重、轻量过渡、短时状态缓存与竞态保护 |
| 十个工作台同时常驻 | 只加载当前页面，保留低占用边界 |

## 界面

<div align="center">

<img src="astrbot_plugin_zhiban/logo.png" alt="知伴界面标识" width="76">

**总览 · 聊天系统 · 记忆成长 · 表达创作 · QQ 社交**

</div>

五个一级入口固定不随模块变色。`总览` 包含 `运行总览` 与 `全局设置`；全局设置管理模块开关、队列和资源上限，业务参数仍在对应功能页编辑。

- 桌面左栏导航；窄屏自动切换为顶部导航。
- 白色内容区、浅绿背景、深绿主操作，固定品牌语义。
- 1024、768、390 像素响应式布局已验收。
- 浏览器支持跨文档过渡时使用约 120–160 ms 的浅淡过渡；`prefers-reduced-motion` 下自动关闭。
- 页面切换先给出即时忙碌反馈，不靠长动画掩盖等待。

## 五个一级入口

| 入口 | 模块 | 主要用途 |
| --- | --- | --- |
| **总览** | 运行总览、全局设置 | 待办、状态、队列、模块启停与资源设置 |
| **聊天系统** | 聊天互动、主动问候、历史查询 | 回应、问候计划和群记录检索 |
| **记忆成长** | LivingMemory | 长期记忆、知识图谱、召回与人格审批 |
| **表达创作** | 表情互动、语音回复、图片创作、音乐点播 | 图库、TTS、生图改图与音乐发送 |
| **QQ 社交** | QQ 动态、QQ 资料 | 空间动态、状态、签名、昵称与头像 |

## 十个运行模块

| 模块 | 能力 | 业务页面 / 运行形态 |
| --- | --- | --- |
| **聊天互动** | 群聊接话、唤醒、上下文、私聊处理 | 天使之心页面 |
| **记忆成长** | 长期记忆、检索、知识图谱、人格建议 | LivingMemory 页面与知伴审批库 |
| **表情互动** | 图库、分类、发送与语义检索 | 表情包管理页面 |
| **语音回复** | BreezeBlue TTS、音色、语速、概率 | 语音设置页面 |
| **主动问候** | 私聊主动消息与后台调度 | AstrBot 事件与计划任务 |
| **图片创作** | 文生图、改图与供应商配置 | 天使画笔页面 |
| **音乐点播** | Bilibili 搜索、下载与音频发送 | 音乐账号页面 |
| **历史查询** | 群记录检索与分页适配 | 命令、事件与 LLM 工具 |
| **QQ 动态** | 空间浏览、发布、评论、点赞 | QQ 空间 Ultra 页面 |
| **QQ 资料** | 管理员更新状态、签名、昵称、头像 | 命令、工具与配置页 |

内容过滤与旧链接过滤不再注册或进入发布包。LivingMemory 是唯一长期记忆模块；AngelMemory 不参与运行。

## 快速开始

### 环境要求

- AstrBot `>=4.29.3,<4.30`
- Python 3.12
- OneBot v11，通过 AstrBot `aiocqhttp` 平台适配器接入
- Windows 或 Linux；具体依赖取决于启用的媒体与社交模块
- 启用音乐点播时需 FFmpeg；启用 TTS、图片或空间模块时需对应外部服务凭据

### 安装

1. 备份 AstrBot、知伴配置和 `data/plugin_data/`。
2. 将 `astrbot_plugin_zhiban` 放入 AstrBot 插件目录。
3. 停用与知伴同名的独立上游插件，避免重复处理器、工具和后台任务。
4. 启用知伴并重载 AstrBot。
5. 打开 AstrBot 侧栏 `扩展功能 → 知伴`，从 `总览 → 全局设置` 检查十个模块。
6. 发送 `/知伴 菜单` 与 `/知伴 状态` 验证命令与管理入口。

详细迁移、回退、配置和数据边界见 **[完整插件文档](astrbot_plugin_zhiban/README.md)**。

## 兼容矩阵

| 项目 | 支持范围 |
| --- | --- |
| 宿主 | AstrBot 4.29.3（当前锁定兼容 4.29.x） |
| 消息协议 | OneBot v11；不是独立 OneBot 服务 |
| QQ 桥接 | AstrBot `aiocqhttp` 适配器；SnowLuma 等协议端仍需分别验证 |
| 操作系统 | Windows、Linux，前提是 Python/媒体/协议端依赖满足 |
| 界面 | 浅色默认、深色兼容、减少动态效果偏好 |
| 部署 | Dashboard 登录态与插件页桥接；失败时明确显示未授权或未就绪 |

## 状态与安全

知伴不把“进程加载”冒充“业务可用”：

- **启用**：配置文件中的模块开关。
- **运行**：AstrBot 已加载处理器、工具或页面实例。
- **业务就绪**：该模块完成真实前置检查。例如 QQ 空间缺少 Cookie 时显示“业务未就绪”。
- **未检测**：接口或外部依赖暂时无法判断，不填充虚构值。

配置保存采用版本校验，密钥只返回“已配置/未配置”，草稿不会把敏感值写入浏览器存储。配置冲突、保存待应用和应用失败都有独立反馈。

临时状态缓存最多保留 **5 秒**，仅包含模块启用/运行/业务状态、菜单顺序和调度摘要，不缓存密钥、配置正文或用户业务数据；配置与运行状态以新的接口结果覆盖旧结果。

## 低占用与切换体验

- 只加载当前工作台，不常驻十个模块页面。
- 离开页面释放知伴引用；上游独立轮询按各自实现运行。
- 同一入口重复点击不重新导航；同时发起的快速跳转由最后目标决定。
- 当前页面隐藏时停止知伴状态轮询。
- 不引入 React/Vue 等新框架，不增加网络字体或重型转场依赖。

当前实测（AstrBot 4.29.3，Windows）：

| 场景 | 结果 |
| --- | --- |
| 当前入口重复点击 | 页面不重建，业务请求 0 |
| 全局设置接口 | 约 26 ms |
| 模块间重复切换 20 次 | 平均约 1.44 秒，范围约 0.85–1.79 秒 |
| 页面往返后的 DOM | 文档数保持 3，节点数保持 899 |
| AstrBot 主进程空闲工作集 | 约 367 MiB（包含宿主与十个模块，不是插件增量） |

活动 frame 与监听数仍会随访问过的不同模块变化，长期回收尚需更深入的 session 级验证；Linux 与完整 OneBot 全栈也未完成端到端资源验收。

## 质量与验证

- **Python**：97 项测试通过，另有 18 个子测试通过。
- **Node**：17 项测试通过。
- **真实页面**：五入口、总览、全局设置、配置页、10 个模块入口和 1024/768/390 像素布局已检查。
- **配置安全**：并发冲突、密钥脱敏、显式清除、保存/应用、无修改反馈均有回归。
- **竞态**：快速并发跳转最终停留在最后目标，旧页面结果不覆盖新页面。
- **构建**：830 个发布文件、79 个生成页面资源；资源清单、ZIP、安装副本和 SHA-256 对照通过。

发布包：[`dist/zhiban-0.3.1.zip`](dist/zhiban-0.3.1.zip)

SHA-256：`a91d8dfb477311edb8fbd8c65b218ae6eb92dd714e3d2299be24e49ca1bda0d6`

## 开发模型

AI 开发记录如实区分“辅助编码模型”和“曾参与方案/审查的模型”：

| 阶段 | 模型 | 用途 |
| --- | --- | --- |
| 架构整合、代码实现、测试与发布 | **GPT-6 Astra** | 本仓库主要 AI 辅助开发模型 |
| 页面切换方案检查与优化审查 | **DeepSeek V4.1 Flash** | 导航卡顿方案、问题拆解与改进审查 |

模型记录用于说明开发过程，不代表插件运行时必须调用这些模型。机器人对话、记忆、嵌入、重排序、图片、语音与判断使用的是部署者在 AstrBot 中配置的提供商。

## 参考项目与移植边界

### 直接整合的业务项目

以下项目通过服务器快照整合为知伴内部模块，业务能力、名称、版本和上游来源以各模块 `metadata.yaml` 及随附许可证为准。

| 知伴模块（快照版本） | 参考 / 上游项目 | 保留内容 | 许可证状态 |
| --- | --- | --- | --- |
| 聊天互动（2.2.13） | [kawayiYokami/astrbot_plugin_angel_heart](https://github.com/kawayiYokami/astrbot_plugin_angel_heart) | 天使之心聊天流程与页面 | AGPL v3 |
| 记忆成长（2.8.2） | [lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) | 长期记忆、图谱、召回、提示词与数据工具 | AGPL v3 |
| 表情互动（5.3.5） | [anka-afk/astrbot_plugin_meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) | 图库、发送、语义检索与管理页 | MIT |
| 语音回复（1.3.1） | [hangdingding/AstrBot-breezetts](https://github.com/hangdingding/AstrBot-breezetts) | BreezeBlue TTS 页面与调用 | 未发现 LICENSE，待核实 |
| 主动问候（v1.3.0-beta.1） | [Pancakes-Labs/astrbot_plugin_proactive_chat](https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat) | 私聊计划与后台调度 | AGPL v3 |
| 图片创作（0.2.2） | [kawayiYokami/astrbot_plugin_angel_brush](https://github.com/kawayiYokami/astrbot_plugin_angel_brush) | 生图、改图与供应商页面 | 未发现 LICENSE，待核实 |
| 音乐点播（0.1.3） | [57Darling02/astrbot_plugin_listen_music](https://github.com/57Darling02/astrbot_plugin_listen_music) | Bilibili 搜索、音频与账号页 | 未发现 LICENSE，待核实 |
| 历史查询（1.0.10） | [kawayiYokami/astrbot_plugin_angel_eye](https://github.com/kawayiYokami/astrbot_plugin_angel_eye) | 群记录工具与分页适配 | AGPL 文件与 README 冲突，待澄清 |
| QQ 动态（0.9.0） | [diaomin66/astrbot_plugin_qzone_ultra](https://github.com/diaomin66/astrbot_plugin_qzone_ultra) | 空间页面、控制器与本地守护进程 | MIT；字体许可待核实 |
| QQ 资料（v1.1.6） | [Zhalslar/astrbot_plugin_qqprofile](https://github.com/Zhalslar/astrbot_plugin_qqprofile) | 状态、签名、昵称、头像与管理命令 | AGPL v3 |

### 架构与体验参考

- [AstrBot](https://github.com/AstrBotDevs/AstrBot)：插件生命周期、Dashboard 页面、鉴权、页面桥接和平台适配的宿主环境。
- 上述十个业务项目的原有导航、表单密度、模块语义与工作流；知伴在其上统一外层入口，不宣称原创这些业务能力。
- 固定五入口、模块状态模型、配置安全流程、浅绿色设计语言与页面切换实现属于知伴整合层，代码和适配记录在本仓库。

许可证文件是否存在不等于已获公开再分发授权。当前混合许可证、缺失许可证和冲突声明必须在公开分发或商业部署前由项目所有者进一步核实；这不是法律意见。

## 仓库结构

~~~~text
astrbot_plugin_zhiban/
  main.py                  插件入口、Web API、全局设置、聊天准入
  runtime.py               模块生命周期、冲突与资源清理
  catalog.py               十模块和五入口元数据
  settings_service.py      配置版本、校验、密钥脱敏
  scheduling.py            队列、超时与媒体串行
  views/知伴/              侧栏应用、工作台、主题与桥接
  modules/                 十个运行模块的源码、资源和许可
tests/                     配置、生命周期、桥接、资源和调度测试
build_views.py             生成模块资源与适配清单
build_schema.py            汇总配置 schema
package_release.py         ZIP、逐文件清单与 SHA-256
~~~~

## 本地开发

~~~~powershell
python build_schema.py
python build_views.py
python -m pytest tests -q
node --test tests/*.mjs
python package_release.py
~~~~

不要提交 `data/config`、`data/plugin_data`、模型密钥、供应商凭据、用户记忆或生产数据库。上游页面继续保留自身业务逻辑；知伴负责生命周期、配置、状态、导航与经过清单记录的主题适配。

小版本在本地累积完整回归，重大版本验收后统一推送私有 GitHub 仓库，生产部署另行测试。
