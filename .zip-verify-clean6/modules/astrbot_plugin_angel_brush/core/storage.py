"""Storage & validation."""

from __future__ import annotations

import base64
import io
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 16_000_000


def decode_b64(data: str) -> bytes:
    encoded = (
        data.split(",", 1)[1]
        if data.strip().startswith("data:") and "," in data
        else data
    )
    # remove whitespace
    compact = "".join(ch for ch in encoded if not ch.isspace())
    if len(compact) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise ValueError("图片 Base64 数据超过大小限制")
    raw = base64.b64decode(compact)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("图片超过 8 MiB 大小限制")
    return raw


def format_info(data: bytes) -> tuple[str, str, int, int]:
    if not data:
        raise ValueError("供应商返回了空图片")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("图片超过 8 MiB 大小限制")
    try:
        fmt = Image.open(io.BytesIO(data)).format
    except Exception:
        raise ValueError("无法识别真实图片格式")
    fmt = (fmt or "").upper()
    mapping = {
        "PNG": ("image/png", "png"),
        "JPEG": ("image/jpeg", "jpg"),
        "JPG": ("image/jpeg", "jpg"),
        "GIF": ("image/gif", "gif"),
        "WEBP": ("image/webp", "webp"),
        "BMP": ("image/bmp", "bmp"),
    }
    if fmt not in mapping:
        raise ValueError("当前仅支持 PNG、JPEG、GIF、WebP 和 BMP 图片")
    mime, ext = mapping[fmt]
    try:
        im = Image.open(io.BytesIO(data))
        w, h = im.size
    except Exception as e:
        raise ValueError(f"读取图片尺寸失败：{e}")
    if w == 0 or h == 0 or w * h > MAX_PIXELS:
        raise ValueError(f"图片尺寸不安全：{w}x{h}")
    return mime, ext, w, h


def persist_image(
    data_dir: Path,
    data: bytes,
    remote_url: str | None = None,
    revised_prompt: str | None = None,
) -> dict:
    mime, ext, w, h = format_info(data)
    date_dir = datetime.now().strftime("%Y%m%d")
    # [本地补丁] 输出到 AstrBot temp 目录，该目录在 send_message_to_user 的
    # 本地文件发送白名单内；原 plugin_data 路径会被沙箱校验拒绝。
    fname = f"{uuid.uuid4()}.{ext}"

    # 1) 插件数据目录：供 WebUI「已生成」面板展示
    panel_dir = data_dir / "generated-images" / date_dir
    panel_path = panel_dir / fname

    # 2) AstrBot temp 目录：位于 send_message_to_user 的本地文件白名单内，
    #    用于把图片发给 QQ 用户（原始 plugin_data 路径会被沙箱校验拒绝）。
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_root

        send_dir = (
            Path(get_astrbot_root()) / "data" / "temp" / "brush-images" / date_dir
        )
    except Exception:
        send_dir = panel_dir

    out_path = send_dir / fname
    try:
        send_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
    except Exception:
        out_path = panel_path
    try:
        panel_dir.mkdir(parents=True, exist_ok=True)
        if panel_path != out_path:
            panel_path.write_bytes(data)
    except Exception:
        pass
    # relative to plugin data dir for markdown
    try:
        rel = panel_path.relative_to(data_dir).as_posix()
    except ValueError:
        rel = panel_path.as_posix()
    markdown = f"![生成图片]({rel})"
    return {
        "relative_path": rel,
        "remote_url": remote_url,
        "markdown": markdown,
        "mime": mime,
        "width": w,
        "height": h,
        "revised_prompt": revised_prompt,
        "absolute_path": str(out_path),
    }
