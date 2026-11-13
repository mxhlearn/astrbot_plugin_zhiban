# 知伴

![知伴 Logo](logo.png)

将服务器当前启用的九个 AstrBot 插件与本机 LivingMemory 记忆模块整合为一个中文插件，保留现有业务实现与补丁，统一配置、调度、模块状态和生命周期。

**运行平台：AstrBot；协议支持：OneBot v11（AstrBot 的 `aiocqhttp` 平台适配器）。插件不是 Linux 专用，也不是独立运行的 OneBot 服务；Windows 和 Linux 均可部署，具体取决于 AstrBot 版本及各模块依赖。**

安装后，AstrBot 左侧「扩展功能」中会出现单一「知伴」入口。进入后可选择功能模块，再切换到应用内「配置」视图编辑详细参数、密钥与启用状态，保存后点击「应用更改」重载模块。图片创作与音乐点播沿用上游专用配置页面。AstrBot 的「插件 → 知伴」设置仍用于调度和宿主管理参数。

## 功能菜单

默认按预期使用频率排列，可在 AstrBot 插件设置的「调度与管理 → 菜单排列顺序」调整。顺序是默认值，不是运行时统计。

1. 聊天互动：群聊接话、唤醒和私聊上下文。
2. 记忆成长：长期记忆、知识工具、嵌入、重排序和人格审批。
3. 表情互动：服务器现有图库与发送。
4. 语音回复：BreezeBlue TTS、音色、概率和非流式接口补丁。
5. 主动问候：保留私聊启用、群聊关闭的服务器设置。
6. 图片创作：生图、改图、供应商和图片面板。
7. 音乐点播：Bilibili 搜索、下载和发送。
8. 历史查询：群记录查询，适配 SnowLuma 2.4.2 分页接口。
9. QQ 空间：沿用现有工具和受管理的后台进程。
10. 内容过滤：链接过滤规则。

模块原有命令与 LLM 工具继续可用。

## 目标环境

- 兼容范围：AstrBot `>=4.29.3,<4.30`，OneBot v11 通过 `aiocqhttp` 接入。
- 支持类型：AstrBot 插件，不是独立 OneBot 服务；OneBot v11 由 AstrBot 的 `aiocqhttp` 平台适配器提供。
- 操作系统：不限定 Linux；Windows 是当前本地回归平台，Ubuntu 是目标迁移平台。不同系统需安装对应的 Python/系统依赖。
- 开发回归环境：AstrBot 4.29.3。
- Linux 目标：Ubuntu Server 24.04 amd64、Python 3.12、AstrBot 4.29.4。
- 目标桥接：SnowLuma 2.4.2 Linux x64 Lite、Node.js 24.22.3、OneBot v11 反向 WebSocket。
- Linux QQ 3.2.35 amd64 仍是待联调候选。
- 新部署到 SnowLuma 2.4.2 时，将历史查询设置 history_api_mode 改为 snowluma_v24；原 Windows 服务继续使用导入的旧分页模式。
- 插件包不含 QQ、SnowLuma、AstrBot 或模型凭据。

### 功能依赖

| 模块 | 主要功能 | 额外条件 |
| --- | --- | --- |
| 聊天互动 | 群聊接话、唤醒、上下文 | 配置 AstrBot 对话模型；OneBot v11 群聊事件 |
| 记忆成长 | 长期记忆、知识工具、人格审批 | LivingMemory 使用的模型；嵌入/重排序按需配置，未配置时使用关键词回退 |
| 表情互动 | 本地图库、表情发送 | 现有图库；语义检索需对应索引/模型配置 |
| 语音回复 | 回复转语音、音色与语速 | BreezeBlue 服务凭据；这是 TTS，不提供语音转文字 |
| 主动问候 | 私聊主动消息、定时任务 | AstrBot 模型与调度环境；群聊默认关闭 |
| 图片创作 | 文生图、图生图 | 至少配置一个受支持的图像生成服务 |
| 音乐点播 | 搜索、获取与发送音频 | Bilibili 可访问性、FFmpeg 与平台文件发送能力 |
| 历史查询 | 群聊记录搜索 | OneBot v11 记录来源；不同部署可需配置对应分页适配模式 |
| QQ 空间 | 读取、发布和管理空间内容 | QQ 空间 Cookie、OneBot；部分任务会启动独立子进程 |
| 内容过滤 | 移除回复中的链接 | 无独立模型；随聊天输出路径执行 |

以上是模块的功能与配置条件，不代表所有外部服务均已在每种操作系统上验收。未配置外部服务的模块可以关闭或保留为未就绪状态。

## 安装与切换

