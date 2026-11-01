# -*- coding: utf-8 -*-
"""Pure utility functions (no Flask request context).

Anything that needs ``request`` / ``g`` / ``jsonify`` belongs in
:mod:`sapic.utils.web` instead.
"""

from __future__ import annotations

import base64
import binascii

from ..basis.errors import ApiError, ErrorCode


def encode_cursor(*values) -> str:
    """Encode pagination cursor values into an opaque string."""
    raw = ":".join(str(v) for v in values)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[int, int]:
    """Decode a ``created_at:id`` cursor."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        created_at, row_id = raw.split(":", 1)
        return int(created_at), int(row_id)
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError) as exc:
        raise ApiError(
            "invalid cursor", ErrorCode.PARAM_ERROR, 400
        ) from exc
