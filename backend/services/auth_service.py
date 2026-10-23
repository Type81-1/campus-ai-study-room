"""登录、会话与身份校验（用户模块）。

v2.1 起身份不再由前端传 `user_id` 决定：
- 登录成功后签发随机令牌，数据库只存 SHA-256 摘要与过期时间；
- 每个请求由 `Authorization: Bearer <token>` 还原身份；
- 服务层接收已解析的 `actor` 字典，不再接收可被伪造的 user_id。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..config import config
from ..errors import AuthError, PermissionDenied, ValidationError
from ..repositories import session_repository, user_repository
from ..security import hash_password, is_hashed, new_token, token_digest, verify_password


def _now() -> datetime:
    return datetime.now()


def _text(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def login(db, username, password, cfg=config) -> dict:
    if not username or not password:
        raise ValidationError("缺少字段：username, password")

    with db.session(write=True) as session:
        user = user_repository.get_by_username_with_secret(session, username)
        if not user or not verify_password(password, user["password"]):
            raise AuthError("账号或密码错误")

        # 存量明文口令：首次登录时自动升级为哈希
        if not is_hashed(user["password"]):
            user_repository.update_password(session, user["id"], hash_password(password))

        session_repository.purge_expired(session, _text(_now()))
        token = new_token()
        expires_at = _now() + timedelta(days=cfg.session_ttl_days)
        session_repository.create(session, user["id"], token_digest(token), _text(expires_at))

        public = {key: value for key, value in user.items() if key != "password"}

    return {"token": token, "expires_at": _text(expires_at), "user": public}


def authenticate(db, token, cfg=config) -> dict:
    """令牌 → 当前用户；无效或过期抛 AuthError。"""
    if not token:
        raise AuthError("请先登录")
    digest = token_digest(token)
    # 只读事务：鉴权是每个请求都会走的路径，不能在这里抢写锁
    # （SQLite 的写事务是库级串行，会把所有并发请求排队）。
    # 令牌有效期是从登录时刻起算的绝对有效期，因此无需刷新 last_seen_at。
    with db.session() as session:
        user = session_repository.find_user_by_token(session, digest, _text(_now()))
    if not user:
        raise AuthError("登录已过期，请重新登录")
    user.pop("expires_at", None)
    user.pop("session_id", None)
    return user


def logout(db, token) -> str:
    if not token:
        return "已退出登录"
    with db.session(write=True) as session:
        session_repository.delete(session, token_digest(token))
    return "已退出登录"


def require_user(actor: dict | None) -> dict:
    if not actor:
        raise AuthError("请先登录")
    return actor


def require_admin(actor: dict | None) -> dict:
    actor = require_user(actor)
    if actor.get("role") != "admin":
        raise PermissionDenied("需要管理员权限")
    return actor


def ensure_owner_or_admin(actor: dict | None, owner_id) -> dict:
    actor = require_user(actor)
    if actor["role"] != "admin" and int(actor["id"]) != int(owner_id):
        raise PermissionDenied("无权操作该预约")
    return actor


def list_users(session) -> list[dict]:
    return user_repository.list_all(session)


def migrate_plaintext_passwords(db) -> int:
    """把库里遗留的明文口令一次性替换为 PBKDF2 哈希，返回迁移条数。"""
    with db.session(write=True) as session:
        rows = session.query_all("SELECT id, password FROM users")
        migrated = 0
        for row in rows:
            if not is_hashed(row["password"]):
                user_repository.update_password(session, row["id"], hash_password(row["password"]))
                migrated += 1
    return migrated
