"""Materialize upstream module pages under AstrBot's signed 知伴 view."""
from __future__ import annotations

import json
import shutil
from pathlib import Path, PurePosixPath

from astrbot_plugin_zhiban.catalog import MODULES
from astrbot_plugin_zhiban.ui_assets import MODULE_UI_ROOTS, prepare_module_ui_html


ROOT = Path(__file__).resolve().parent
PLUGIN_ROOT = ROOT / "astrbot_plugin_zhiban"
VIEW_ROOT = PLUGIN_ROOT / "views" / "知伴"
OUTPUT_ROOT = VIEW_ROOT / "modules"
MANIFEST = VIEW_ROOT / ".zhiban_generated_assets.json"
BRIDGE_ADAPTATIONS = {
    "scope": "mapped upstream index.html files",
    "mode": "authenticated SDK and module bridge injection",
    "theme": "module_bridge.js controlled light-green overrides",
    "unchanged_non_html_assets": True,
}
def _safe_relative_file(root: Path, value: str) -> Path | None:
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return None
    target = (root / Path(*relative.parts)).resolve(strict=False)
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def _materialize_logos(plugin_root: Path, view_root: Path) -> int:
    """Expose the plugin and module logos inside the signed view's asset root."""
    brand_source = plugin_root / "logo.png"
    if not brand_source.is_file():
        raise FileNotFoundError(f"Missing 知伴 logo: {brand_source}")
    shutil.copy2(brand_source, view_root / "logo.png")

    logo_root = view_root / "logos"
    logo_root.mkdir(parents=True, exist_ok=True)
    for item in MODULES:
        key = item["key"]
        package = item["package"]
        source = plugin_root / "modules" / package / "logo.png"
        if not source.is_file():
            raise FileNotFoundError(f"Missing logo for module {key}: {source}")
        shutil.copy2(source, logo_root / f"{key}{source.suffix.lower()}")
    return len(MODULES)


def build_views(
    plugin_root: Path = PLUGIN_ROOT,
    *,
    view_root: Path | None = None,
    mapping: dict[str, tuple[str, ...]] | None = None,
) -> dict:
    """Copy the selected upstream pages and install the authenticated bridge shim."""
    plugin_root = Path(plugin_root).resolve()
    view_root = Path(view_root or plugin_root / "views" / "知伴").resolve()
    output_root = view_root / "modules"
    output_root.mkdir(parents=True, exist_ok=True)
    mapping = mapping or MODULE_UI_ROOTS

    previous: set[str] = set()
    manifest_path = view_root / ".zhiban_generated_assets.json"
    try:
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(saved, list):
            saved_files = saved
        elif isinstance(saved, dict):
            saved_files = saved.get("generated_files", [])
        else:
            saved_files = []
        if isinstance(saved_files, list):
            previous = {item for item in saved_files if isinstance(item, str)}
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass

    generated: set[str] = set()
    for module, source_parts in mapping.items():
        if len(source_parts) < 2:
            raise ValueError(f"Invalid UI source mapping for {module}")
        source_root = plugin_root / "modules" / Path(*source_parts)
        if not source_root.is_dir():
            raise FileNotFoundError(f"Missing UI source for {module}: {source_root}")
        for source in source_root.rglob("*"):
            if not source.is_file():
                continue
            relative_inside = source.relative_to(source_root).as_posix()
            output_relative = PurePosixPath(module, relative_inside).as_posix()
            destination = _safe_relative_file(output_root, output_relative)
            if destination is None:
                raise ValueError(f"Unsafe generated asset path: {output_relative}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.name.lower() == "index.html":
                html = source.read_text(encoding="utf-8")
                depth = 2 + len(PurePosixPath(relative_inside).parent.parts)
                bridge_src = "../" * depth + "module_bridge.js"
                html = prepare_module_ui_html(
                    html, source_parts[0], module_bridge_src=bridge_src
                )
                destination.write_text(html, encoding="utf-8", newline="")
            else:
                shutil.copy2(source, destination)
            generated.add(output_relative)

    for stale in previous - generated:
        path = _safe_relative_file(output_root, stale)
        if path is not None and path.is_file():
            path.unlink()

    manifest = {
        "schema_version": 2,
        "generated_files": sorted(generated),
        "adaptations": BRIDGE_ADAPTATIONS,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="",
    )
    logos = _materialize_logos(plugin_root, view_root) if mapping == MODULE_UI_ROOTS else 0
    return {"modules": len(mapping), "files": len(generated), "logos": logos, "output": str(output_root)}


if __name__ == "__main__":
    print(json.dumps(build_views(), ensure_ascii=False))