1. 备份 AstrBot 主配置、插件配置、数据库及各插件数据目录。
2. 安装 requirements.txt，将本目录放入 data/plugins/astrbot_plugin_zhiban。
3. 在 AstrBot 中停用原来的 angel_heart、angel_memory、angel_eye、angel_brush、breeze_tts、meme_manager、listen_music、proactive_chat、astrbot_plugin_qzone（或 qzone_ultra）、link_filter；若已安装独立的 astrbot_plugin_livingmemory，也先停用它。保留所有原插件目录和数据。
4. 启用「知伴」并重载 AstrBot。首次启动只读导入仍未配置的旧模块设置；已有知伴配置优先。
5. 发送 /知伴 菜单 和 /知伴 状态，检查模块状态与工具注册。
6. 配好模型、嵌入、重排序和生图供应商后，逐项测试功能。
7. 如需回退，停用知伴并重新启用旧插件；原数据目录保持不动。

不要同时启用知伴和同名旧插件。知伴会检测冲突并阻止重复模块加载。

### 升级与回退

升级前备份知伴插件目录、`data/config/astrbot_plugin_zhiban_config.json` 和相关 `data/plugin_data/` 目录。停用知伴后替换插件文件、核对依赖，再启用或重载插件并检查 `/知伴 状态` 与核心功能。升级失败时恢复旧插件目录和配置，再按原切换方式重新启用旧插件。不要在知伴运行时让旧模块同时写入共享数据目录。

## 配置、数据与记忆

- 每个功能菜单的「配置」视图读取生成的 schema 并直接修改知伴配置；敏感值只显示是否已配置，留空保持原值，清除需显式操作；保存使用配置版本校验，冲突时要求重新读取，重载后应用。
- 旧插件 JSON 配置只在知伴首次迁移时导入，不会覆盖已存在的新设置；迁移结果单独记录，保留后续用户主动清空的值。
- 聊天、表情、图片、语音、音乐、主动问候、历史和空间沿用原 plugin_data 目录。
- LivingMemory 复用原有 `data/plugin_data/astrbot_plugin_livingmemory/` 数据目录，不搬动数据库、不重建索引。原 AngelMemory 数据不导入，仍保留在旧目录供回退。独立 LivingMemory 插件必须先停用，避免双实例同时写入。
- 人格审批数据库仍位于 `data/plugin_data/astrbot_plugin_zhiban/memory/persona.sqlite3`，与 LivingMemory 记忆库分开。
- 生图供应商文件与其他私有凭据不进入源码仓库。
- 可在 AstrBot 配置提供商中添加 OpenAI 兼容接口，再选择 BAAI/bge-m3 嵌入与 BAAI/bge-reranker-v2-m3 重排序。账户额度和认证由服务商决定。
- 查询和候选记忆会发送至所配置的云端嵌入／重排序服务。服务失败时退回本地关键词检索，不切换收费模型。
- 长期事实不按固定 180 天删除；相关性衰减只影响召回排序。临时事项可以过期。人格建议仅在管理员批准后生效，并支持回滚。

## 调度与资源

- 聊天同一时间执行 1 条；全局等待最多 20 条、单会话最多 4 条、最长等待 90 秒。
- 记忆提取设置每日上限；媒体重处理默认串行。各旧模块自己的后台任务仍由其原生命周期管理。
- 表情语义索引和自动采集沿用服务器当前的关闭状态。
- 新默认设置关闭主动插件的 Web 管理服务、遥测和通知轮询；聊天主动问候仍沿用私聊开启、群聊关闭的旧设置。
- QQ 空间可能启动独立 Python 进程；一个插件包不代表单进程或零内存增量。调度器不限制其他第三方插件独立发出的模型请求。

## 命令

- /知伴 菜单：显示按使用频率预设的模块菜单。
- /知伴 状态：显示模块、队列和错误状态。
- /知伴 人格建议：列出当前会话待审批建议。
- /知伴 批准 编号、/知伴 拒绝 编号：管理员审批建议。
- /知伴 回滚：恢复当前会话上一人格版本。

人格审批使用 AstrBot event.is_admin() 验权。其他模块命令与工具继续采用原名称。

## 验证状态

- 本地回归：2026-11-13 Python 测试 91 项通过，Node 前端/桥接测试 12 项通过；覆盖 AstrBot 注册表绑定与重载、配置保存与密钥脱敏、首次配置迁移、页面资源和 API 桥接、上游页面资源一致性、队列、记忆隔离、人格权限和媒体限制。完整运行命令见下方。
- 所有 Python 文件通过 AST 解析；源码扫描未发现密钥或令牌。
- Windows 本机 AstrBot 4.29.3：发布包已同步并启动，WebUI 监听 127.0.0.1:6185；8 个独立第三方插件保持停用，知伴主插件与 LivingMemory 初始化成功，Qzone 工具已注册。Qzone 自动绑定未从 OneBot 获得可用 Cookie，空间读写需先手动绑定；页面视觉与“配置 → 保存 → 应用”的交互仍待人工检查。OneBot 实际收发与远端 Linux 环境仍需分别验收。
- Ubuntu、SnowLuma、Linux QQ 与 2 GB 全栈尚未端到端验证。
- 60 MiB 插件增量和 2 GB 可用性均为工程目标，不是实测结论。
- 不承诺 QQ 账号零风控或零封禁风险。

