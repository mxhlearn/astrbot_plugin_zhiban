# 知伴：AstrBot 整合应用

![知伴 Logo](astrbot_plugin_zhiban/logo.png)

知伴将服务器当前使用的十个 AstrBot 业务模块整合到一个中文侧栏应用，统一聊天准入、模块生命周期、状态、配置入口和资源边界。插件运行于 AstrBot，支持 OneBot v11（`aiocqhttp`），可在满足依赖的 Windows 与 Linux 环境部署，不限定 Linux，也不是独立 OneBot 服务。

当前版本为 `0.3.1`，使用浅绿色统一界面，固定五个一级入口：

- 总览：运行总览、全局设置
- 聊天系统：聊天互动、主动问候、历史查询
- 记忆成长：LivingMemory
- 表达创作：表情互动、语音回复、图片创作、音乐点播
- QQ 社交：QQ 动态、QQ 资料

内容过滤模块不再注册或进入运行包。安装、兼容范围、配置方式、来源许可、外部依赖和验收边界见 [插件 README](astrbot_plugin_zhiban/README.md)。

## 仓库结构

- `astrbot_plugin_zhiban`：可安装插件、十个运行模块、侧栏应用与统一桥接。
- `tests`：生命周期、调度、配置冲突、密钥脱敏、页面资源和桥接测试。
- `build_views.py`：生成上游页面资源、注入受控桥接并写入资源适配清单。
- `build_schema.py`：汇总模块配置 schema。
- `package_release.py`：生成发布 ZIP、逐文件哈希清单和 SHA-256。
- `upstream`、`.venv`：本地基线与回归环境，不进入版本控制。

## 本地开发

使用 Python 3.12，并准备 AstrBot 4.29.3 兼容环境：

~~~~powershell
python build_schema.py
python build_views.py
python -m pytest tests -q
node --test tests/*.mjs
python package_release.py
~~~~

不要提交 `data/config`、`data/plugin_data`、模型密钥、供应商凭据、用户记忆或生产数据库。上游页面继续保留自身业务逻辑；知伴负责生命周期、配置、状态、导航和经过清单记录的主题适配。

AI 辅助开发模型：GPT-6 Astra。小版本在本地累积并完成回归，重大版本验收后统一推送私有 GitHub 仓库；生产部署另行执行服务器测试。

## 当前验证

- Python 97 项测试、18 个子测试通过。
- Node 17 项测试通过。
- 本机 AstrBot 4.29.3 已加载十个模块，真实登录态页面完成五入口、工作台、配置、业务就绪提示和响应式布局验收。
- QQ 空间缺少 Cookie 时明确显示“业务未就绪”；语音、图片、音乐和 QQ 资料的真实外部操作未执行。
- 当前入口重复点击不再重建页面或发出业务请求；全局设置接口约 26 ms，状态快照最多复用 5 秒；20 次模块往返平均约 1.44 秒。
- 20 次往返抽查中文档数保持 3、节点数保持 899，但活动 frame 与监听数会随访问过的不同模块累积，长期回收仍需进一步验收；完整 Linux、OneBot 和 2 GB 全栈资源目标也未验收。
