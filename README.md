# 知伴：服务器插件整合

![知伴 Logo](astrbot_plugin_zhiban/logo.png)

此仓库整合 QQ 机器人服务器当前使用的九个 AstrBot 插件，并使用 LivingMemory 2.8.2 替换 AngelMemory 作为记忆模块。插件运行于 AstrBot，支持 OneBot v11（`aiocqhttp`），不限定 Linux，并在 AstrBot 左侧「扩展功能」添加「知伴」应用入口。进入后可选择功能模块，在同一应用的「配置」视图编辑模块参数、密钥与启用状态，保存后应用重载；图片创作与音乐点播复用各自原有配置页面。兼容范围、安装切换流程、模块配置及验收边界见 [插件 README](astrbot_plugin_zhiban/README.md)。

## 仓库结构

- astrbot_plugin_zhiban：可安装插件、九个服务器模块及 LivingMemory 记忆实现。
- tests：调度、配置导入、记忆隔离、媒体限制和 AstrBot 注册表集成测试。
- build_schema.py：从各服务器模块 schema 生成中文配置菜单。
- package_release.py：生成含插件源码、必要静态资源及现有许可文件的本地验证 ZIP，不含凭据和用户数据；许可缺口不会因打包而消失。
- upstream、.venv：本地回归环境和源码基线，不进入版本控制。

## 本地开发

使用 Python 3.12 并先安装 AstrBot 4.29.3 的开发依赖，再安装仓库 requirements.txt 与测试依赖。不要把 data/config、data/plugin_data、模型密钥、供应商配置或生产数据库加入提交。

```powershell
python build_schema.py
python build_views.py
python -m pytest tests -q
node --test tests/*.mjs
python package_release.py
```

旧 LivingMemory 配置在知伴首次启动时从 `data/config/astrbot_plugin_livingmemory_config.json` 导入；记忆数据库继续留在 `data/plugin_data/astrbot_plugin_livingmemory/`。本仓库只保存导入器和功能代码，不保存配置值或记忆数据。

Linux 与 SnowLuma 测试需在部署机或隔离环境另行完成。当前仓库回归通过不代表 Linux QQ Hook 和 2 GB 全栈已验证。

## 开发与发布

- AI 辅助开发模型：GPT-6 Astra。
- 小版本改动先在本地完成实现与验证，汇总到重大版本里程碑后再统一推送私有仓库。
- 不为每次小修单独推送；服务器测试和发布记录按版本归档。