## 来源与许可

知伴包含九个服务器非记忆模块与 LivingMemory，共十个运行模块；旧 AngelMemory 源码仍在仓库中供回退参考，但不注册、不进入发布 ZIP。各模块保留在独立目录，尽量保留元数据、版权声明、许可证和必要资源。上游地址来自模块 `metadata.yaml`，不是已核实的精确来源提交；`upstream/source-manifest.json` 记录旧服务器快照文件校验值，不含上游 commit。

| 模块（快照版本） | metadata.yaml 中记录的上游 | 随附许可与注意事项 |
| --- | --- | --- |
| 天使之心（2.2.13） | `kawayiYokami/astrbot_plugin_angel_heart` | AGPL v3，见模块 `LICENSE` |
| LivingMemory（2.8.2） | `lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory` | AGPL v3，见 `LICENSE`；前端依赖另有许可文件 |
| 表情包管理器（5.3.5） | `anka-afk/astrbot_plugin_meme_manager` | MIT，见模块 `LICENSE` |
| Breeze TTS（1.3.1） | `hangdingding/AstrBot-breezetts` | 未发现 LICENSE/COPYING/NOTICE；授权待核实 |
| 主动消息（v1.3.0-beta.1） | `Pancakes-Labs/astrbot_plugin_proactive_chat` | AGPL v3，见模块 `LICENSE` |
| 天使画笔（0.2.2） | `kawayiYokami/astrbot_plugin_angel_brush` | 未发现 LICENSE/COPYING/NOTICE；授权待核实 |
| 我想听歌（0.1.3） | `57Darling02/astrbot_plugin_listen_music` | 未发现 LICENSE/COPYING/NOTICE；授权待核实 |
| 天使之眼（1.0.10） | `kawayiYokami/astrbot_plugin_angel_eye` | LICENSE 为 AGPL v3，但原 README 写 GPL-3.0；许可说明冲突，待上游澄清 |
| QQ 空间 Ultra（0.9.0） | `diaomin66/astrbot_plugin_qzone_ultra` | MIT，见模块 `LICENSE`；随包普惠体字体没有许可文本 |
| 链接过滤（1.0.0） | metadata 为 `https://example.local/link_filter` | repo 是占位地址；未发现 LICENSE/COPYING/NOTICE，来源和授权均待核实 |
| AngelMemory（2.0.4，旧源码） | `kawayiYokami/astrbot_plugin_angel_memory` | GPL v3，见模块 `LICENSE`；不进入运行模块与发布 ZIP |

许可证文件未随附不等于获得授权，“私有部署与测试”也不能替代授权。当前 ZIP 仅用于项目所有者本地验证和既有服务器部署；打包成功不构成公开再分发许可，也不代表不同 AGPL/GPL 模块和整合适配代码之间的许可证兼容性已获确认。公开分发前需核实缺失许可模块的授权、AngelEye 的许可冲突、QQ 空间字体许可、实际上游版本/提交，以及各模块 AGPL/GPL 条款（含网络交互条款）的适用要求。本段是随附文件审计，不是法律意见。

服务器代码基线取自 2026-11-13 快照；部署前再次确认线上配置与补丁。

## 项目结构

```text
astrbot_plugin_zhiban/
  main.py                 AstrBot 插件入口与侧栏应用注册
  runtime.py              子模块生命周期、配置代理和冲突保护
  catalog.py              功能模块清单与默认菜单顺序
  legacy_config.py        旧插件配置导入
  scheduling.py           并发与队列调度限制
  memory_control.py       记忆隔离与人格审批控制
  _conf_schema.json       知伴配置页 schema
  logo.png                知伴侧栏图标
  ui_assets.py            页面资源映射与路径校验
  views/                  知伴应用页面
  modules/                按上游插件 ID 隔离的模块源码、资源和许可
  requirements.txt        合并后的 Python 依赖
tests/                    知伴适配、配置、页面及调度测试
build_schema.py           汇总模块配置 schema
package_release.py         构建发布 ZIP 和 SHA-256 清单
```

## 开发与测试

开发模式为“保留上游实现、在知伴宿主内适配生命周期与配置”，不把所有业务重写成新的单体实现。使用 Python 3.12、AstrBot 4.29.3 和仓库测试依赖；从仓库根目录执行：

```powershell
python build_schema.py
python build_views.py
python -m pytest tests -q
node --test tests/*.mjs
python package_release.py
```

测试主要验证本地适配与回归，不代表所有第三方服务、OneBot 桥接器或 Linux 目标环境均已端到端验收。

## 开发与发布

- AI 辅助开发模型：GPT-6 Astra。
- 小版本改动先本地实现和验证，重大版本验收后统一推送到 GitHub 私有仓库。
- 开发模式：尽量复用上游业务实现，由知伴统一承载模块生命周期、菜单和配置代理；页面及协议适配独立维护。
