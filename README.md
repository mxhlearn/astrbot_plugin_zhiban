# 知伴：服务器插件整合

此仓库整合 QQ 机器人服务器当前使用的十个 AstrBot 插件，菜单按预期使用频率排序。插件实施说明、安装切换流程、模块配置及验收边界见 [插件 README](astrbot_plugin_zhiban/README.md)。

## 仓库结构

- astrbot_plugin_zhiban：可安装插件及服务器源码快照副本。
- tests：调度、配置导入、记忆隔离、媒体限制和 AstrBot 注册表集成测试。
- build_schema.py：从各服务器模块 schema 生成中文配置菜单。
- package_release.py：生成仅含源码和随附许可的 ZIP。
- upstream、.venv：本地回归环境和源码基线，不进入版本控制。

## 本地开发

使用 Python 3.12 并先安装 AstrBot 4.29.3 的开发依赖，再安装仓库 requirements.txt 与测试依赖。不要把 data/config、data/plugin_data、模型密钥、供应商配置或生产数据库加入提交。

```powershell
python build_schema.py
python -m pytest tests -q
python package_release.py
```

服务器配置由插件首次启动时从旧插件设置文件导入；本仓库只保存导入器和功能代码，不保存服务器配置值。

Linux 与 SnowLuma 测试需在部署机或隔离环境另行完成。当前仓库回归通过不代表 Linux QQ Hook 和 2 GB 全栈已验证。
