# -*- coding: utf-8 -*-
"""Unified API errors.

API responses use stable string codes so the Vue frontend can map them to
localised messages.
"""

from __future__ import annotations

from enum import Enum

from flask import current_app, g
from werkzeug.exceptions import HTTPException


class ErrorCode(str, Enum):
    BAD_REQUEST = "BAD_REQUEST"
    PARAM_ERROR = "PARAM_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


_HTTP_CODE_MAP = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.INTERNAL_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


class ApiError(Exception):
    """Raise to abort the request and return a JSON error."""

    def __init__(
        self,
        message: str,
        code: ErrorCode | str = ErrorCode.BAD_REQUEST,
        status_code: int = 400,
        details=None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code.value if isinstance(code, ErrorCode) else str(code)
        self.status_code = status_code
        self.details = details


def _payload(code: str, message: str, details=None) -> dict:
    body = {
        "code": code,
        "message": message,
        "request_id": getattr(g, "request_id", ""),
    }
    if details is not None:
        body["details"] = details
    return body


def register_error_handlers(app) -> None:
    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return _payload(exc.code, exc.message, exc.details), exc.status_code

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        code = _HTTP_CODE_MAP.get(exc.code, ErrorCode.BAD_REQUEST)
        return _payload(code.value, exc.description or exc.name), exc.code

    @app.errorhandler(Exception)
    def _unhandled_error(exc: Exception):
        current_app.logger.exception("Unhandled error: %s", exc)
        return _payload(
            ErrorCode.INTERNAL_ERROR.value, "Internal server error"
        ), 500
