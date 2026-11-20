<!-- markdownlint-disable MD033 MD041 -->
<div align="center">

<img src="astrbot_plugin_zhiban/logo.png" alt="知伴 Logo" width="112">

# 知伴

**把分散的 AstrBot QQ 机器人能力，整理成一个真正可用的中文应用。**

[![Version](https://img.shields.io/badge/version-0.3.5-2f6b4f?style=flat-square)](astrbot_plugin_zhiban/metadata.yaml)
[![AstrBot](https://img.shields.io/badge/AstrBot-4.29.x-4f8f6c?style=flat-square)](https://github.com/AstrBotDevs/AstrBot)
[![OneBot](https://img.shields.io/badge/OneBot-v11-5b7f66?style=flat-square)](#兼容矩阵)
[![Python](https://img.shields.io/badge/Python-3.12-3f7560?style=flat-square)](#本地开发)
[![Tests](https://img.shields.io/badge/tests-3434%20Python%20%2B%20141%20Node-2f6b4f?style=flat-square)](#质量与验证)
[![License](https://img.shields.io/badge/license-mixed%20%2F%20review%20required-8c5917?style=flat-square)](astrbot_plugin_zhiban/README.md)

[快速开始](#快速开始) · [功能模块](#十一个运行模块) · [完整文档](astrbot_plugin_zhiban/README.md)

</div>

> **知伴**是运行于 AstrBot 的整合应用，面向 OneBot v11（`aiocqhttp`）QQ 机器人。它把聊天、长期记忆、表情、语音、图片、音乐、历史检索、QQ 空间和 QQ 资料整理成同一个侧栏入口，同时保留各上游模块的业务实现、命令、工具与数据目录。

## 为什么是知伴

维护多套机器人插件时，常见问题不是“功能少”，而是入口分散、开关重复、状态含糊、密钥危险、页面风格割裂和资源边界失控。知伴在不重写上游业务逻辑的前提下，把这些问题统一到一层轻量宿主中：

| 问题 | 知伴的处理 |
| --- | --- |
| 功能分散在十一个插件 | 五个一级入口、十一个内部模块、一个侧栏应用 |
| “开着”不代表“能用” | 启用、运行、业务就绪三层状态 |
| 配置入口与宿主设置重复 | 总览集中启停与调度，各模块保留业务配置 |
| 密钥可能回显或误覆盖 | 脱敏、版本冲突检测、显式清除、保存后应用 |
| 页面风格不一致 | 浅绿色品牌主题与受控上游样式适配 |
| 每次切换都整页重载 | 单一外壳、内容面板切换、短时状态缓存与竞态保护 |
| 十一个工作台同时常驻 | 只加载当前页面，保留低占用边界 |

## 界面

<div align="center">

<img src="astrbot_plugin_zhiban/logo.png" alt="知伴界面标识" width="76">

**总览 · 聊天系统 · 记忆成长 · 表达创作 · QQ 社交**

</div>

五个一级入口固定不随模块变色。`总览` 包含 `运行总览` 与 `全局设置`；全局设置管理模块开关、队列和资源上限，业务参数仍在对应功能页编辑。

- 桌面左栏导航；窄屏自动切换为顶部导航。
- 白色内容区、浅绿背景、深绿主操作，固定品牌语义。
- 记忆成长内页改为 52 px 紧凑业务页签，标题 20–24 px、统计横排，图谱与搜索图例保持正常文档流。
- 图片创作统一知伴浅绿并跟随宿主明暗；记忆与图片页面均不提供独立外观入口或本地主题缓存。
- 1440、1024、768、390 px 已完成主外壳、记忆成长与图片创作的视觉和横向溢出回归；其余工作台完成登录态进入与配置检查。
- 模块正文在知伴内容面板内切换，顶部五入口与侧栏不重绘。
- 模块的浅绿首帧、桥接 adapter 与 SDK 顺序由构建产物控制；状态就绪需由真实 bridge 事件确认，不以定时器代替。

## 五个一级入口

| 入口 | 模块 | 主要用途 |
| --- | --- | --- |
| **总览** | 运行总览、全局设置 | 待办、状态、队列、模块启停与资源设置 |
| **聊天系统** | 聊天互动、联网搜索、主动问候、历史查询 | 回应、实时检索、问候计划和群记录检索 |

| **记忆成长** | LivingMemory | 长期记忆、知识图谱、召回与人格审批 |
| **表达创作** | 表情互动、语音回复、图片创作、音乐点播 | 图库、TTS、生图改图与音乐发送 |
| **QQ 社交** | QQ 动态、QQ 资料 | 空间动态、状态、签名、昵称与头像 |

## 十一个运行模块

| 模块 | 能力 | 业务页面 / 运行形态 |
| --- | --- | --- |
| **聊天互动** | 群聊接话、唤醒、上下文、私聊处理 | 天使之心页面 |
| **联网搜索** | Anysearch 实时搜索、公开网页正文提取与配置状态 | 有界联网页面、命令与可选 LLM 工具 |
| **记忆成长** | 长期记忆、检索、知识图谱、人格建议 | LivingMemory 页面与知伴审批库 |
| **表情互动** | 图库、分类、发送与语义检索 | 表情包管理页面 |
| **语音回复** | BreezeBlue TTS、音色、语速、概率 | 语音设置页面 |
| **主动问候** | 私聊主动消息与后台调度 | AstrBot 事件与计划任务 |
| **图片创作** | 文生图、改图与供应商配置 | 图片创作页面 |
| **音乐点播** | Bilibili 搜索、下载与音频发送 | 音乐账号页面 |
| **历史查询** | 群记录检索与分页适配 | 命令、事件与 LLM 工具 |
| **QQ 动态** | 空间浏览、发布、评论、点赞 | QQ 空间 Ultra 页面 |
| **QQ 资料** | 管理员更新状态、签名、昵称、头像 | 命令、工具与配置页 |

LivingMemory 是唯一长期记忆模块。

## 快速开始

### 环境要求

- AstrBot `>=4.29.3,<4.30`
- Python 3.12
- OneBot v11，通过 AstrBot `aiocqhttp` 平台适配器接入
- Windows 或 Linux；具体依赖取决于启用的媒体与社交模块
- 启用音乐点播时需 FFmpeg；启用 TTS、图片或空间模块时需对应外部服务凭据

### 安装

支持范围：Windows/Linux x86_64、AstrBot `>=4.29.3,<4.30`、Python 3.12。其他平台未验证。

推荐从 GitHub Releases 获取 `zhiban-0.3.5.zip`，将解压结果目录重命名为 `astrbot_plugin_zhiban` 后放入 AstrBot 插件目录。发布包已经包含物化模块页面、hash 桥接和 `.zhiban_generated_assets.json`，无需 npm 或联网下载。

如果从源码安装，先在仓库根目录运行 `python build_views.py`，再运行 `python check_install.py`；预检通过后才复制到插件目录。缺少 `views/知伴/modules/` 或 hash 桥接时不要启用插件，按报错重建视图或改用发布包。

安装时只复制发布项，不覆盖 AstrBot 配置、`data/plugin_data/`、QQ/SnowLuma 数据或密钥。启用知伴并重载 AstrBot 后，从 `总览 → 全局设置` 检查十一个模块。

### 直接整合的业务项目

以下项目作为上游业务实现整合为知伴内部模块，业务能力、名称、版本和上游来源以各模块 `metadata.yaml` 及随附许可证为准。

| 知伴模块（快照版本） | 上游项目 | 保留内容 | 许可证状态 |
| --- | --- | --- | --- |
| 聊天互动（2.2.13） | [kawayiYokami/astrbot_plugin_angel_heart](https://github.com/kawayiYokami/astrbot_plugin_angel_heart) | 天使之心聊天流程与页面 | AGPL v3 |
| 记忆成长（2.8.2） | [lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) | 长期记忆、图谱、召回、提示词与数据工具 | AGPL v3 |
| 联网搜索（v0.3） | [AgIzT/astrbot_plugin_anysearch](https://github.com/AgIzT/astrbot_plugin_anysearch) | Anysearch 搜索、正文提取与有界联网工具 | MIT |
| 回复防抖（1.4.2） | [Ye1xiaotian/astrbot_plugin_reply_merge](https://github.com/Ye1xiaotian/astrbot_plugin_reply_merge) | 有界 draft-window 私聊防抖与最终提示词注入 | MIT |
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
- 上述十一项业务能力的原有导航、表单密度、模块语义与工作流；知伴在其上统一外层入口，不宣称原创这些业务能力。
- 固定五入口、模块状态模型、配置安全流程、浅绿色设计语言与页面切换实现属于知伴整合层，代码和适配记录在本仓库。

本仓库已公开，但其中整合了多个上游项目，许可证状态包含 AGPL v3、MIT、缺失与待澄清项。使用、再分发或商业部署前，请按各模块 `metadata.yaml` 与随附许可证逐项核实；公开可见不等于额外授权。

## 仓库结构

~~~~text
astrbot_plugin_zhiban/
  main.py                  插件入口、Web API、全局设置、聊天准入
  runtime.py               模块生命周期、冲突与资源清理
  catalog.py               十一个模块和五入口元数据
  settings_service.py      配置版本、校验、密钥脱敏
  scheduling.py            队列、超时与媒体串行
  views/知伴/              侧栏应用、工作台、主题与桥接
  modules/                 十一个运行模块的源码、资源和许可
tests/                     配置、生命周期、桥接、资源和调度测试
build_views.py             生成模块资源与适配清单
build_schema.py            汇总配置 schema
package_release.py         ZIP、逐文件清单与 SHA-256
~~~~

## 质量与验证

- **Python**：3,434 项测试通过（根测试 211 + 图片模块 12 + 表情模块 1,542 + 记忆模块 1,187 + 联网搜索模块 28 + QQ 动态模块 454），7 项跳过，另有 127 个子测试通过（根 34 + 表情 93）。
- **Node**：141 项测试通过（根桥接/前端 47 + 表情前端 94）。

## 本地开发

~~~~powershell
python build_schema.py
python build_views.py
python -m pytest tests -q
node --test tests/*.mjs
python package_release.py
~~~~

仓库发布源码、测试、构建脚本与必要静态资源；运行时配置、模型密钥、供应商凭据、用户记忆和生产数据库不属于仓库内容。部署前请单独检查目标实例的数据目录、访问权限与备份策略。

版本号以 `metadata.yaml` 为准。行为、配置或接口变化应同时更新测试、构建产物和安装副本校验；生产部署还需结合目标 AstrBot、平台适配器和数据规模验收。

## AI 辅助开发

- **GPT-6 Astra**：用于跨模块架构梳理、复杂调用链与生命周期/资源预算审阅，以及导航、统计和安装态问题的诊断与验收方案。
- **DeepSeek V4.1 Flash**：用于回复防抖、Anysearch 联网搜索、缓存与调度等代码实现，并执行定向/全量测试、构建、安装同步和实机页面复验。
- **AstrBot 运行时使用部署者自行配置的 Provider，与上述开发工具相互独立**。
