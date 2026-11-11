# -*- coding: utf-8 -*-
"""sapic.libs.media

Header-level media helpers: intrinsic size and metadata stripping.

Both features are deliberately dependency free — only container headers are
read, so an upload never pays for a full decode and Pillow is only needed by the
``pic2webp`` hook, never here. Anything unparsable returns
``None`` / the original bytes instead of raising: media handling must never
be the reason an upload fails.
"""

from __future__ import annotations

import struct

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8"
GIF_MAGICS = (b"GIF87a", b"GIF89a")

#: JPEG APP1 payloads that only carry capture metadata (EXIF / XMP).
_JPEG_METADATA_PREFIXES = (
    b"Exif\x00\x00",
    b"http://ns.adobe.com/xap/",
    b"http://ns.adobe.com/xmp/extension/",
)

#: WebP chunks dropped on save; the VP8X flag bits that announce them.
_WEBP_METADATA_CHUNKS = {b"EXIF": 0x08, b"XMP ": 0x04}


def image_size(stream: bytes, suffix: str = "") -> tuple[int, int] | None:
    """Intrinsic ``(width, height)`` in pixels, ``None`` when unknown.

    ``suffix`` is accepted for symmetry with :func:`strip_metadata`; the
    container is sniffed from the bytes so a mislabeled file still works.
    """
    if not stream:
        return None
    try:
        if stream.startswith(JPEG_MAGIC):
            return _jpeg_size(stream)
        if stream.startswith(PNG_MAGIC):
            return _png_size(stream)
        if stream.startswith(GIF_MAGICS):
            return _gif_size(stream)
        if stream[:4] == b"RIFF" and stream[8:12] == b"WEBP":
            return _webp_size(stream)
    except (IndexError, struct.error, ValueError):
        return None
    return None


def strip_metadata(stream: bytes, suffix: str = "") -> bytes:
    """Remove EXIF/XMP (capture time, camera, GPS) from JPEG/PNG/WebP.

    Images uploaded to a public bed are meant to be embedded, not archived:
    capture metadata mostly leaks location and device details. Videos, GIFs,
    BMP/ICO and SVG are returned untouched, and so is every payload where
    nothing had to be removed (the common path stays a no-op).
    """
    if not stream:
        return stream
    try:
        if stream.startswith(JPEG_MAGIC):
            return _strip_jpeg(stream)
        if stream.startswith(PNG_MAGIC):
            return _strip_png(stream)
        if stream[:4] == b"RIFF" and stream[8:12] == b"WEBP":
            return _strip_webp(stream)
    except (IndexError, struct.error, ValueError):
        return stream
    return stream


