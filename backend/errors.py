"""业务异常。

服务层只抛 AppError（或 ValueError），HTTP 层统一翻译成状态码 + JSON，
避免业务代码里出现 HTTPStatus 依赖。
"""
from __future__ import annotations


class AppError(Exception):
    """带 HTTP 语义的业务异常。"""

    status = 400
    code = "bad_request"

    def __init__(self, message: str, status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status
        if code is not None:
            self.code = code


class ValidationError(AppError):
    status = 400
    code = "validation_error"


class AuthError(AppError):
    status = 401
    code = "unauthorized"


class PermissionDenied(AppError):
    status = 403
    code = "forbidden"


class NotFound(AppError):
    status = 404
    code = "not_found"


class ConflictError(AppError):
    status = 409
    code = "conflict"
