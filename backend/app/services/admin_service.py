"""管理后台服务层：用户管理、日志查询、系统配置管理。"""

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.core.security import hash_password
from app.models.user import User
from app.models.file import FileItem
from app.models.share import Share
from app.models.log import SystemLog
from app.schemas.admin import (
    SystemConfigUpdate,
    UserQuotaUpdate,
    UserStatusUpdate,
    AdminUserCreate,
)


# =============================================================================
#  用户管理
# =============================================================================


def list_users(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    role: str = "",
    is_active: bool | None = None,
) -> dict[str, Any]:
    """列出所有用户，支持模糊搜索、角色过滤、状态过滤和分页。"""
    query = db.query(User)

    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            User.username.ilike(like_pattern) | User.email.ilike(like_pattern)
        )
    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total = query.count()
    users = (
        query.order_by(User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    user_list = [_serialize_user(u) for u in users]

    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": user_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


def get_user_detail(db: Session, user_id: int) -> dict[str, Any]:
    """获取单个用户的详细信息，包含存储统计。"""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundException("用户不存在")

    file_count = db.query(FileItem).filter(
        FileItem.user_id == user_id, FileItem.is_deleted == False
    ).count()
    share_count = db.query(Share).filter(Share.user_id == user_id).count()

    user_data = _serialize_user(user)
    user_data["file_count"] = file_count
    user_data["share_count"] = share_count

    return {"code": 0, "message": "success", "data": user_data}


def create_user(db: Session, admin_user: User, data: AdminUserCreate) -> dict[str, Any]:
    """管理员手动创建用户。"""
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise BadRequestException("用户名已存在")

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        email=data.email,
        role=data.role,
        storage_quota=data.storage_quota,
        storage_used=0,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 记录操作日志
    _write_log(
        db,
        user_id=admin_user.id,
        action="admin_create_user",
        detail=f"管理员 {admin_user.username} 创建了用户 {user.username} (id={user.id})",
    )

    return {"code": 0, "message": "用户创建成功", "data": _serialize_user(user)}


def update_user_quota(
    db: Session, admin_user: User, user_id: int, data: UserQuotaUpdate
) -> dict[str, Any]:
    """更新用户的存储配额。"""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundException("用户不存在")

    if data.storage_quota < 0:
        raise BadRequestException("存储配额不能为负数")

    old_quota = user.storage_quota
    user.storage_quota = data.storage_quota
    db.commit()
    db.refresh(user)

    _write_log(
        db,
        user_id=admin_user.id,
        action="admin_update_quota",
        detail=(
            f"管理员 {admin_user.username} 将用户 {user.username} "
            f"配额从 {old_quota} 修改为 {data.storage_quota}"
        ),
    )

    return {"code": 0, "message": "配额更新成功", "data": _serialize_user(user)}


def update_user_status(
    db: Session, admin_user: User, user_id: int, data: UserStatusUpdate
) -> dict[str, Any]:
    """启用或禁用用户账号。不允许管理员禁用自己。"""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundException("用户不存在")

    if user.id == admin_user.id:
        raise ForbiddenException("不能修改自己的账号状态")

    if user.role == "admin" and not data.is_active:
        raise ForbiddenException("不能禁用其他管理员账号")

    old_status = user.is_active
    user.is_active = data.is_active
    db.commit()
    db.refresh(user)

    action_label = "启用" if data.is_active else "禁用"
    _write_log(
        db,
        user_id=admin_user.id,
        action="admin_update_status",
        detail=(
            f"管理员 {admin_user.username} {action_label}了用户 "
            f"{user.username} (id={user.id})"
        ),
    )

    return {
        "code": 0,
        "message": f"用户已{action_label}",
        "data": _serialize_user(user),
    }


def delete_user(db: Session, admin_user: User, user_id: int) -> dict[str, Any]:
    """删除用户及其所有文件和分享记录。"""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundException("用户不存在")

    if user.id == admin_user.id:
        raise ForbiddenException("不能删除自己的账号")

    if user.role == "admin":
        raise ForbiddenException("不能删除管理员账号")

    username = user.username

    # 级联删除：文件、分享、日志
    db.query(Share).filter(Share.user_id == user_id).delete()
    db.query(SystemLog).filter(SystemLog.user_id == user_id).delete()
    db.query(FileItem).filter(FileItem.user_id == user_id).delete()
    db.delete(user)
    db.commit()

    _write_log(
        db,
        user_id=admin_user.id,
        action="admin_delete_user",
        detail=f"管理员 {admin_user.username} 删除了用户 {username} (id={user_id})",
    )

    return {"code": 0, "message": "用户已删除", "data": None}


# =============================================================================
#  日志查询
# =============================================================================


def list_logs(
    db: Session,
    page: int = 1,
    page_size: int = 30,
    user_id: int | None = None,
    action: str = "",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    """查询系统操作日志，支持多维度过滤和分页。"""
    query = db.query(SystemLog)

    if user_id is not None:
        query = query.filter(SystemLog.user_id == user_id)
    if action:
        query = query.filter(SystemLog.action == action)
    if start_time is not None:
        query = query.filter(SystemLog.created_at >= start_time)
    if end_time is not None:
        query = query.filter(SystemLog.created_at <= end_time)

    total = query.count()
    logs = (
        query.order_by(desc(SystemLog.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    log_list = [
        {
            "id": log.id,
            "user_id": log.user_id,
            "username": log.user.username if log.user else None,
            "action": log.action,
            "detail": log.detail,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": log_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


def get_log_actions(db: Session) -> dict[str, Any]:
    """获取所有已记录的日志动作类型列表（用于筛选下拉）。"""
    actions = (
        db.query(SystemLog.action)
        .distinct()
        .order_by(SystemLog.action)
        .all()
    )
    action_list = [row[0] for row in actions]

    return {"code": 0, "message": "success", "data": action_list}


# =============================================================================
#  系统配置管理
# =============================================================================

_ENV_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".env",
)


def get_system_config() -> dict[str, Any]:
    """获取当前系统配置。"""
    return {
        "code": 0,
        "message": "success",
        "data": {
            "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB,
            "allowed_extensions": settings.ALLOWED_EXTENSIONS,
            "allow_registration": settings.ALLOW_REGISTRATION,
        },
    }


def update_system_config(
    db: Session, admin_user: User, data: SystemConfigUpdate
) -> dict[str, Any]:
    """更新系统配置，持久化到 .env 文件并更新运行时 settings。"""
    changes: list[str] = []

    if data.max_upload_size_mb is not None:
        if data.max_upload_size_mb <= 0:
            raise BadRequestException("最大上传大小必须大于 0")
        old_val = settings.MAX_UPLOAD_SIZE_MB
        settings.MAX_UPLOAD_SIZE_MB = data.max_upload_size_mb
        _update_env_key("MAX_UPLOAD_SIZE_MB", str(data.max_upload_size_mb))
        changes.append(f"最大上传大小: {old_val}MB -> {data.max_upload_size_mb}MB")

    if data.allowed_extensions is not None:
        old_val = settings.ALLOWED_EXTENSIONS
        settings.ALLOWED_EXTENSIONS = data.allowed_extensions
        _update_env_key("ALLOWED_EXTENSIONS", data.allowed_extensions)
        changes.append("允许的文件扩展名已更新")

    if data.allow_registration is not None:
        old_val = settings.ALLOW_REGISTRATION
        settings.ALLOW_REGISTRATION = data.allow_registration
        _update_env_key("ALLOW_REGISTRATION", str(data.allow_registration).lower())
        changes.append(f"开放注册: {old_val} -> {data.allow_registration}")

    change_summary = "; ".join(changes) if changes else "无变更"

    _write_log(
        db,
        user_id=admin_user.id,
        action="admin_update_config",
        detail=f"管理员 {admin_user.username} 更新了系统配置: {change_summary}",
    )

    return {
        "code": 0,
        "message": "配置更新成功",
        "data": {
            "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB,
            "allowed_extensions": settings.ALLOWED_EXTENSIONS,
            "allow_registration": settings.ALLOW_REGISTRATION,
        },
    }


# =============================================================================
#  系统统计
# =============================================================================


def get_system_stats(db: Session) -> dict[str, Any]:
    """获取系统整体统计信息。"""
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_files = db.query(FileItem).filter(FileItem.is_deleted == False).count()
    total_shares = db.query(Share).count()
    total_storage_used = (
        db.query(User).with_entities(User.storage_used).all()
    )
    total_storage = sum(row[0] for row in total_storage_used)
    total_logs = db.query(SystemLog).count()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "total_users": total_users,
            "active_users": active_users,
            "total_files": total_files,
            "total_shares": total_shares,
            "total_storage_used": total_storage,
            "total_logs": total_logs,
        },
    }


# =============================================================================
#  数据库维护
# =============================================================================


def vacuum_database(db: Session, admin_user: User) -> dict[str, Any]:
    """清理已标记删除的文件并回收数据库空间（仅 SQLite 有效）。"""
    # 清理软删除超过 30 天的文件记录
    cutoff = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    deleted_files = (
        db.query(FileItem)
        .filter(
            FileItem.is_deleted == True,
            FileItem.deleted_at.isnot(None),
            FileItem.deleted_at < cutoff,
        )
        .all()
    )
    count = len(deleted_files)
    for f in deleted_files:
        # 清理关联的分享记录
        db.query(Share).filter(Share.file_id == f.id).delete()
        db.delete(f)
    db.commit()

    # SQLite VACUUM
    if "sqlite" in settings.DATABASE_URL:
        from sqlalchemy import text
        db.execute(text("VACUUM"))

    _write_log(
        db,
        user_id=admin_user.id,
        action="admin_vacuum",
        detail=f"管理员 {admin_user.username} 执行了数据库清理，清除了 {count} 条已删除文件记录",
    )

    return {"code": 0, "message": f"数据库清理完成，清除了 {count} 条记录", "data": None}


# =============================================================================
#  内部辅助函数
# =============================================================================


def _serialize_user(user: User) -> dict[str, Any]:
    """将 User ORM 对象序列化为字典。"""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "storage_quota": user.storage_quota,
        "storage_used": user.storage_used,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _write_log(
    db: Session,
    user_id: int,
    action: str,
    detail: str = "",
    ip_address: str = "",
) -> None:
    """写入系统操作日志。"""
    log_entry = SystemLog(
        user_id=user_id,
        action=action,
        detail=detail,
        ip_address=ip_address,
    )
    db.add(log_entry)
    db.commit()


def _update_env_key(key: str, value: str) -> None:
    """更新 .env 文件中指定键的值；如果键不存在则追加。"""
    if not os.path.exists(_ENV_FILE_PATH):
        # .env 不存在则创建
        with open(_ENV_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")
        return

    with open(_ENV_FILE_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} "):
            lines[i] = f"{key}={value}\n"
            updated = True
            break

    if not updated:
        lines.append(f"{key}={value}\n")

    with open(_ENV_FILE_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)
