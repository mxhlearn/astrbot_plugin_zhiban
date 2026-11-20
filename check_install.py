#!/usr/bin/env python3
"""Check that an installed Zhiban plugin has its required web assets."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path


def _bridge_hash(view_root: Path) -> str:
    candidates = sorted(
        path.name for path in view_root.glob("module_bridge.*.js")
        if re.fullmatch(r"module_bridge\.[0-9a-f]{12}\.js", path.name)
    )
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected exactly one hashed module bridge, found {candidates or 'none'}"
        )
    return candidates[0].removeprefix("module_bridge.").removesuffix(".js")


def _catalog_keys(plugin_root: Path) -> list[str]:
    source = (plugin_root / "catalog.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "MODULES" for t in node.targets
        ):
            return [
                value.value
                for item in node.value.elts
                for key, value in zip(item.keys, item.values)
                if getattr(key, "value", None) == "key"
            ]
    return []


def resolve_plugin_root(path: Path) -> Path:
    if (path / "catalog.py").is_file():
        return path
    candidate = path / "astrbot_plugin_zhiban"
    if (candidate / "catalog.py").is_file():
        return candidate
    return path


def check(plugin_root: Path) -> dict:
    resolved = resolve_plugin_root(plugin_root)
    view_root = resolved / "views" / "知伴"
    problems = []
    if not (view_root / "index.html").is_file():
        problems.append("missing views/知伴/index.html")
    bridge_hash = None
    try:
        bridge_hash = _bridge_hash(view_root)
    except RuntimeError as exc:
        problems.append(str(exc))
    modules_root = view_root / "modules"
    module_pages = sorted(path.parent.relative_to(modules_root).as_posix()
                          for path in modules_root.rglob("index.html")) if modules_root.is_dir() else []
    if not module_pages:
        problems.append("missing generated module pages under views/知伴/modules")
    manifest_path = view_root / ".zhiban_generated_assets.json"
    if not manifest_path.is_file():
        problems.append("missing views/知伴/.zhiban_generated_assets.json")
    if bridge_hash:
        bridge_file = view_root / f"module_bridge.{bridge_hash}.js"
        if bridge_file.is_file():
            content_hash = hashlib.sha256(bridge_file.read_bytes()).hexdigest()[:12]
            if content_hash != bridge_hash:
                problems.append("hashed bridge content does not match its filename")
        stale = [
            page for page in module_pages
            if f"module_bridge.{bridge_hash}.js" not in (
                modules_root / page / "index.html"
            ).read_text(encoding="utf-8")
        ]
        if stale:
            problems.append("module pages reference a different bridge hash: " + ", ".join(stale[:5]))

    expected_pages = {
        "meme/a_manage", "meme/catalog", "meme/semantic", "meme/settings",
    }
    missing_deep_links = sorted(expected_pages - set(module_pages))
    if missing_deep_links:
        problems.append("missing meme deep links: " + ", ".join(missing_deep_links))

    keys = _catalog_keys(resolved)
    if len(keys) != 11:
        problems.append(f"expected 11 catalog modules, found {len(keys)}")
    if "parser" in keys:
        problems.append("catalog still contains removed parser module")

    manifest_path = view_root / ".zhiban_generated_assets.json"
    generated = []
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            generated = list(data.get("generated_files", []))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"invalid generated assets manifest: {type(exc).__name__}")
    checked = 0
    mismatches = []
    for relative in generated:
        relative = relative.removeprefix("modules/")
        path = modules_root / Path(*relative.split("/"))
        if not path.is_file():
            mismatches.append(relative)
            continue
        checked += 1
    if generated and checked != len(generated):
        problems.append(f"missing generated assets: {len(generated) - checked}")

    return {
        "ok": not problems,
        "module_pages": len(module_pages),
        "catalog_modules": len(keys),
        "generated_files": len(generated),
        "bridge_hash": bridge_hash,
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin_root", nargs="?", default=None)
    args = parser.parse_args()
    default = Path(__file__).resolve().parent / "astrbot_plugin_zhiban"
    root = Path(args.plugin_root).resolve() if args.plugin_root else default
    result = check(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
