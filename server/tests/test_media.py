# -*- coding: utf-8 -*-
import io
import struct
import zlib
from pathlib import Path

from sapic.libs.media import image_size, strip_metadata
from sapic.models import Image, ImageBackend

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def png_chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def png_bytes(width=640, height=480, extra: bytes = b"") -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return PNG_MAGIC + png_chunk(b"IHDR", ihdr) + extra + png_chunk(b"IEND", b"")


def jpeg_bytes(width=800, height=600, app1: bytes = b"") -> bytes:
    out = b"\xff\xd8"
    app0 = b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    out += b"\xff\xe0" + struct.pack(">H", len(app0) + 2) + app0
    if app1:
        out += b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
    sof = (
        b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    )
    out += b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof
    sos = b"\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"
    out += b"\xff\xda" + struct.pack(">H", len(sos) + 2) + sos + b"\x00\x11\x22"
    return out + b"\xff\xd9"


def webp_bytes(width=320, height=240, exif=False, xmp=False) -> bytes:
    flags = (0x08 if exif else 0) | (0x04 if xmp else 0)
    vp8x = (
        struct.pack("<I", flags)
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )
    chunks = b"VP8X" + struct.pack("<I", len(vp8x)) + vp8x
    for fourcc, payload in (
        (b"EXIF", b"Exif\x00\x00MM\x00*" if exif else b""),
        (b"XMP ", b"<x:xmpmeta/>" if xmp else b""),
    ):
        if not payload:
            continue
        chunks += fourcc + struct.pack("<I", len(payload)) + payload
        if len(payload) % 2:
            chunks += b"\x00"
    body = b"WEBP" + chunks
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_image_size_reads_headers():
    assert image_size(jpeg_bytes(800, 600)) == (800, 600)
    assert image_size(png_bytes(640, 480)) == (640, 480)
    assert image_size(b"GIF89a" + struct.pack("<HH", 12, 34) + b"\x00\x00\x00") == (12, 34)
    assert image_size(webp_bytes(320, 240)) == (320, 240)


def test_image_size_tolerates_garbage():
    assert image_size(b"") is None
    assert image_size(b"not an image at all") is None
    #: 截断的 PNG 只有签名，头部不完整。
    assert image_size(PNG_MAGIC + b"\x00\x00") is None


def test_strip_jpeg_removes_exif_and_xmp():
    exif = b"Exif\x00\x00" + b"MM\x00*" + b"\x00" * 24
    xmp = b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta/>"
    stripped = strip_metadata(jpeg_bytes(800, 600, app1=exif))
    assert b"Exif" not in stripped
    assert image_size(stripped) == (800, 600)
    assert stripped.endswith(b"\xff\xd9")

    stripped = strip_metadata(jpeg_bytes(800, 600, app1=xmp))
    assert b"xmpmeta" not in stripped
    assert image_size(stripped) == (800, 600)


def test_strip_png_removes_exif_and_xmp_text():
    extra = png_chunk(b"eXIf", b"Exif\x00\x00payload") + png_chunk(
        b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00<x:xmpmeta/>"
    )
    stripped = strip_metadata(png_bytes(640, 480, extra))
    assert b"eXIf" not in stripped
    assert b"xmpmeta" not in stripped
    assert image_size(stripped) == (640, 480)
    assert stripped.startswith(PNG_MAGIC)


def test_strip_webp_removes_chunks_and_updates_container():
    stripped = strip_metadata(webp_bytes(320, 240, exif=True, xmp=True))
    assert b"EXIF" not in stripped
    assert b"XMP " not in stripped
    assert image_size(stripped) == (320, 240)
    #: RIFF 长度必须与实际内容一致，否则严格的解码器会拒绝。
    assert struct.unpack("<I", stripped[4:8])[0] == len(stripped) - 8
    #: VP8X 里声明「有 EXIF/XMP」的标志位已清掉。
    flags = struct.unpack("<I", stripped[20:24])[0]
    assert not flags & 0x08 and not flags & 0x04


def test_strip_metadata_is_noop_without_metadata():
    plain = png_bytes(10, 20)
    assert strip_metadata(plain) is plain
    gif = b"GIF89a" + struct.pack("<HH", 12, 34) + b"\x00\x00\x00"
    assert strip_metadata(gif) is gif


def register_and_login(client):
    client.post(
        "/api/v2/auth/register",
        json={"username": "alice", "password": "secret123"},
    )
    response = client.post(
        "/api/v2/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    return response.get_json()["data"]["csrf"]


def test_upload_records_size_and_strips_metadata(app, client):
    """上传按文件头记录宽高，落盘字节里不再带 EXIF。"""
    csrf = register_and_login(client)
    payload = jpeg_bytes(800, 600, app1=b"Exif\x00\x00" + b"\x00" * 32)
    response = client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(payload), "photo.jpg")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()
    image = response.get_json()["data"]["image"]
    assert (image["width"], image["height"]) == (800, 600)
    #: 剥掉 APP1 后体积变小，记录的大小要跟实际落盘一致。
    assert image["size"] < len(payload)

    with app.app_context():
        row = Image.get(Image.sha == image["sha"])
        replica = ImageBackend.get(ImageBackend.image == row)
        stored = Path(app.config["STORAGE_DIR"]) / replica.object_key
        assert b"Exif" not in stored.read_bytes()
        assert row.width == 800 and row.height == 600

    assert b"Exif" not in client.get(image["src"]).data
