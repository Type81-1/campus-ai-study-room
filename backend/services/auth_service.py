"""登录与身份校验（用户模块）。

注意：当前仍为课程演示级别的明文口令比对；口令哈希与令牌会话属于 P1 改造项，
此处只把校验逻辑收敛到一处，方便后续替换。
"""
from __future__ import annotations

from ..errors import AuthError, NotFound, PermissionDenied, ValidationError
from ..repositories import user_repository


def login(db, username, password) -> dict:
    if not username or not password:
        raise ValidationError("缺少字段：username, password")
    with db.session() as session:
        user = user_repository.find_by_credentials(session, username, password)
    if not user:
        raise AuthError("账号或密码错误")
    return user


def require_user(session, user_id) -> dict:
    """按 user_id 取用户，取不到视为未认证。"""
    try:
        uid = int(user_id)
    except (TypeError, ValueError) as exc:
        raise AuthError("需要有效的 user_id") from exc
    user = user_repository.get_by_id(session, uid)
    if not user:
        raise AuthError("用户不存在")
    return user


def require_admin(session, user_id) -> dict:
    user = require_user(session, user_id)
    if user["role"] != "admin":
        raise PermissionDenied("需要管理员权限")
    return user


def ensure_owner_or_admin(session, user_id, owner_id) -> dict:
    """本人或管理员才可操作。"""
    user = require_user(session, user_id)
    if user["role"] != "admin" and int(user["id"]) != int(owner_id):
        raise PermissionDenied("无权操作该预约")
    return user


def list_users(session) -> list[dict]:
    return user_repository.list_all(session)


def get_user_or_404(session, user_id) -> dict:
    user = user_repository.get_by_id(session, user_id)
    if not user:
        raise NotFound("用户不存在")
    return user
