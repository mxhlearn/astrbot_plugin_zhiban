# Upstream 记录

- 项目：`drdon1234/astrbot_plugin_media_parser`
- 地址：https://github.com/drdon1234/astrbot_plugin_media_parser
- 锁定提交：`0ec4ad6f67a9b4618f8effd995ca74023dddaa22`
- 快照版本：`1.13.3`
- 许可证：GNU Affero General Public License v3.0，随附 `LICENSE`。
- 核验时间：2026-11-17；上游为非 fork、非归档仓库，80 stars，最近提交于 2026-11-14。

## 知伴适配

- 保留上游解析器、下载器、消息交付、配置 schema 与资源文件。
- 移除上游开发用 `AGENTS.md` 和本地独立运行脚本 `run_local.py`，不作为运行时入口。
- 增加只读 `module_readiness`：基础解析可用；Playwright 网页截图增强和 FFmpeg 转码/合并增强缺失时明确降级说明。
- 不执行上游安装脚本；依赖由部署者按 `requirements.txt` 安装。Playwright Chromium 需单独安装并以真实平台解析验证。
