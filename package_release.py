"""打包插件源码、必要静态资源和校验清单，不含配置、令牌或用户数据。"""
from pathlib import Path
import ast
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "astrbot_plugin_zhiban"


def build():
    from build_views import build_views

    build_views()
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    version_line = None
    for line in (PLUGIN / "metadata.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            version_line = line.split(":", 1)[1].strip().strip("'")
            break
    if not version_line:
        raise ValueError("Plugin metadata has no version")
    archive = out / f"zhiban-{version_line}.zip"
    manifest = []
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PLUGIN.rglob("*")):
            if not p.is_file():
                continue
            parts = p.relative_to(PLUGIN).parts
            if set(parts) & {"__pycache__", ".pytest_cache", ".git", "node_modules", "tests"}:
                continue
            if parts[:2] in {
                ("modules", "astrbot_plugin_angel_memory"),
                ("modules", "astrbot_plugin_link_filter"),
            }:
                continue
            if p.suffix in {".pyc", ".db", ".sqlite3", ".log"} or p.name.startswith(".env"):
                continue
            raw = p.read_bytes()
            if p.suffix == ".py":
                ast.parse(raw.decode("utf-8-sig"), filename=str(p))
            name = p.relative_to(PLUGIN).as_posix()
            z.writestr(name, raw)
            manifest.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"files": len(manifest), "archive_bytes": archive.stat().st_size,
                      "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    build()
