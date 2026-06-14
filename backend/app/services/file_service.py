"""文件服务：CRUD、配额管理、存储追踪。"""

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
    QuotaExceededException,
)
from app.models.file import FileItem
from app.models.log import SystemLog
from app.models.user import User


class FileService:
    """文件业务逻辑，所有方法需要传入 SQLAlchemy Session。"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _get_file(self, file_id: int, user_id: int | None = None) -> FileItem:
        """获取文件记录，可选的归属校验。"""
        file = self.db.get(FileItem, file_id)
        if file is None or file.is_deleted:
            raise NotFoundException("文件或目录不存在")
        if user_id is not None and file.user_id != user_id:
            raise ForbiddenException("无权操作此文件或目录")
        return file

    def _check_name_conflict(
        self, name: str, parent_id: int | None, user_id: int, exclude_id: int | None = None
    ) -> None:
        """检查同名文件/文件夹是否已存在。"""
        q = self.db.query(FileItem).filter(
            FileItem.user_id == user_id,
            FileItem.name == name,
            FileItem.parent_id == parent_id,
            FileItem.is_deleted == False,  # noqa: E712
        )
        if exclude_id is not None:
            q = q.filter(FileItem.id != exclude_id)
        if q.first() is not None:
            raise BadRequestException("当前目录下已存在同名文件或文件夹")

    def _resolve_upload_storage_path(self, filename: str, user_id: int) -> Path:
        """为上传文件生成唯一的服务器存储路径，按日期 / 用户分目录。"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dir_path = Path(settings.UPLOAD_DIR) / today / str(user_id)
        dir_path.mkdir(parents=True, exist_ok=True)
        suffix = "".join(Path(filename).suffixes)
        unique_name = f"{uuid.uuid4().hex}{suffix}"
        return dir_path / unique_name

    def _validate_extension(self, filename: str) -> str:
        """校验扩展名是否在允许列表中，返回小写后缀。"""
        suffix = Path(filename).suffix.lower()
        # 组合后缀处理：.tar.gz 等
        if filename.lower().endswith(".tar.gz"):
            suffix = ".tar.gz"
        allowed = settings.allowed_extensions_set
        if suffix.lstrip(".") not in allowed and suffix not in allowed:
            raise BadRequestException(f"不支持的文件类型: {suffix}")
        return suffix

    @staticmethod
    def _infer_mime_type(suffix: str) -> str:
        """根据扩展名推断 MIME 类型。"""
        mapping = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".ppt": "application/vnd.ms-powerpoint",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".txt": "text/plain",
            ".zip": "application/zip",
            ".rar": "application/vnd.rar",
            ".7z": "application/x-7z-compressed",
            ".tar.gz": "application/gzip",
            ".mp4": "video/mp4",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".flac": "audio/flac",
        }
        return mapping.get(suffix, "application/octet-stream")

    def _update_storage_used(self, user: User, delta: int) -> None:
        """安全地更新用户已用空间，并校验配额。"""
        new_used = user.storage_used + delta
        if new_used < 0:
            new_used = 0
        if user.storage_quota > 0 and new_used > user.storage_quota:
            raise QuotaExceededException("存储空间不足，无法完成操作")
        user.storage_used = new_used
        self.db.add(user)

    # ------------------------------------------------------------------
    # 日志记录
    # ------------------------------------------------------------------

    def _log(self, user_id: int, action: str, detail: str = "") -> None:
        log = SystemLog(user_id=user_id, action=action, detail=detail)
        self.db.add(log)

    # ------------------------------------------------------------------
    # 文件列表
    # ------------------------------------------------------------------

    def list_files(
        self,
        user: User,
        parent_id: int | None = None,
        keyword: str = "",
        page: int = 1,
        page_size: int = 50,
        file_type: str = "",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """列出当前目录下的文件与子目录（分页、搜索、过滤）。"""
        q = self.db.query(FileItem).filter(
            FileItem.user_id == user.id,
            FileItem.is_deleted == False,  # noqa: E712
        )

        # 目录浏览 vs 全局搜索
        if keyword:
            q = q.filter(FileItem.name.ilike(f"%{keyword}%"))
        else:
            q = q.filter(
                FileItem.parent_id == parent_id
                if parent_id is not None
                else FileItem.parent_id.is_(None)
            )

        # 按类型过滤
        if file_type:
            q = self._apply_type_filter(q, file_type)

        # 时间范围
        if start_time:
            q = q.filter(FileItem.created_at >= start_time)
        if end_time:
            q = q.filter(FileItem.created_at <= end_time)

        total = q.count()
        q = q.order_by(FileItem.is_dir.desc(), FileItem.name.asc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        items = q.all()

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def _apply_type_filter(query, file_type: str):
        """按文件类型过滤查询。"""
        type_filters = {
            "image": [
                "image/jpeg", "image/png", "image/gif",
                "image/bmp", "image/webp",
            ],
            "video": ["video/mp4", "video/x-msvideo", "video/x-matroska"],
            "audio": ["audio/mpeg", "audio/wav", "audio/flac"],
            "pdf": ["application/pdf"],
            "text": ["text/plain"],
            "archive": [
                "application/zip", "application/vnd.rar",
                "application/x-7z-compressed", "application/gzip",
            ],
            "doc": [
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-powerpoint",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ],
        }
        mimes = type_filters.get(file_type)
        if mimes:
            query = query.filter(FileItem.is_dir == False, FileItem.mime_type.in_(mimes))  # noqa: E712
        return query

    # ------------------------------------------------------------------
    # 文件详情
    # ------------------------------------------------------------------

    def get_file_detail(self, file_id: int, user: User) -> FileItem:
        return self._get_file(file_id, user_id=user.id)

    # ------------------------------------------------------------------
    # 新建文件夹
    # ------------------------------------------------------------------

    def mkdir(self, name: str, parent_id: int | None, user: User) -> FileItem:
        """在指定目录下创建子文件夹。"""
        # 校验父目录归属
        if parent_id is not None:
            parent = self._get_file(parent_id, user_id=user.id)
            if not parent.is_dir:
                raise BadRequestException("父路径必须是一个文件夹")

        self._check_name_conflict(name, parent_id, user.id)

        folder = FileItem(
            name=name,
            is_dir=True,
            parent_id=parent_id,
            user_id=user.id,
            mime_type="inode/directory",
        )
        self.db.add(folder)
        self.db.flush()
        self._log(user.id, "mkdir", f"创建文件夹: {name}")
        return folder

    # ------------------------------------------------------------------
    # 重命名
    # ------------------------------------------------------------------

    def rename(self, file_id: int, new_name: str, user: User) -> FileItem:
        file = self._get_file(file_id, user_id=user.id)
        self._check_name_conflict(new_name, file.parent_id, user.id, exclude_id=file_id)
        old_name = file.name
        file.name = new_name
        file.updated_at = datetime.now(timezone.utc)
        self.db.add(file)
        self.db.flush()
        self._log(user.id, "rename", f"重命名: {old_name} -> {new_name}")
        return file

    # ------------------------------------------------------------------
    # 移动
    # ------------------------------------------------------------------

    def move(self, file_ids: list[int], target_parent_id: int | None, user: User) -> list[FileItem]:
        """批量移动文件/文件夹到目标目录。"""
        if target_parent_id is not None:
            target = self._get_file(target_parent_id, user_id=user.id)
            if not target.is_dir:
                raise BadRequestException("目标必须是文件夹")

        moved: list[FileItem] = []
        for fid in file_ids:
            file = self._get_file(fid, user_id=user.id)
            if target_parent_id is not None and self._is_descendant(target_parent_id, fid):
                raise BadRequestException(f"不能将文件夹移动到自身或子文件夹内: {file.name}")

            # 检查目标目录同名冲突
            self._check_name_conflict(file.name, target_parent_id, user.id, exclude_id=fid)

            file.parent_id = target_parent_id
            file.updated_at = datetime.now(timezone.utc)
            self.db.add(file)
            moved.append(file)

        self.db.flush()
        self._log(user.id, "move", f"移动 {len(file_ids)} 个文件/文件夹")
        return moved

    def _is_descendant(self, ancestor_id: int, descendant_id: int) -> bool:
        """检查 descendant_id 是否是 ancestor_id 的后代。"""
        current_id = ancestor_id
        # 简单场景下检查: target_parent_id 不能等于 file_id
        # 也不能是 file_id 的子孙
        file = self.db.get(FileItem, descendant_id)
        if file is None:
            return False
        if not file.is_dir:
            return False
        # 向上遍历检查
        child_ids = [descendant_id]
        while child_ids:
            children = (
                self.db.query(FileItem)
                .filter(
                    FileItem.parent_id.in_(child_ids),
                    FileItem.is_deleted == False,  # noqa: E712
                )
                .all()
            )
            child_ids = [c.id for c in children]
            if ancestor_id in child_ids:
                return True
        return False

    # ------------------------------------------------------------------
    # 删除（软删除，移到回收站）
    # ------------------------------------------------------------------

    def delete(self, file_ids: list[int], user: User) -> None:
        """软删除文件/文件夹，递归标记所有子孙。"""
        all_ids = self._collect_tree_ids(file_ids, user.id)

        files = (
            self.db.query(FileItem)
            .filter(FileItem.id.in_(all_ids), FileItem.user_id == user.id)
            .all()
        )
        if not files:
            raise NotFoundException("未找到可删除的文件或文件夹")

        now = datetime.now(timezone.utc)
        delta_bytes = 0
        for f in files:
            if f.is_deleted:
                continue
            f.is_deleted = True
            f.deleted_at = now
            self.db.add(f)
            if not f.is_dir:
                delta_bytes -= f.file_size

        self._update_storage_used(user, delta_bytes)
        self.db.flush()
        self._log(user.id, "delete", f"删除 {len(files)} 个条目")

    def _collect_tree_ids(self, root_ids: list[int], user_id: int) -> set[int]:
        """递归收集所有子孙 id（包括自身）。"""
        result: set[int] = set()
        stack = list(root_ids)
        while stack:
            current = stack.pop()
            if current in result:
                continue
            result.add(current)
            children = (
                self.db.query(FileItem.id)
                .filter(
                    FileItem.parent_id == current,
                    FileItem.user_id == user_id,
                    FileItem.is_deleted == False,  # noqa: E712
                )
                .all()
            )
            stack.extend(c[0] for c in children)
        return result

    # ------------------------------------------------------------------
    # 彻底删除（回收站清空）
    # ------------------------------------------------------------------

    def permanent_delete(self, file_ids: list[int], user: User) -> None:
        """彻底删除记录并从磁盘移除文件。"""
        all_ids = self._collect_trash_tree_ids(file_ids, user.id)

        files = self.db.query(FileItem).filter(FileItem.id.in_(all_ids)).all()
        if not files:
            raise NotFoundException("未找到可删除的文件")

        total_bytes = 0
        for f in files:
            # 从磁盘删除
            if not f.is_dir and f.storage_path:
                self._remove_from_disk(f.storage_path)
            total_bytes += f.file_size if not f.is_dir else 0
            self.db.delete(f)

        if total_bytes > 0:
            self._update_storage_used(user, -total_bytes)

        self.db.flush()
        self._log(user.id, "permanent_delete", f"彻底删除 {len(files)} 个文件/文件夹")

    def _collect_trash_tree_ids(self, root_ids: list[int], user_id: int) -> set[int]:
        """递归收集回收站中所有子孙 id。"""
        result: set[int] = set()
        stack = list(root_ids)
        while stack:
            current = stack.pop()
            if current in result:
                continue
            result.add(current)
            children = (
                self.db.query(FileItem.id)
                .filter(
                    FileItem.parent_id == current,
                    FileItem.user_id == user_id,
                )
                .all()
            )
            stack.extend(c[0] for c in children)
        return result

    @staticmethod
    def _remove_from_disk(storage_path: str) -> None:
        path = Path(storage_path)
        if path.exists() and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # 恢复（从回收站还原）
    # ------------------------------------------------------------------

    def restore(self, file_ids: list[int], user: User) -> list[FileItem]:
        """从回收站恢复文件/文件夹。"""
        all_ids = self._collect_trash_tree_ids(file_ids, user.id)
        files = (
            self.db.query(FileItem)
            .filter(
                FileItem.id.in_(all_ids),
                FileItem.user_id == user.id,
                FileItem.is_deleted == True,  # noqa: E712
            )
            .all()
        )

        restored: list[FileItem] = []
        for f in files:
            # 检查原路径上是否存在同名未删除文件
            conflicting = (
                self.db.query(FileItem)
                .filter(
                    FileItem.user_id == user.id,
                    FileItem.parent_id == f.parent_id,
                    FileItem.name == f.name,
                    FileItem.is_deleted == False,  # noqa: E712
                )
                .first()
            )
            if conflicting:
                f.name = self._generate_restore_name(f.name, f.parent_id, user.id)

            f.is_deleted = False
            f.deleted_at = None
            f.updated_at = datetime.now(timezone.utc)
            self.db.add(f)
            restored.append(f)

            if not f.is_dir:
                self._update_storage_used(user, f.file_size)

        self.db.flush()
        self._log(user.id, "restore", f"恢复 {len(restored)} 个文件/文件夹")
        return restored

    def _generate_restore_name(self, name: str, parent_id: int | None, user_id: int, counter: int = 1) -> str:
        """为恢复的文件生成不冲突的名称。"""
        stem = Path(name).stem
        suffixes = "".join(Path(name).suffixes)
        candidate = f"{stem} (恢复{counter}){suffixes}" if counter > 1 else f"{stem} (恢复){suffixes}"
        exists = (
            self.db.query(FileItem)
            .filter(
                FileItem.user_id == user_id,
                FileItem.parent_id == parent_id,
                FileItem.name == candidate,
                FileItem.is_deleted == False,  # noqa: E712
            )
            .first()
        )
        if exists:
            return self._generate_restore_name(name, parent_id, user_id, counter + 1)
        return candidate

    # ------------------------------------------------------------------
    # 回收站列表
    # ------------------------------------------------------------------

    def list_trash(self, user: User, page: int = 1, page_size: int = 50) -> dict:
        q = self.db.query(FileItem).filter(
            FileItem.user_id == user.id,
            FileItem.is_deleted == True,  # noqa: E712
        )
        total = q.count()
        q = q.order_by(FileItem.deleted_at.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)

        return {
            "items": q.all(),
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ------------------------------------------------------------------
    # 上传文件
    # ------------------------------------------------------------------

    def upload(
        self,
        file_obj: BinaryIO,
        filename: str,
        parent_id: int | None,
        user: User,
    ) -> FileItem:
        """处理单文件上传：校验、写盘、写库、更新配额。"""
        # 校验扩展名
        suffix = self._validate_extension(filename)
        mime_type = self._infer_mime_type(suffix)

        # 校验父目录
        if parent_id is not None:
            parent = self._get_file(parent_id, user_id=user.id)
            if not parent.is_dir:
                raise BadRequestException("上传目标必须是文件夹")

        # 名称冲突检查
        self._check_name_conflict(filename, parent_id, user.id)

        # 先检查配额（文件大小未知时先不检查，写盘后检查）
        storage_path = self._resolve_upload_storage_path(filename, user.id)

        # 写入磁盘
        try:
            with open(storage_path, "wb") as buffer:
                file_obj.seek(0)
                shutil.copyfileobj(file_obj, buffer)
        except Exception:
            self._remove_from_disk(str(storage_path))
            raise BadRequestException("文件写入失败")

        file_size = storage_path.stat().st_size

        # 配额校验
        if user.storage_quota > 0 and (user.storage_used + file_size) > user.storage_quota:
            self._remove_from_disk(str(storage_path))
            raise QuotaExceededException("存储空间不足，请清理后再上传")

        # 写数据库
        file_item = FileItem(
            name=filename,
            storage_path=str(storage_path),
            file_size=file_size,
            mime_type=mime_type,
            is_dir=False,
            parent_id=parent_id,
            user_id=user.id,
        )
        self.db.add(file_item)
        self._update_storage_used(user, file_size)
        self.db.flush()
        self._log(user.id, "upload", f"上传文件: {filename} ({file_size} bytes)")
        return file_item

    # ------------------------------------------------------------------
    # 下载 / 获取存储路径
    # ------------------------------------------------------------------

    def get_storage_path(self, file_id: int, user: User) -> tuple[FileItem, Path]:
        """返回文件记录和磁盘路径，用于下载。"""
        file = self._get_file(file_id, user_id=user.id)
        if file.is_dir:
            raise BadRequestException("不能下载文件夹")
        path = Path(file.storage_path)
        if not path.exists() or not path.is_file():
            raise NotFoundException("服务器上找不到该文件")
        return file, path

    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------

    def get_storage_stats(self, user: User) -> dict:
        """获取用户存储统计。"""
        file_count = (
            self.db.query(func.count(FileItem.id))
            .filter(
                FileItem.user_id == user.id,
                FileItem.is_dir == False,  # noqa: E712
                FileItem.is_deleted == False,  # noqa: E712
            )
            .scalar()
            or 0
        )
        folder_count = (
            self.db.query(func.count(FileItem.id))
            .filter(
                FileItem.user_id == user.id,
                FileItem.is_dir == True,  # noqa: E712
                FileItem.is_deleted == False,  # noqa: E712
            )
            .scalar()
            or 0
        )
        trash_count = (
            self.db.query(func.count(FileItem.id))
            .filter(
                FileItem.user_id == user.id,
                FileItem.is_deleted == True,  # noqa: E712
            )
            .scalar()
            or 0
        )
        return {
            "storage_used": user.storage_used,
            "storage_quota": user.storage_quota,
            "file_count": file_count,
            "folder_count": folder_count,
            "trash_count": trash_count,
        }

    # ------------------------------------------------------------------
    # 浏览器路径
    # ------------------------------------------------------------------

    def get_breadcrumbs(self, file_id: int | None, user: User) -> list[dict]:
        """根据 file_id 向上追溯完整路径面包屑。"""
        crumbs: list[dict] = []
        current_id = file_id
        while current_id is not None:
            file = self.db.query(FileItem).filter(
                FileItem.id == current_id,
                FileItem.user_id == user.id,
                FileItem.is_deleted == False,  # noqa: E712
            ).first()
            if file is None:
                break
            crumbs.append({"id": file.id, "name": file.name})
            current_id = file.parent_id
        crumbs.reverse()
        return crumbs
