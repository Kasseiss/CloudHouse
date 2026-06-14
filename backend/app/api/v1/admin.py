"""管理后台 API 路由：用户管理、配额/状态管理、系统日志、系统配置。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Query
from sqlalchemy import desc

from app.api.v1.dependencies import AdminUser, CurrentUser, DbSession
from app.core.config import settings
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.core.security import hash_password
from app.models.file import FileItem
from app.models.log import SystemLog
from app.models.share import Share
from app.models.user import User
from app.schemas.admin import (
    AdminUserCreate,
    LogOut,
    SystemConfigOut,
    SystemConfigUpdate,
    UserQuotaUpdate,
    UserStatusUpdate,
)
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.user import UserOut

router = APIRouter()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _log_action(db: DbSession, user_id: int | None, action: str, detail: str, ip_address: str = "") -> None:
    """写入一条系统操作日志。"""
    log_entry = SystemLog(
        user_id=user_id,
        action=action,
        detail=detail,
        ip_address=ip_address,
    )
    db.add(log_entry)
    db.commit()


# ===================================================================
# 用户 CRUD
# ===================================================================

@router.get("/users", response_model=ApiResponse[PaginatedData[UserOut]])
def list_users(
    db: DbSession,
    _admin: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="按用户名或邮箱模糊搜索"),
):
    """获取用户列表（管理员）。"""
    query = db.query(User)
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            User.username.ilike(like_pattern) | User.email.ilike(like_pattern)
        )

    total = query.count()
    items = (
        query.order_by(desc(User.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ApiResponse(
        data=PaginatedData(
            items=[UserOut.model_validate(u) for u in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/users/{user_id}", response_model=ApiResponse[UserOut])
def get_user(
    user_id: int,
    db: DbSession,
    _admin: AdminUser,
):
    """获取单个用户详情。"""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundException("用户不存在")
    return ApiResponse(data=UserOut.model_validate(user))


@router.post("/users", response_model=ApiResponse[UserOut])
def create_user(
    body: AdminUserCreate,
    db: DbSession,
    _admin: AdminUser,
):
    """管理员创建新用户。"""
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise BadRequestException("用户名已存在")

    if body.role not in ("user", "admin"):
        raise BadRequestException("角色只能为 user 或 admin")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        email=body.email,
        role=body.role,
        storage_quota=body.storage_quota,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _log_action(db, _admin.id, "create_user", f"管理员创建用户: {user.username}")
    return ApiResponse(data=UserOut.model_validate(user))


@router.put("/users/{user_id}", response_model=ApiResponse[UserOut])
def update_user(
    user_id: int,
    body: AdminUserCreate,
    db: DbSession,
    _admin: AdminUser,
):
    """管理员编辑用户信息。"""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundException("用户不存在")

    if user.id == _admin.id and body.role != "admin":
        raise BadRequestException("不能取消自己的管理员权限")

    # 检查用户名是否被其他用户占用
    existing = db.query(User).filter(
        User.username == body.username, User.id != user_id
    ).first()
    if existing:
        raise BadRequestException("用户名已被其他用户占用")

    user.username = body.username
    user.email = body.email
    user.role = body.role
    user.storage_quota = body.storage_quota
    if body.password:
        user.password_hash = hash_password(body.password)

    db.commit()
    db.refresh(user)

    _log_action(db, _admin.id, "update_user", f"管理员编辑用户: {user.username}")
    return ApiResponse(data=UserOut.model_validate(user))


@router.delete("/users/{user_id}", response_model=ApiResponse)
def delete_user(
    user_id: int,
    db: DbSession,
    admin: AdminUser,
):
    """管理员删除用户（同时清理该用户的文件、分享、日志）。"""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundException("用户不存在")

    if user.id == admin.id:
        raise BadRequestException("不能删除自己的账号")

    # 逻辑删除该用户的文件（并非物理删除服务器文件）
    db.query(FileItem).filter(FileItem.user_id == user_id).delete()
    # 删除该用户的分享记录
    db.query(Share).filter(Share.user_id == user_id).delete()
    # 删除该用户的日志
    db.query(SystemLog).filter(SystemLog.user_id == user_id).delete()
    # 最后删除用户
    db.delete(user)
    db.commit()

    _log_action(db, admin.id, "delete_user", f"管理员删除用户: {user.username}")
    return ApiResponse(message="用户已删除")


# ===================================================================
# 配额 / 状态管理
# ===================================================================

@router.put("/users/{user_id}/quota", response_model=ApiResponse[UserOut])
def update_user_quota(
    user_id: int,
    body: UserQuotaUpdate,
    db: DbSession,
    admin: AdminUser,
):
    """修改用户存储配额（单位：字节）。0 表示不限。"""
    if body.storage_quota < 0:
        raise BadRequestException("存储配额不能为负数")

    user = db.get(User, user_id)
    if user is None:
        raise NotFoundException("用户不存在")

    old_quota = user.storage_quota
    user.storage_quota = body.storage_quota
    db.commit()
    db.refresh(user)

    _log_action(
        db,
        admin.id,
        "update_quota",
        f"修改用户 {user.username} 配额: {old_quota} -> {body.storage_quota}",
    )
    return ApiResponse(data=UserOut.model_validate(user))


@router.put("/users/{user_id}/status", response_model=ApiResponse[UserOut])
def update_user_status(
    user_id: int,
    body: UserStatusUpdate,
    db: DbSession,
    admin: AdminUser,
):
    """启用 / 禁用用户。"""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundException("用户不存在")

    if user.id == admin.id:
        raise BadRequestException("不能禁用自己的账号")

    user.is_active = body.is_active
    db.commit()
    db.refresh(user)

    status_text = "启用" if body.is_active else "禁用"
    _log_action(db, admin.id, "update_status", f"{status_text}用户: {user.username}")
    return ApiResponse(data=UserOut.model_validate(user))


# ===================================================================
# 系统日志
# ===================================================================

@router.get("/logs", response_model=ApiResponse[PaginatedData[LogOut]])
def list_system_logs(
    db: DbSession,
    _admin: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str = Query("", description="按操作类型过滤"),
    user_id: int | None = Query(None, description="按用户 ID 过滤"),
    keyword: str = Query("", description="按详情模糊搜索"),
):
    """查询系统操作日志（管理员）。"""
    query = db.query(SystemLog)

    if action:
        query = query.filter(SystemLog.action == action)
    if user_id is not None:
        query = query.filter(SystemLog.user_id == user_id)
    if keyword:
        query = query.filter(SystemLog.detail.ilike(f"%{keyword}%"))

    total = query.count()
    items = (
        query.order_by(desc(SystemLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ApiResponse(
        data=PaginatedData(
            items=[LogOut.model_validate(log) for log in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


# ===================================================================
# 系统配置
# ===================================================================

@router.get("/config", response_model=ApiResponse[SystemConfigOut])
def get_system_config(_admin: AdminUser):
    """获取当前系统配置。"""
    return ApiResponse(
        data=SystemConfigOut(
            max_upload_size_mb=settings.MAX_UPLOAD_SIZE_MB,
            allowed_extensions=settings.ALLOWED_EXTENSIONS,
            allow_registration=settings.ALLOW_REGISTRATION,
        )
    )


@router.put("/config", response_model=ApiResponse[SystemConfigOut])
def update_system_config(
    body: SystemConfigUpdate,
    db: DbSession,
    admin: AdminUser,
):
    """更新系统配置（运行时生效，服务重启后部分配置会还原为 .env 文件的值）。"""
    if body.max_upload_size_mb is not None:
        if body.max_upload_size_mb <= 0:
            raise BadRequestException("上传大小限制必须大于 0")
        settings.MAX_UPLOAD_SIZE_MB = body.max_upload_size_mb

    if body.allowed_extensions is not None:
        settings.ALLOWED_EXTENSIONS = body.allowed_extensions

    if body.allow_registration is not None:
        settings.ALLOW_REGISTRATION = body.allow_registration

    _log_action(db, admin.id, "update_config", "管理员更新系统配置")

    return ApiResponse(
        data=SystemConfigOut(
            max_upload_size_mb=settings.MAX_UPLOAD_SIZE_MB,
            allowed_extensions=settings.ALLOWED_EXTENSIONS,
            allow_registration=settings.ALLOW_REGISTRATION,
        )
    )


# ===================================================================
# 仪表盘统计
# ===================================================================

@router.post("/trash/cleanup", response_model=ApiResponse)
def force_trash_cleanup(
    db: DbSession,
    admin: AdminUser,
    days: int = 30,
):
    """管理员手动触发回收站清理（删除超过 N 天的回收站文件）。"""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    from app.models.file import FileItem
    from app.core.config import settings
    from pathlib import Path

    old_items = (
        db.query(FileItem)
        .filter(FileItem.is_deleted == True, FileItem.deleted_at <= cutoff)
        .all()
    )
    count = 0
    freed = 0
    for item in old_items:
        if item.storage_path and not item.is_dir:
            try:
                (Path(settings.UPLOAD_DIR) / item.storage_path).unlink(missing_ok=True)
                freed += item.file_size
            except OSError:
                pass
        db.delete(item)
        count += 1

    _log_action(db, admin.id, "trash_cleanup", f"手动清理回收站: {count} 个文件, 释放 {freed} bytes")
    db.commit()
    return ApiResponse(data={"cleaned": count, "freed_bytes": freed, "older_than_days": days})


@router.get("/dashboard", response_model=ApiResponse)
def get_dashboard_stats(
    db: DbSession,
    _admin: AdminUser,
):
    """获取管理后台仪表盘统计数据。"""
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()  # noqa: E712
    total_files = db.query(FileItem).filter(FileItem.is_dir == False, FileItem.is_deleted == False).count()  # noqa: E712
    total_shares = db.query(Share).count()
    total_storage_used = db.query(FileItem).filter(FileItem.is_deleted == False).with_entities(  # noqa: E712
        FileItem.file_size
    ).all()
    storage_sum = sum(row[0] for row in total_storage_used)

    # 最近 7 天新增用户
    from datetime import timedelta

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    new_users_7d = db.query(User).filter(User.created_at >= seven_days_ago).count()

    return ApiResponse(
        data={
            "total_users": total_users,
            "active_users": active_users,
            "disabled_users": total_users - active_users,
            "total_files": total_files,
            "total_shares": total_shares,
            "storage_used_bytes": storage_sum,
            "storage_used_display": _format_bytes(storage_sum),
            "new_users_last_7_days": new_users_7d,
        }
    )


def _format_bytes(size: int) -> str:
    """将字节数转换为可读的字符串。"""
    if size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    fsize = float(size)
    while fsize >= 1024 and i < len(units) - 1:
        fsize /= 1024
        i += 1
    return f"{fsize:.2f} {units[i]}"
