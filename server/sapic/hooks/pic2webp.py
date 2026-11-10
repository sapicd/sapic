# -*- coding: utf-8 -*-
"""pic2webp — convert JPEG/PNG payloads to WebP before they are stored.

Processor contract (kept from v1): ``upimg_stream_processor(stream, suffix)``
returns ``{"code": 0, "data": {"stream": <bytes>}, "suffix": ".webp"}``; any
other result is ignored by :func:`sapic.libs.images.process_stream`, so a
broken or unwanted conversion can never break an upload.

Disabled by default: enabling it changes what is stored while the original
bytes are not kept.
"""

from __future__ import annotations

from io import BytesIO

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None

__version__ = "0.1.0"
__author__ = "blunt"
__description__ = "将JPG/PNG图片转为webp格式"
__catalog__ = "processor"
__state__ = "disabled"

SUFFIXES = (".jpg", ".jpeg", ".png")
QUALITY = 75


def hook_manifest():
    return {"title": "转 WebP", "catalog": "processor"}


def upimg_stream_processor(stream, suffix, **kwargs):
    if Image is None:
        return {"code": 1, "message": "Please install Pillow module"}
    if not stream or str(suffix).lower() not in SUFFIXES:
        return {"code": 1, "message": "not a jpeg/png image"}

    buffer = BytesIO()
    try:
        with Image.open(BytesIO(stream)) as picture:
            picture.convert("RGB").save(
                buffer, "WEBP", optimize=True, quality=QUALITY
            )
    except Exception as exc:
        return {"code": 1, "message": str(exc)}
    return {"code": 0, "data": {"stream": buffer.getvalue()}, "suffix": ".webp"}
