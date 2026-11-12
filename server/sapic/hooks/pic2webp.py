# -*- coding: utf-8 -*-
"""pic2webp — convert JPEG/PNG payloads to WebP before they are stored.

Processor contract (kept from v1): ``upimg_stream_processor(stream, suffix,
config=None)`` returns ``{"code": 0, "data": {"stream": <bytes>}, "suffix":
".webp"}``; any other result is ignored by :func:`sapic.libs.images.
process_stream`, so a broken or unwanted conversion can never break an upload.

Transparency survives the conversion (RGBA/LA, plus palette images carrying a
transparency entry), and the lossy ``quality`` is configurable from the hook
page. Disabled by default: enabling it changes what is stored while the
original bytes are not kept.
"""

from __future__ import annotations

from io import BytesIO

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None

__version__ = "0.2.0"
__author__ = "blunt"
__description__ = "将JPG/PNG图片转为webp格式"
__catalog__ = "processor"
__state__ = "disabled"

SUFFIXES = (".jpg", ".jpeg", ".png")
DEFAULT_QUALITY = 75
MIN_QUALITY = 1
MAX_QUALITY = 100


def hook_manifest():
    return {
        "title": "转 WebP",
        "catalog": "processor",
        "config_schema": [
            {
                "key": "quality",
                "type": "number",
                "label": "WebP 质量",
                "default": DEFAULT_QUALITY,
                "min": MIN_QUALITY,
                "max": MAX_QUALITY,
                "help": "1-100，越大越清晰、体积也越大；默认 75",
            }
        ],
    }


def _quality(config=None) -> int:
    """Clamp the configured quality; unusable values fall back to the default."""
    try:
        value = int((config or {}).get("quality"))
    except (TypeError, ValueError):
        return DEFAULT_QUALITY
    if value <= 0:
        return DEFAULT_QUALITY
    return max(MIN_QUALITY, min(value, MAX_QUALITY))


def _has_alpha(picture) -> bool:
    """Palette images hide transparency in ``info`` instead of the mode."""
    return picture.mode in ("RGBA", "LA") or (
        picture.mode == "P" and "transparency" in picture.info
    )


def upimg_stream_processor(stream, suffix, config=None, **kwargs):
    if Image is None:
        return {"code": 1, "message": "Please install Pillow module"}
    if not stream or str(suffix).lower() not in SUFFIXES:
        return {"code": 1, "message": "not a jpeg/png image"}

    buffer = BytesIO()
    try:
        with Image.open(BytesIO(stream)) as picture:
            #: ``convert("RGB")`` would flatten transparent pixels onto a solid
            #: background, which ruins logos and UI screenshots.
            target = picture.convert("RGBA" if _has_alpha(picture) else "RGB")
            target.save(
                buffer,
                "WEBP",
                optimize=True,
                quality=_quality(config),
            )
    except Exception as exc:
        return {"code": 1, "message": str(exc)}
    return {"code": 0, "data": {"stream": buffer.getvalue()}, "suffix": ".webp"}