def _jpeg_size(stream: bytes) -> tuple[int, int] | None:
    """Walk the marker chain until the SOF segment reports the frame size."""
    index = 2
    while index + 3 < len(stream):
        if stream[index] != 0xFF:
            return None
        marker = stream[index + 1]
        if marker == 0xFF:
            #: Fill byte, keep looking for the real marker.
            index += 1
            continue
        if marker in (0x01, 0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        if marker == 0xDA:
            #: Start of scan: the frame header must have come earlier.
            return None
        length = struct.unpack(">H", stream[index + 2:index + 4])[0]
        if length < 2:
            return None
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            #: SOFn payload: precision(1), height(2), width(2).
            payload = index + 4
            height = struct.unpack(">H", stream[payload + 1:payload + 3])[0]
            width = struct.unpack(">H", stream[payload + 3:payload + 5])[0]
            return (width, height) if width and height else None
        index += 2 + length
    return None


def _png_size(stream: bytes) -> tuple[int, int] | None:
    """IHDR is always the first chunk: 8-byte signature + 4 length + 4 type."""
    if stream[12:16] != b"IHDR" or len(stream) < 24:
        return None
    width, height = struct.unpack(">II", stream[16:24])
    return (width, height) if width and height else None


def _gif_size(stream: bytes) -> tuple[int, int] | None:
    """Logical screen descriptor right after the 6-byte signature."""
    if len(stream) < 10:
        return None
    width, height = struct.unpack("<HH", stream[6:10])
    return (width, height) if width and height else None


def _webp_size(stream: bytes) -> tuple[int, int] | None:
    """Read the canvas from VP8X, or the frame header of VP8/VP8L."""
    index = 12
    while index + 8 <= len(stream):
        fourcc = stream[index:index + 4]
        size = struct.unpack("<I", stream[index + 4:index + 8])[0]
        data = index + 8
        if fourcc == b"VP8X" and data + 10 <= len(stream):
            width = 1 + int.from_bytes(stream[data + 4:data + 7], "little")
            height = 1 + int.from_bytes(stream[data + 7:data + 10], "little")
            return (width, height)
        if fourcc == b"VP8 " and data + 10 <= len(stream):
            if stream[data + 3:data + 6] == b"\x9d\x01\x2a":
                width = struct.unpack("<H", stream[data + 6:data + 8])[0]
                height = struct.unpack("<H", stream[data + 8:data + 10])[0]
                return (width & 0x3FFF, height & 0x3FFF)
        if fourcc == b"VP8L" and data + 5 <= len(stream):
            if stream[data] == 0x2F:
                bits = struct.unpack("<I", stream[data + 1:data + 5])[0]
                return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        index = data + size + (size & 1)
    return None


def _strip_jpeg(stream: bytes) -> bytes:
    """Drop APP1 EXIF/XMP segments, keeping every other marker intact."""
    out = bytearray(stream[:2])
    index = 2
    while index + 3 < len(stream):
        if stream[index] != 0xFF:
            #: Marker chain lost sync: better to keep the file than to mangle it.
            return stream
        marker = stream[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker == 0xDA:
            #: Everything from the scan onwards is entropy-coded payload.
            out += stream[index:]
            return bytes(out)
        if marker in (0x01, 0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            out += stream[index:index + 2]
            index += 2
            continue
        length = struct.unpack(">H", stream[index + 2:index + 4])[0]
        if length < 2 or index + 2 + length > len(stream):
            return stream
        end = index + 2 + length
        payload = stream[index + 4:end]
        if marker == 0xE1 and payload.startswith(_JPEG_METADATA_PREFIXES):
            index = end
            continue
        out += stream[index:end]
        index = end
    #: 没有扫描段（截断/异常文件）时把剩余字节原样带上，不要截断文件。
    return bytes(out + stream[index:])


def _strip_png(stream: bytes) -> bytes:
    """Drop the ``eXIf`` chunk and XMP text chunks, CRC stays untouched."""
    out = bytearray(PNG_MAGIC)
    index = len(PNG_MAGIC)
    changed = False
    while index + 8 <= len(stream):
        size = struct.unpack(">I", stream[index:index + 4])[0]
        chunk_type = stream[index + 4:index + 8]
        end = index + 12 + size
        if end > len(stream):
            return stream
        data = stream[index + 8:index + 8 + size]
        drop = chunk_type == b"eXIf" or (
            chunk_type in (b"tEXt", b"iTXt", b"zTXt")
            and data.startswith(b"XML:com.adobe.xmp\x00")
        )
        if drop:
            changed = True
        else:
            out += stream[index:end]
        index = end
        if chunk_type == b"IEND":
            break
    return bytes(out) if changed else stream


def _strip_webp(stream: bytes) -> bytes:
    """Drop ``EXIF``/``XMP `` chunks, then fix RIFF size and VP8X flags."""
    out = bytearray(stream[:12])
    index = 12
    removed_flags = 0
    while index + 8 <= len(stream):
        fourcc = stream[index:index + 4]
        size = struct.unpack("<I", stream[index + 4:index + 8])[0]
        end = index + 8 + size + (size & 1)
        if end > len(stream):
            return stream
        flag = _WEBP_METADATA_CHUNKS.get(fourcc)
        if flag is not None:
            removed_flags |= flag
        else:
            out += stream[index:end]
        index = end
    if not removed_flags:
        return stream

    #: VP8X 的标志位声明「文件里有 EXIF/XMP」，删了块就要一起清掉。
    if out[12:16] == b"VP8X" and len(out) >= 24:
        flags = struct.unpack("<I", out[20:24])[0] & ~removed_flags
        struct.pack_into("<I", out, 20, flags)
    struct.pack_into("<I", out, 4, len(out) - 8)
    return bytes(out)
