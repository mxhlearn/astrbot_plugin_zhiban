"""Materialize upstream module pages under AstrBot's signed 知伴 view."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath

from astrbot_plugin_zhiban.catalog import MODULES
from astrbot_plugin_zhiban.ui_assets import MODULE_UI_ROOTS, prepare_module_ui_html


ROOT = Path(__file__).resolve().parent
PLUGIN_ROOT = ROOT / "astrbot_plugin_zhiban"
VIEW_ROOT = PLUGIN_ROOT / "views" / "知伴"
OUTPUT_ROOT = VIEW_ROOT / "modules"
MANIFEST = VIEW_ROOT / ".zhiban_generated_assets.json"
BRIDGE_REASON = "authenticated SDK and module bridge injection"
HEART_REBUILD_REASON = (
    "rebuilt from the adapted heart webui for Zhiban branding, Chinese copy, "
    "and the controlled light-green theme"
)
NON_HTML_ADAPTATIONS = {
    ("heart", "assets/index-BL7DV78x.js"): {
        "source": "astrbot_plugin_angel_heart/pages/chat-config/assets/index-BL7DV78x.js",
        "reason": HEART_REBUILD_REASON,
    },
    ("heart", "assets/style-LSpSUt7F.css"): {
        "source": "astrbot_plugin_angel_heart/pages/chat-config/assets/style-LSpSUt7F.css",
        "reason": HEART_REBUILD_REASON,
    },
}
BRIDGE_ADAPTATIONS = {
    "scope": "mapped upstream resources",
    "mode": BRIDGE_REASON,
    "theme": "first-paint head CSS plus module_bridge.js controlled light-green overrides",
    "motion": "in-panel module loading with reduced-motion opt-out",
    "non_html_policy": (
        "only registered adaptations may differ; all other non-HTML resources "
        "are copied byte-for-byte"
    ),
    "unchanged_non_html_assets": True,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _non_html_adaptation(
    module: str, source_parts: tuple[str, ...], relative_inside: str
) -> dict[str, str] | None:
    """Return the explicit registry entry for an adapted non-HTML resource."""
    relative = PurePosixPath(relative_inside)
    source_is_heart_build = (
        source_parts[0] == "astrbot_plugin_angel_heart"
        and source_parts[1:3] == ("pages", "chat-config")
    )
    if not source_is_heart_build or relative.parts[:1] != ("assets",):
        return None
    adaptation = NON_HTML_ADAPTATIONS.get((module, relative.as_posix()))
    if adaptation is None:
        raise ValueError(f"Adapted resource is missing from the manifest: {module}/{relative}")
    return adaptation


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
    adapted_assets: list[dict[str, str]] = []
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
            source_path = PurePosixPath(
                *source_parts, *PurePosixPath(relative_inside).parts
            ).as_posix()
            if source.name.lower() == "index.html":
                html = source.read_text(encoding="utf-8")
                depth = 2 + len(PurePosixPath(relative_inside).parent.parts)
                bridge_src = "../" * depth + "module_bridge.js"
                reason = BRIDGE_REASON
                # The meme upstream root is only a redirect to a_manage. A
                # sandboxed srcdoc cannot follow that navigation reliably, so
                # materialize the management page at the module entry and keep
                # its relative assets anchored to a_manage with a base URL.
                if (
                    module == "meme"
                    and relative_inside == "index.html"
                    and (source_root / "a_manage" / "index.html").is_file()
                ):
                    source = source_root / "a_manage" / "index.html"
                    source_path = PurePosixPath(
                        *source_parts, "a_manage", "index.html"
                    ).as_posix()
                    html = source.read_text(encoding="utf-8")
                    bridge_src = "../../../module_bridge.js"
                    reason = (
                        "entry redirect materialized as the management page with "
                        "a controlled base URL for sandboxed embedding"
                    )
                html = prepare_module_ui_html(
                    html, source_parts[0], module_bridge_src=bridge_src
                )
                if module == "meme" and relative_inside == "index.html":
                    html = re.sub(
                        r"<head\b[^>]*>",
                        lambda match: match.group(0) + '<base href="./a_manage/">',
                        html,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                destination.write_text(html, encoding="utf-8", newline="")
                adaptation = {"source": source_path, "reason": reason}
            else:
                registered = _non_html_adaptation(
                    module, source_parts, relative_inside
                )
                adaptation = registered
                shutil.copy2(source, destination)
            if adaptation is not None:
                adapted_assets.append(
                    {
                        "path": output_relative,
                        "sha256": _sha256(destination),
                        "reason": adaptation["reason"],
                        "source": adaptation["source"],
                    }
                )
            generated.add(output_relative)

    for stale in previous - generated:
        path = _safe_relative_file(output_root, stale)
        if path is not None and path.is_file():
            path.unlink()

    manifest = {
        "schema_version": 3,
        "generated_files": sorted(generated),
        "adaptations": {
            **BRIDGE_ADAPTATIONS,
            "adapted_assets": sorted(adapted_assets, key=lambda item: item["path"]),
        },
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
