"""分享服务层 —— 创建分享、校验提取码、追踪浏览次数、管理分享。"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.models.file import FileItem
from app.models.share import Share
from app.schemas.common import ApiResponse
from app.schemas.file import FileOut
from app.schemas.share import ShareAccess, ShareCreate, ShareOut


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _generate_share_code(length: int = 8) -> str:
    """生成唯一的分享码。"""
    return secrets.token_urlsafe(length)[:length]


def _generate_unique_code(db: Session, length: int = 8) -> str:
    """生成在库中不重复的分享码，最多重试 10 次。"""
    for _ in range(10):
        code = _generate_share_code(length)
        if db.query(Share).filter(Share.code == code).first() is None:
            return code
    # 极端情况下拉长码长再试
    code = _generate_share_code(16)
    if db.query(Share).filter(Share.code == code).first() is None:
        return code
    raise BadRequestException("分享码生成失败，请重试")


def _normalize_expire(expire_hours: int) -> datetime | None:
    """将过期小时数转为绝对 UTC 时间；0 表示永不过期。"""
    if expire_hours <= 0:
        return None
    return datetime.now(timezone.utc) + timedelta(hours=expire_hours)


def _is_expired(share: Share) -> bool:
    """判断分享是否已过期。"""
    if share.expire_at is None:
        return False
    return datetime.now(timezone.utc) >= share.expire_at


# ---------------------------------------------------------------------------
# 分享服务类
# ---------------------------------------------------------------------------

class ShareService:
    """分享业务逻辑封装。"""

    # ---- 创建分享 -----------------------------------------------------------

    @staticmethod
    def create_share(db: Session, user_id: int, data: ShareCreate) -> ShareOut:
        """为当前用户创建一个文件/文件夹分享链接。

        Args:
            db: 数据库会话。
            user_id: 当前登录用户 ID。
            data: 分享创建参数（file_id, password, expire_hours）。

        Returns:
            ShareOut: 创建成功的分享信息。

        Raises:
            NotFoundException: 文件不存在或已删除。
            ForbiddenException: 文件不属于当前用户。
        """
        file_item = (
            db.query(FileItem)
            .filter(FileItem.id == data.file_id, FileItem.is_deleted == False)
            .first()
        )
        if file_item is None:
            raise NotFoundException("文件不存在或已被删除")
        if file_item.user_id != user_id:
            raise ForbiddenException("只能分享自己的文件")

        code = _generate_unique_code(db)
        expire_at = _normalize_expire(data.expire_hours)

        share = Share(
            file_id=data.file_id,
            user_id=user_id,
            code=code,
            password=data.password or "",
            expire_at=expire_at,
            view_count=0,
        )
        db.add(share)
        db.commit()
        db.refresh(share)

        return ShareOut.model_validate(share)

    # ---- 通过提取码获取分享（内部公用） ---------------------------------------

    @staticmethod
    def _get_share_by_code(db: Session, code: str) -> Share:
        """根据分享码获取分享记录，校验是否存在及过期。

        Raises:
            NotFoundException: 分享码无效。
            BadRequestException: 分享已过期。
        """
        share = db.query(Share).filter(Share.code == code).first()
        if share is None:
            raise NotFoundException("分享链接不存在或已失效")
        if _is_expired(share):
            raise BadRequestException("分享链接已过期")
        return share

    # ---- 校验提取码并返回文件信息 -------------------------------------------

    @staticmethod
    def validate_access(db: Session, data: ShareAccess) -> FileOut:
        """校验提取码并返回分享的文件信息，同时增加浏览次数。

        Args:
            db: 数据库会话。
            data: 分享码 + 提取密码。

        Returns:
            FileOut: 分享的文件信息。

        Raises:
            NotFoundException: 分享链接不存在。
            BadRequestException: 分享已过期或提取码错误。
        """
        share = ShareService._get_share_by_code(db, data.code)

        # 校验提取码（若分享设置了密码）
        if share.password and share.password != data.password:
            raise BadRequestException("提取码错误")

        # 校验文件仍然存在
        file_item = (
            db.query(FileItem)
            .filter(FileItem.id == share.file_id, FileItem.is_deleted == False)
            .first()
        )
        if file_item is None:
            raise NotFoundException("分享的文件已被删除")

        # 增加浏览次数
        share.view_count += 1
        db.commit()
        db.refresh(share)

        return FileOut.model_validate(file_item)

    # ---- 获取分享信息（不增加浏览次数）----------------------------------------

    @staticmethod
    def get_share_info(db: Session, code: str) -> ShareOut:
        """根据分享码获取分享的公开信息（不增加浏览次数）。

        Args:
            db: 数据库会话。
            code: 分享码。

        Returns:
            ShareOut: 分享信息（不含敏感数据）。

        Raises:
            NotFoundException: 分享链接不存在。
            BadRequestException: 分享已过期。
        """
        share = ShareService._get_share_by_code(db, code)

        # 检查文件是否存在
        file_item = (
            db.query(FileItem)
            .filter(FileItem.id == share.file_id, FileItem.is_deleted == False)
            .first()
        )
        if file_item is None:
            raise NotFoundException("分享的文件已被删除")

        return ShareOut.model_validate(share)

    # ---- 列出当前用户的所有分享 ----------------------------------------------

    @staticmethod
    def list_my_shares(
        db: Session,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """分页列出当前用户创建的所有分享。

        Args:
            db: 数据库会话。
            user_id: 当前用户 ID。
            page: 页码（从 1 开始）。
            page_size: 每页数量。

        Returns:
            dict: {"items": [...], "total": int, "page": int, "page_size": int}
        """
        query = (
            db.query(Share)
            .filter(Share.user_id == user_id)
            .order_by(Share.created_at.desc())
        )
        total = query.count()
        shares = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "items": [ShareOut.model_validate(s) for s in shares],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ---- 列出某个文件的所有分享（管理用）--------------------------------------

    @staticmethod
    def list_file_shares(
        db: Session,
        user_id: int,
        file_id: int,
    ) -> list[ShareOut]:
        """列出指定文件的所有分享（仅限文件拥有者）。

        Args:
            db: 数据库会话。
            user_id: 当前用户 ID。
            file_id: 文件 ID。

        Returns:
            list[ShareOut]: 该文件的所有分享信息。
        """
        file_item = (
            db.query(FileItem)
            .filter(FileItem.id == file_id, FileItem.is_deleted == False)
            .first()
        )
        if file_item is None:
            raise NotFoundException("文件不存在或已被删除")
        if file_item.user_id != user_id:
            raise ForbiddenException("只能查看自己文件的分")

        shares = (
            db.query(Share)
            .filter(Share.file_id == file_id, Share.user_id == user_id)
            .order_by(Share.created_at.desc())
            .all()
        )
        return [ShareOut.model_validate(s) for s in shares]

    # ---- 删除分享 -----------------------------------------------------------

    @staticmethod
    def delete_share(db: Session, user_id: int, share_id: int) -> None:
        """删除一个分享链接（仅限分享创建者或管理员）。

        Args:
            db: 数据库会话。
            user_id: 当前用户 ID。
            share_id: 要删除的分享 ID。

        Raises:
            NotFoundException: 分享不存在。
            ForbiddenException: 无权限删除（非创建者且非管理员）。
        """
        share = db.query(Share).filter(Share.id == share_id).first()
        if share is None:
            raise NotFoundException("分享不存在")

        # 权限检查：只能删除自己的分享（管理员另外在 API 层判断）
        if share.user_id != user_id:
            raise ForbiddenException("只能删除自己创建的分享")

        db.delete(share)
        db.commit()

    # ---- 删除文件相关的所有分享（内部调用）-------------------------------------

    @staticmethod
    def delete_file_shares(db: Session, file_id: int) -> int:
        """删除指定文件的所有分享记录（文件删除时联动调用）。

        Args:
            db: 数据库会话。
            file_id: 文件 ID。

        Returns:
            int: 被删除的分享数量。
        """
        count = (
            db.query(Share)
            .filter(Share.file_id == file_id)
            .delete(synchronize_session="fetch")
        )
        db.commit()
        return count

    # ---- 重新生成提取码 ------------------------------------------------------

    @staticmethod
    def regenerate_code(db: Session, user_id: int, share_id: int) -> ShareOut:
        """重新生成分享码（仅限创建者）。

        Args:
            db: 数据库会话。
            user_id: 当前用户 ID。
            share_id: 分享 ID。

        Returns:
            ShareOut: 更新后的分享信息。
        """
        share = db.query(Share).filter(Share.id == share_id).first()
        if share is None:
            raise NotFoundException("分享不存在")
        if share.user_id != user_id:
            raise ForbiddenException("只能修改自己创建的分享")

        share.code = _generate_unique_code(db)
        db.commit()
        db.refresh(share)

        return ShareOut.model_validate(share)

    # ---- 修改提取密码 --------------------------------------------------------

    @staticmethod
    def update_password(
        db: Session,
        user_id: int,
        share_id: int,
        new_password: str,
    ) -> ShareOut:
        """修改分享提取密码（仅限创建者）。

        Args:
            db: 数据库会话。
            user_id: 当前用户 ID。
            share_id: 分享 ID。
            new_password: 新密码，空字符串表示取消密码。

        Returns:
            ShareOut: 更新后的分享信息。
        """
        share = db.query(Share).filter(Share.id == share_id).first()
        if share is None:
            raise NotFoundException("分享不存在")
        if share.user_id != user_id:
            raise ForbiddenException("只能修改自己创建的分享")

        share.password = new_password or ""
        db.commit()
        db.refresh(share)

        return ShareOut.model_validate(share)

    # ---- 修改过期时间 --------------------------------------------------------

    @staticmethod
    def update_expiry(
        db: Session,
        user_id: int,
        share_id: int,
        expire_hours: int,
    ) -> ShareOut:
        """修改分享过期时间（仅限创建者）。

        Args:
            db: 数据库会话。
            user_id: 当前用户 ID。
            share_id: 分享 ID。
            expire_hours: 新的过期小时数，0 表示永不过期。

        Returns:
            ShareOut: 更新后的分享信息。
        """
        share = db.query(Share).filter(Share.id == share_id).first()
        if share is None:
            raise NotFoundException("分享不存在")
        if share.user_id != user_id:
            raise ForbiddenException("只能修改自己创建的分享")

        share.expire_at = _normalize_expire(expire_hours)
        db.commit()
        db.refresh(share)

        return ShareOut.model_validate(share)

    # ---- 后台清理过期分享 ----------------------------------------------------

    @staticmethod
    def clean_expired_shares(db: Session) -> int:
        """删除所有已过期的分享记录（可配合定时任务调用）。

        Args:
            db: 数据库会话。

        Returns:
            int: 被清理的分享数量。
        """
        now = datetime.now(timezone.utc)
        count = (
            db.query(Share)
            .filter(Share.expire_at.isnot(None), Share.expire_at <= now)
            .delete(synchronize_session="fetch")
        )
        db.commit()
        return count


# ---------------------------------------------------------------------------
# 单例引用（便于 API 层直接调用）
# ---------------------------------------------------------------------------
share_service = ShareService()
