"""文件管理 API 路由：列表、上传、新建文件夹、重命名、移动、复制、删除、恢复、下载、预览、搜索。"""

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import and_, or_

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
    QuotaExceededException,
)
from app.models.file import FileItem
from app.models.log import SystemLog
from app.models.note import FileNote
from app.models.user import User
from app.api.v1.dependencies import CurrentUser, DbSession
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.file import FileMove, FileOut, FileRename, FileSearch, MkdirRequest

router = APIRouter()


# ---------------------------------------------------------------------------
#  helpers
# ---------------------------------------------------------------------------

def _resolve_upload_path(storage_path: str) -> Path:
    """将数据库中的相对 storage_path 转为上传目录下的绝对路径，必要时创建父目录。"""
    full = Path(settings.UPLOAD_DIR) / storage_path
    full.parent.mkdir(parents=True, exist_ok=True)
    return full


def _check_ownership(file_item: FileItem, user: User) -> None:
    """校验当前用户是否为文件的拥有者（管理员可绕过）。"""
    if user.role == "admin":
        return
    if file_item.user_id != user.id:
        raise ForbiddenException("无权操作该文件")


def _check_name_conflict(
    db: DbSession,
    name: str,
    parent_id: int | None,
    user_id: int,
    exclude_id: int | None = None,
) -> None:
    """同一父目录下不允许存在同名文件/文件夹（未删除）。"""
    q = db.query(FileItem).filter(
        FileItem.name == name,
        FileItem.parent_id == parent_id,
        FileItem.user_id == user_id,
        FileItem.is_deleted == False,
    )
    if exclude_id is not None:
        q = q.filter(FileItem.id != exclude_id)
    if q.first():
        raise BadRequestException("该目录下已存在同名文件或文件夹")


def _collect_descendants(
    db: DbSession,
    parent_id: int,
    user_id: int,
    include_deleted: bool = False,
) -> list[FileItem]:
    """递归收集某个目录下的所有子孙节点（不包括该目录本身），返回扁平列表。"""
    result: list[FileItem] = []
    q = db.query(FileItem).filter(
        FileItem.parent_id == parent_id,
        FileItem.user_id == user_id,
    )
    if not include_deleted:
        q = q.filter(FileItem.is_deleted == False)

    children = q.all()
    for child in children:
        result.append(child)
        if child.is_dir:
            result.extend(
                _collect_descendants(db, child.id, user_id, include_deleted)
            )
    return result


def _check_quota(user: User, additional_bytes: int) -> None:
    """检查用户存储配额是否足够。quota 为 0 表示不受限（管理员）。"""
    if user.storage_quota == 0:
        return
    if user.storage_used + additional_bytes > user.storage_quota:
        raise QuotaExceededException("存储空间不足，请清理文件后重试")


_MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".zip": "application/zip",
    ".rar": "application/vnd.rar",
    ".7z": "application/x-7z-compressed",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".mp4": "video/mp4",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".json": "application/json",
    ".xml": "application/xml",
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".py": "text/x-python",
    ".java": "text/x-java",
    ".ts": "application/typescript",
    ".tsx": "application/typescript",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".sh": "text/x-shellscript",
    ".sql": "text/x-sql",
}


def _infer_mime_type(filename: str) -> str:
    """根据文件扩展名推断 MIME 类型。"""
    return _MIME_MAP.get(Path(filename).suffix.lower(), "application/octet-stream")


# 内联预览支持的 MIME 前缀及精确值
_INLINE_PREFIXES = ("image/", "video/", "audio/", "text/")
_INLINE_EXACT = (
    "application/pdf",
    "application/json",
    "application/xml",
    "application/javascript",
)


def _can_preview_inline(mime_type: str) -> bool:
    """判断该 MIME 类型是否可在浏览器中内联展示。"""
    return mime_type.startswith(_INLINE_PREFIXES) or mime_type in _INLINE_EXACT


def _log(db: DbSession, user_id: int, action: str, detail: str, ip: str = "") -> None:
    """记录一条系统操作日志。"""
    db.add(SystemLog(user_id=user_id, action=action, detail=detail, ip_address=ip))
    # 不在此处 commit，由调用方在事务末尾统一提交


# ---------------------------------------------------------------------------
#  列表 / 回收站 / 存储信息
# ---------------------------------------------------------------------------

@router.get("", response_model=ApiResponse[list[FileOut]])
def list_files(
    db: DbSession,
    current_user: CurrentUser,
    parent_id: int | None = Query(None, description="父目录 ID，为空则列出根目录"),
    all_users: bool = Query(False, description="管理员可查看所有用户的文件"),
):
    """列出指定目录下的所有文件与文件夹（不含回收站）。管理员可通过 all_users=true 查看全局文件。"""
    q = db.query(FileItem).filter(
        FileItem.parent_id == parent_id,
        FileItem.is_deleted == False,
    )
    if current_user.role != "admin" or not all_users:
        q = q.filter(FileItem.user_id == current_user.id)

    files = q.order_by(FileItem.is_dir.desc(), FileItem.name.asc()).all()
    return ApiResponse(data=[FileOut.model_validate(f) for f in files])


@router.get("/trash/stats", response_model=ApiResponse[dict])
def get_trash_stats(
    db: DbSession,
    current_user: CurrentUser,
):
    """获取回收站统计信息（文件数和总大小）。"""
    trash = (
        db.query(FileItem)
        .filter(FileItem.user_id == current_user.id, FileItem.is_deleted == True)
        .all()
    )
    file_count = sum(1 for f in trash if not f.is_dir)
    folder_count = sum(1 for f in trash if f.is_dir)
    total_size = sum(f.file_size for f in trash if not f.is_dir)
    return ApiResponse(data={
        "file_count": file_count,
        "folder_count": folder_count,
        "total_items": file_count + folder_count,
        "total_size": total_size,
    })


@router.get("/trash", response_model=ApiResponse[list[FileOut]])
def list_trash(
    db: DbSession,
    current_user: CurrentUser,
):
    """列出回收站中的所有文件。"""
    files = (
        db.query(FileItem)
        .filter(
            FileItem.user_id == current_user.id,
            FileItem.is_deleted == True,
        )
        .order_by(FileItem.deleted_at.desc())
        .all()
    )
    return ApiResponse(data=[FileOut.model_validate(f) for f in files])


@router.get("/tree", response_model=ApiResponse[list[dict]])
def get_directory_tree(
    db: DbSession,
    current_user: CurrentUser,
):
    """获取当前用户的目录树（仅文件夹，用于左侧导航）。"""
    folders = (
        db.query(FileItem)
        .filter(
            FileItem.user_id == current_user.id,
            FileItem.is_dir == True,
            FileItem.is_deleted == False,
        )
        .order_by(FileItem.name.asc())
        .all()
    )

    # 构建树结构：{id, name, parent_id, children}
    folder_map: dict[int, dict] = {}
    roots: list[dict] = []

    for f in folders:
        folder_map[f.id] = {
            "id": f.id,
            "name": f.name,
            "parent_id": f.parent_id,
            "children": [],
        }

    for f in folders:
        node = folder_map[f.id]
        if f.parent_id and f.parent_id in folder_map:
            folder_map[f.parent_id]["children"].append(node)
        else:
            roots.append(node)

    return ApiResponse(data=roots)


@router.get("/breadcrumb", response_model=ApiResponse[list[dict]])
def get_breadcrumb(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int | None = Query(None, description="当前目录 ID，为空则返回根目录"),
):
    """获取从根目录到指定文件夹的面包屑路径。"""
    breadcrumb: list[dict] = []
    if file_id is None:
        breadcrumb.append({"id": None, "name": "根目录"})
        return ApiResponse(data=breadcrumb)

    current = db.get(FileItem, file_id)
    if current is None:
        breadcrumb.append({"id": None, "name": "根目录"})
        return ApiResponse(data=breadcrumb)

    # 追溯父级链
    chain: list[dict] = []
    visited: set[int] = set()
    node = current
    while node is not None:
        if node.id in visited:
            break
        visited.add(node.id)
        chain.append({"id": node.id, "name": node.name})
        if node.parent_id is not None:
            node = db.get(FileItem, node.parent_id)
        else:
            node = None

    chain.reverse()
    # 添加根目录
    breadcrumb.append({"id": None, "name": "根目录"})
    breadcrumb.extend(chain)

    return ApiResponse(data=breadcrumb)


@router.get("/activity", response_model=ApiResponse[list[dict]])
def get_recent_activity(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = 10,
):
    """获取当前用户最近的文件操作记录。"""
    from app.models.log import SystemLog
    logs = (
        db.query(SystemLog)
        .filter(SystemLog.user_id == current_user.id)
        .order_by(SystemLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return ApiResponse(data=[
        {
            "id": log.id,
            "action": log.action,
            "detail": log.detail,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ])


@router.get("/recent", response_model=ApiResponse[list[FileOut]])
def get_recent_files(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = 12,
):
    """获取当前用户最近访问/操作的文件（按 last_accessed_at 降序）。"""
    recent = (
        db.query(FileItem)
        .filter(
            FileItem.user_id == current_user.id,
            FileItem.is_deleted == False,
            FileItem.is_dir == False,
            FileItem.last_accessed_at != None,
        )
        .order_by(FileItem.last_accessed_at.desc())
        .limit(limit)
        .all()
    )
    return ApiResponse(data=[FileOut.model_validate(f) for f in recent])


@router.get("/storage", response_model=ApiResponse[dict[str, Any]])
def get_storage_info(
    db: DbSession,
    current_user: CurrentUser,
):
    """获取当前用户的存储空间用量。"""
    quota = current_user.storage_quota
    used = current_user.storage_used
    percent = round(used / quota * 100, 2) if quota > 0 else 0
    return ApiResponse(
        data={
            "storage_used": used,
            "storage_quota": quota,
            "usage_percent": percent,
        }
    )


@router.get("/{file_id}", response_model=ApiResponse[FileOut])
def get_file_detail(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int,
):
    """获取单个文件/文件夹的详细信息。"""
    file_item = db.get(FileItem, file_id)
    if file_item is None:
        raise NotFoundException("文件不存在")
    _check_ownership(file_item, current_user)
    return ApiResponse(data=FileOut.model_validate(file_item))


# ---------------------------------------------------------------------------
#  上传
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=ApiResponse[FileOut])
async def upload_file(
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    parent_id: int | None = Form(None),
):
    """上传文件到指定目录。"""
    if not file.filename:
        raise BadRequestException("文件名为空")

    filename = file.filename.strip()

    # 校验扩展名
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext and ext not in settings.allowed_extensions_set:
        raise BadRequestException(f"不支持的文件类型: .{ext}")

    # 验证父目录（若指定）
    if parent_id is not None:
        parent = db.get(FileItem, parent_id)
        if parent is None or parent.user_id != current_user.id or not parent.is_dir:
            raise NotFoundException("目标目录不存在")
        if parent.is_deleted:
            raise BadRequestException("目标目录在回收站中，请先恢复")

    # 读取文件内容
    contents = await file.read()
    file_size = len(contents)

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size > max_bytes:
        raise BadRequestException(
            f"文件大小超过上限 {settings.MAX_UPLOAD_SIZE_MB} MB"
        )

    # 配额检查
    _check_quota(current_user, file_size)

    # 同名检查
    _check_name_conflict(db, filename, parent_id, current_user.id)

    # 生成唯一存储路径： {user_id}/{uuid}_{原始文件名}
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    storage_path = f"{current_user.id}/{unique_name}"

    # 写入磁盘
    dest = _resolve_upload_path(storage_path)
    dest.write_bytes(contents)

    mime_type = _infer_mime_type(filename)
    file_item = FileItem(
        name=filename,
        storage_path=storage_path,
        file_size=file_size,
        mime_type=mime_type,
        is_dir=False,
        parent_id=parent_id,
        user_id=current_user.id,
    )
    db.add(file_item)

    # 更新用户已用空间
    current_user.storage_used += file_size

    _log(db, current_user.id, "upload", f"上传文件: {filename} ({file_size} bytes)")

    db.commit()
    db.refresh(file_item)

    return ApiResponse(data=FileOut.model_validate(file_item))


# ---------------------------------------------------------------------------
#  分片上传（大文件 > 10 MB 自动使用）
# ---------------------------------------------------------------------------

import json as _json

CHUNK_DIR = Path(settings.UPLOAD_DIR).parent / "chunks"

# 存储进行中的分片上传会话
_pending_uploads: dict[str, dict[str, Any]] = {}


@router.post("/upload/chunk/init", response_model=ApiResponse[dict])
async def chunk_upload_init(
    current_user: CurrentUser,
    db: DbSession,
    filename: str = Form(...),
    total_size: int = Form(...),
    total_chunks: int = Form(...),
    parent_id: int | None = Form(None),
):
    """初始化分片上传，返回 upload_id。"""
    filename = filename.strip()
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext and ext not in settings.allowed_extensions_set:
        raise BadRequestException(f"不支持的文件类型: .{ext}")

    _check_quota(current_user, total_size)

    if parent_id is not None:
        parent = db.get(FileItem, parent_id)
        if parent is None or not parent.is_dir:
            raise NotFoundException("目标目录不存在")

    _check_name_conflict(db, filename, parent_id, current_user.id)

    upload_id = uuid.uuid4().hex
    chunk_dir = CHUNK_DIR / upload_id
    chunk_dir.mkdir(parents=True, exist_ok=True)

    _pending_uploads[upload_id] = {
        "filename": filename,
        "total_size": total_size,
        "total_chunks": total_chunks,
        "parent_id": parent_id,
        "user_id": current_user.id,
        "received": 0,
    }

    # 会话信息持久化到磁盘
    (chunk_dir / "meta.json").write_text(_json.dumps({
        "filename": filename,
        "total_size": total_size,
        "total_chunks": total_chunks,
        "parent_id": parent_id,
        "user_id": current_user.id,
    }))

    return ApiResponse(data={"upload_id": upload_id, "chunk_size": settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 // max(total_chunks, 1)})


@router.post("/upload/chunk/{upload_id}", response_model=ApiResponse[dict])
async def chunk_upload_part(
    upload_id: str,
    current_user: CurrentUser,
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
):
    """上传单个分片。"""
    chunk_dir = CHUNK_DIR / upload_id
    meta_file = chunk_dir / "meta.json"

    if not meta_file.exists():
        raise NotFoundException("上传会话不存在或已过期")

    meta = _json.loads(meta_file.read_text())
    if meta["user_id"] != current_user.id:
        raise ForbiddenException("无权操作此上传会话")

    # 保存分片
    chunk_path = chunk_dir / f"chunk_{chunk_index:06d}"
    chunk_data = await chunk.read()
    chunk_path.write_bytes(chunk_data)

    return ApiResponse(data={"chunk_index": chunk_index, "received": True, "size": len(chunk_data)})


@router.post("/upload/chunk/{upload_id}/complete", response_model=ApiResponse[FileOut])
def chunk_upload_complete(
    upload_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """合并分片，完成上传。"""
    chunk_dir = CHUNK_DIR / upload_id
    meta_file = chunk_dir / "meta.json"

    if not meta_file.exists():
        raise NotFoundException("上传会话不存在或已过期")

    meta = _json.loads(meta_file.read_text())
    if meta["user_id"] != current_user.id:
        raise ForbiddenException("无权操作此上传会话")

    filename = meta["filename"]
    total_size = meta["total_size"]
    total_chunks = meta["total_chunks"]
    parent_id = meta["parent_id"]

    # 验证所有分片已接收
    received = 0
    all_data = bytearray()
    for i in range(total_chunks):
        chunk_path = chunk_dir / f"chunk_{i:06d}"
        if not chunk_path.exists():
            raise BadRequestException(f"缺少分片 {i}，请重新上传")
        data = chunk_path.read_bytes()
        all_data.extend(data)
        received += len(data)

    if received != total_size:
        raise BadRequestException(f"文件大小不一致: 期望 {total_size}, 实际 {received}")

    # 配额检查
    user = db.get(User, current_user.id)
    _check_quota(user, total_size)

    # 存储合并后的文件
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    storage_path = f"{current_user.id}/{unique_name}"
    dest = Path(settings.UPLOAD_DIR) / storage_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(bytes(all_data))

    mime_type = _infer_mime_type(filename)
    file_item = FileItem(
        name=filename,
        storage_path=storage_path,
        file_size=total_size,
        mime_type=mime_type,
        is_dir=False,
        parent_id=parent_id,
        user_id=current_user.id,
    )
    db.add(file_item)
    user.storage_used += total_size
    _log(db, current_user.id, "upload", f"分片上传: {filename} ({total_size} bytes, {total_chunks} chunks)")

    db.commit()
    db.refresh(file_item)

    # 清理分片临时文件
    shutil.rmtree(chunk_dir, ignore_errors=True)

    return ApiResponse(data=FileOut.model_validate(file_item))


# ---------------------------------------------------------------------------
#  新建文件夹
# ---------------------------------------------------------------------------

@router.post("/touch", response_model=ApiResponse[FileOut])
def touch_file(
    db: DbSession,
    current_user: CurrentUser,
    name: str = Form(...),
    content: str = Form(""),
    parent_id: int | None = Form(None),
):
    """在当前目录创建一个新的文本文件。"""
    name = name.strip()
    if not name:
        raise BadRequestException("文件名不能为空")

    # 自动加扩展名
    if "." not in name:
        name = name + ".txt"

    ext = Path(name).suffix.lower().lstrip(".")
    if ext and ext not in settings.allowed_extensions_set:
        raise BadRequestException(f"不支持的文件类型: .{ext}")

    if parent_id is not None:
        parent = db.get(FileItem, parent_id)
        if parent is None or parent.user_id != current_user.id or not parent.is_dir:
            raise NotFoundException("目标目录不存在")

    _check_name_conflict(db, name, parent_id, current_user.id)

    content_bytes = content.encode("utf-8")
    file_size = len(content_bytes)

    _check_quota(current_user, file_size)

    unique_name = f"{uuid.uuid4().hex}_{name}"
    storage_path = f"{current_user.id}/{unique_name}"
    dest = _resolve_upload_path(storage_path)
    dest.write_bytes(content_bytes)

    mime_type = _infer_mime_type(name)
    file_item = FileItem(
        name=name, storage_path=storage_path, file_size=file_size,
        mime_type=mime_type, is_dir=False, parent_id=parent_id, user_id=current_user.id,
    )
    db.add(file_item)
    current_user.storage_used += file_size
    _log(db, current_user.id, "touch", f"新建文件: {name}")
    db.commit()
    db.refresh(file_item)
    return ApiResponse(data=FileOut.model_validate(file_item))


@router.post("/mkdir", response_model=ApiResponse[FileOut])
def mkdir(
    db: DbSession,
    current_user: CurrentUser,
    body: MkdirRequest,
):
    """新建文件夹。"""
    name = body.name.strip()
    parent_id = body.parent_id

    if not name:
        raise BadRequestException("文件夹名不能为空")

    if parent_id is not None:
        parent = db.get(FileItem, parent_id)
        if parent is None or parent.user_id != current_user.id or not parent.is_dir:
            raise NotFoundException("目标目录不存在")
        if parent.is_deleted:
            raise BadRequestException("目标目录在回收站中，请先恢复")

    _check_name_conflict(db, name, parent_id, current_user.id)

    folder = FileItem(
        name=name,
        is_dir=True,
        file_size=0,
        mime_type="inode/directory",
        parent_id=parent_id,
        user_id=current_user.id,
    )
    db.add(folder)
    _log(db, current_user.id, "mkdir", f"创建文件夹: {name}")
    db.commit()
    db.refresh(folder)

    return ApiResponse(data=FileOut.model_validate(folder))


# ---------------------------------------------------------------------------
#  重命名
# ---------------------------------------------------------------------------

@router.put("/{file_id}/rename", response_model=ApiResponse[FileOut])
def rename_file(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int,
    body: FileRename,
):
    """重命名文件或文件夹。"""
    file_item = db.get(FileItem, file_id)
    if file_item is None:
        raise NotFoundException("文件不存在")
    _check_ownership(file_item, current_user)

    new_name = body.name.strip()
    if not new_name:
        raise BadRequestException("文件名不能为空")

    _check_name_conflict(
        db, new_name, file_item.parent_id, current_user.id, exclude_id=file_id
    )

    file_item.name = new_name
    file_item.updated_at = datetime.now(timezone.utc)
    _log(db, current_user.id, "rename", f"重命名: {file_item.name} -> {new_name}")
    db.commit()
    db.refresh(file_item)

    return ApiResponse(data=FileOut.model_validate(file_item))


# ---------------------------------------------------------------------------
#  移动
# ---------------------------------------------------------------------------

@router.put("/move", response_model=ApiResponse[dict[str, Any]])
def move_files(
    db: DbSession,
    current_user: CurrentUser,
    body: FileMove,
):
    """批量移动文件/文件夹到目标目录。"""
    if not body.file_ids:
        raise BadRequestException("请选择至少一个文件")

    target_parent_id = body.target_parent_id

    # 验证目标目录
    if target_parent_id is not None:
        target = db.get(FileItem, target_parent_id)
        if target is None or target.user_id != current_user.id or not target.is_dir:
            raise NotFoundException("目标目录不存在")
        if target.is_deleted:
            raise BadRequestException("目标目录在回收站中，请先恢复")

    now = datetime.now(timezone.utc)
    moved = 0
    for fid in body.file_ids:
        item = db.get(FileItem, fid)
        if item is None:
            continue
        _check_ownership(item, current_user)

        # 禁止将目录移动到自身或子孙目录下
        if item.is_dir and target_parent_id is not None:
            descendants = _collect_descendants(
                db, item.id, current_user.id, include_deleted=True
            )
            descendant_ids = {d.id for d in descendants}
            if target_parent_id == item.id or target_parent_id in descendant_ids:
                raise BadRequestException(
                    f"不能将文件夹「{item.name}」移动到自身或子文件夹中"
                )

        # 目标位置同名检查
        _check_name_conflict(
            db, item.name, target_parent_id, current_user.id, exclude_id=item.id
        )

        item.parent_id = target_parent_id
        item.updated_at = now
        moved += 1

    _log(db, current_user.id, "move", f"移动 {moved} 个文件到目录 ID {target_parent_id}")
    db.commit()
    return ApiResponse(data={"moved_count": moved})


# ---------------------------------------------------------------------------
#  软删除（移入回收站）
# ---------------------------------------------------------------------------

@router.delete("/{file_id}", response_model=ApiResponse[dict[str, Any]])
def delete_file(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int,
):
    """软删除文件/文件夹（移入回收站）。"""
    file_item = db.get(FileItem, file_id)
    if file_item is None:
        raise NotFoundException("文件不存在")
    _check_ownership(file_item, current_user)

    if file_item.is_deleted:
        raise BadRequestException("文件已在回收站中")

    now = datetime.now(timezone.utc)

    def _soft_delete(item: FileItem) -> None:
        item.is_deleted = True
        item.deleted_at = now
        item.updated_at = now
        if item.is_dir:
            for child in _collect_descendants(
                db, item.id, current_user.id, include_deleted=False
            ):
                child.is_deleted = True
                child.deleted_at = now
                child.updated_at = now

    _soft_delete(file_item)
    _log(db, current_user.id, "delete", f"软删除: {file_item.name} (ID {file_id})")
    db.commit()
    return ApiResponse(data={"deleted": True})


# ---------------------------------------------------------------------------
#  从回收站恢复
# ---------------------------------------------------------------------------

@router.post("/{file_id}/restore", response_model=ApiResponse[FileOut])
def restore_file(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int,
):
    """从回收站恢复文件/文件夹。"""
    file_item = db.get(FileItem, file_id)
    if file_item is None:
        raise NotFoundException("文件不存在")
    _check_ownership(file_item, current_user)

    if not file_item.is_deleted:
        raise BadRequestException("该文件不在回收站中")

    # 父目录如果在回收站中，不允许恢复子项
    if file_item.parent_id is not None:
        parent = db.get(FileItem, file_item.parent_id)
        if parent and parent.is_deleted:
            raise BadRequestException("父目录在回收站中，请先恢复父目录")

    # 原位置同名冲突检查
    conflicting = (
        db.query(FileItem)
        .filter(
            FileItem.name == file_item.name,
            FileItem.parent_id == file_item.parent_id,
            FileItem.user_id == current_user.id,
            FileItem.is_deleted == False,
            FileItem.id != file_item.id,
        )
        .first()
    )
    if conflicting:
        raise BadRequestException(
            f"原位置已存在同名文件「{file_item.name}」，请先处理冲突"
        )

    now = datetime.now(timezone.utc)

    def _restore(item: FileItem) -> None:
        item.is_deleted = False
        item.deleted_at = None
        item.updated_at = now
        if item.is_dir:
            for child in _collect_descendants(
                db, item.id, current_user.id, include_deleted=True
            ):
                if child.is_deleted:
                    child.is_deleted = False
                    child.deleted_at = None
                    child.updated_at = now

    _restore(file_item)
    _log(db, current_user.id, "restore", f"恢复: {file_item.name} (ID {file_id})")
    db.commit()
    db.refresh(file_item)

    return ApiResponse(data=FileOut.model_validate(file_item))


# ---------------------------------------------------------------------------
#  永久删除（从回收站彻底清除）
# ---------------------------------------------------------------------------

@router.post("/trash/empty", response_model=ApiResponse[dict])
def empty_trash(
    db: DbSession,
    current_user: CurrentUser,
):
    """一键清空当前用户的回收站（永久删除所有已删除文件）。"""
    trash_items = (
        db.query(FileItem)
        .filter(
            FileItem.user_id == current_user.id,
            FileItem.is_deleted == True,
        )
        .all()
    )

    total_freed = 0
    deleted_count = 0
    for item in trash_items:
        if item.storage_path and not item.is_dir:
            file_path = Path(settings.UPLOAD_DIR) / item.storage_path
            try:
                if file_path.exists():
                    file_path.unlink()
            except OSError:
                pass
            total_freed += item.file_size
        db.delete(item)
        deleted_count += 1

    current_user.storage_used = max(0, current_user.storage_used - total_freed)
    _log(db, current_user.id, "empty_trash", f"清空回收站: {deleted_count} 个文件, 释放 {total_freed} bytes")
    db.commit()

    return ApiResponse(data={"deleted_count": deleted_count, "freed_bytes": total_freed})


@router.delete("/{file_id}/permanent", response_model=ApiResponse[dict[str, Any]])
def delete_permanent(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int,
):
    """永久删除文件/文件夹，同时释放存储空间。"""
    file_item = db.get(FileItem, file_id)
    if file_item is None:
        raise NotFoundException("文件不存在")
    _check_ownership(file_item, current_user)

    def _permanent_delete(item: FileItem) -> int:
        """递归物理删除，返回释放的字节数。"""
        freed = 0
        if item.is_dir:
            for child in _collect_descendants(
                db, item.id, current_user.id, include_deleted=True
            ):
                freed += _permanent_delete(child)

        # 删除物理文件
        if item.storage_path and not item.is_dir:
            file_path = Path(settings.UPLOAD_DIR) / item.storage_path
            try:
                if file_path.exists():
                    file_path.unlink()
            except OSError:
                pass

        freed += item.file_size if not item.is_dir else 0
        db.delete(item)
        return freed

    freed_bytes = _permanent_delete(file_item)

    # 更新用户已用空间（不低于 0）
    current_user.storage_used = max(0, current_user.storage_used - freed_bytes)

    _log(db, current_user.id, "permanent_delete", f"永久删除: {file_item.name} (ID {file_id}), 释放 {freed_bytes} bytes")
    db.commit()
    return ApiResponse(data={"deleted": True, "freed_bytes": freed_bytes})


# ---------------------------------------------------------------------------
#  批量操作（批量删除 / 批量永久删除）
# ---------------------------------------------------------------------------

@router.post("/batch-delete", response_model=ApiResponse[dict[str, Any]])
def batch_delete(
    db: DbSession,
    current_user: CurrentUser,
    file_ids: list[int],
):
    """批量软删除文件。"""
    if not file_ids:
        raise BadRequestException("请选择至少一个文件")

    now = datetime.now(timezone.utc)
    deleted_count = 0
    for fid in file_ids:
        item = db.get(FileItem, fid)
        if item is None or item.user_id != current_user.id:
            continue
        if item.is_deleted:
            continue

        item.is_deleted = True
        item.deleted_at = now
        item.updated_at = now
        if item.is_dir:
            for child in _collect_descendants(
                db, item.id, current_user.id, include_deleted=False
            ):
                child.is_deleted = True
                child.deleted_at = now
                child.updated_at = now
        deleted_count += 1

    _log(db, current_user.id, "batch_delete", f"批量删除 {deleted_count} 个文件")
    db.commit()
    return ApiResponse(data={"deleted_count": deleted_count})


# ---------------------------------------------------------------------------
#  批量重命名
# ---------------------------------------------------------------------------

@router.post("/batch-rename", response_model=ApiResponse[dict])
def batch_rename(
    db: DbSession,
    current_user: CurrentUser,
    file_ids: str = Form(...),
    pattern: str = Form(""),
):
    """批量重命名文件。pattern 支持占位符：{name}=原名, {n}=序号, {ext}=扩展名。file_ids 逗号分隔。"""
    ids = [int(x.strip()) for x in file_ids.split(",") if x.strip()]
    if not ids:
        raise BadRequestException("请选择至少一个文件")
    if not pattern.strip():
        raise BadRequestException("请提供重命名模式，例如: 照片_{n}{ext}")

    pattern = pattern.strip()
    files_to_rename = (
        db.query(FileItem)
        .filter(FileItem.id.in_(ids), FileItem.user_id == current_user.id,
                FileItem.is_deleted == False)
        .order_by(FileItem.name)
        .all()
    )

    if not files_to_rename:
        raise BadRequestException("没有可重命名的文件")

    n = 1
    renamed = 0
    now = datetime.now(timezone.utc)
    for item in files_to_rename:
        base, ext = os.path.splitext(item.name)
        new_name = pattern.replace("{name}", base).replace("{n}", str(n)).replace("{ext}", ext)
        # 检查同名冲突
        _check_name_conflict(db, new_name, item.parent_id, current_user.id, exclude_id=item.id)
        item.name = new_name
        item.updated_at = now
        renamed += 1
        n += 1

    _log(db, current_user.id, "batch_rename", f"批量重命名 {renamed} 个文件，模式: {pattern}")
    db.commit()
    return ApiResponse(data={"renamed_count": renamed, "pattern": pattern})


# ---------------------------------------------------------------------------
#  批量下载（打包为 ZIP）
# ---------------------------------------------------------------------------

@router.post("/batch-download")
def batch_download(
    db: DbSession,
    current_user: CurrentUser,
    file_ids: list[int],
):
    """将选中的多个文件打包为 ZIP 下载。"""
    import io as _io
    import zipfile as _zipfile

    if not file_ids:
        raise BadRequestException("请选择至少一个文件")

    # 去重
    file_ids = list(dict.fromkeys(file_ids))

    # 收集要打包的文件（跳过文件夹和回收站文件）
    to_pack: list[FileItem] = []
    for fid in file_ids:
        item = db.get(FileItem, fid)
        if item is None or item.user_id != current_user.id:
            continue
        if item.is_dir:
            continue  # 暂不支持打包文件夹
        if item.is_deleted:
            continue
        if not item.storage_path:
            continue
        disk_path = Path(settings.UPLOAD_DIR) / item.storage_path
        if not disk_path.exists():
            continue
        to_pack.append(item)

    if not to_pack:
        raise BadRequestException("没有可下载的有效文件")

    # 在内存中创建 ZIP
    buf = _io.BytesIO()
    seen_names: dict[str, int] = {}
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        for item in to_pack:
            disk_path = Path(settings.UPLOAD_DIR) / item.storage_path
            # 处理重名
            name = item.name
            if name in seen_names:
                seen_names[name] += 1
                base, ext = os.path.splitext(name)
                name = f"{base} ({seen_names[name]}){ext}"
            else:
                seen_names[name] = 0
            zf.write(str(disk_path), arcname=name)
            _log(db, current_user.id, "download", f"批量下载: {item.name}")

    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=clouddisk_batch.zip"},
    )


# ---------------------------------------------------------------------------
#  复制
# ---------------------------------------------------------------------------

def _copy_file_record(
    db: DbSession,
    src: FileItem,
    target_parent_id: int | None,
    user: User,
    new_name: str | None = None,
) -> FileItem:
    """深度复制一条文件记录及其物理文件（递归处理文件夹）。返回新记录。"""
    copy_name = new_name or src.name

    if src.is_dir:
        # 创建目标文件夹
        new_folder = FileItem(
            name=copy_name,
            is_dir=True,
            file_size=0,
            mime_type="inode/directory",
            parent_id=target_parent_id,
            user_id=user.id,
        )
        db.add(new_folder)
        db.flush()

        # 递归复制子项
        children = (
            db.query(FileItem)
            .filter(
                FileItem.parent_id == src.id,
                FileItem.user_id == user.id,
                FileItem.is_deleted == False,
            )
            .all()
        )
        for child in children:
            _copy_file_record(db, child, new_folder.id, user)

        return new_folder
    else:
        # 复制物理文件
        src_path = Path(settings.UPLOAD_DIR) / src.storage_path
        unique_name = f"{uuid.uuid4().hex}_{copy_name}"
        storage_path = f"{user.id}/{unique_name}"
        dest_path = Path(settings.UPLOAD_DIR) / storage_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if src_path.exists():
            shutil.copy2(src_path, dest_path)
            file_size = src.file_size
        else:
            file_size = 0

        # 检查配额
        _check_quota(user, file_size)

        new_file = FileItem(
            name=copy_name,
            storage_path=storage_path,
            file_size=file_size,
            mime_type=src.mime_type,
            is_dir=False,
            parent_id=target_parent_id,
            user_id=user.id,
        )
        db.add(new_file)
        db.flush()

        # 更新用户空间
        user.storage_used += file_size

        return new_file


def _generate_copy_name(db: DbSession, original_name: str, parent_id: int | None, user_id: int) -> str:
    """为复制操作生成不冲突的名称：xxx - 副本, xxx - 副本 (2), ..."""
    base, ext = os.path.splitext(original_name)
    candidate = f"{base} - 副本{ext}"
    counter = 2
    while True:
        exists = (
            db.query(FileItem)
            .filter(
                FileItem.name == candidate,
                FileItem.parent_id == parent_id,
                FileItem.user_id == user_id,
                FileItem.is_deleted == False,
            )
            .first()
        )
        if not exists:
            return candidate
        candidate = f"{base} - 副本 ({counter}){ext}"
        counter += 1


@router.post("/{file_id}/copy", response_model=ApiResponse[FileOut])
def copy_file(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int,
    target_parent_id: int | None = None,
):
    """复制文件或文件夹到目标目录（同用户）。"""
    src = db.get(FileItem, file_id)
    if src is None:
        raise NotFoundException("文件不存在")
    _check_ownership(src, current_user)
    if src.is_deleted:
        raise BadRequestException("文件在回收站中，无法复制")

    # 验证目标目录
    if target_parent_id is not None:
        target = db.get(FileItem, target_parent_id)
        if target is None or target.user_id != current_user.id or not target.is_dir:
            raise NotFoundException("目标目录不存在")
        if target.is_deleted:
            raise BadRequestException("目标目录在回收站中")

        # 禁止复制到自己或子孙目录下
        if src.is_dir:
            descendants = _collect_descendants(db, src.id, current_user.id, include_deleted=True)
            descendant_ids = {d.id for d in descendants}
            if target_parent_id == src.id or target_parent_id in descendant_ids:
                raise BadRequestException("不能将文件夹复制到自身或子文件夹中")

    # 生成不冲突的名称
    copy_name = _generate_copy_name(db, src.name, target_parent_id, current_user.id)

    new_item = _copy_file_record(db, src, target_parent_id, current_user, copy_name)

    _log(db, current_user.id, "copy", f"复制: {src.name} -> {copy_name} (目标目录 ID {target_parent_id})")
    db.commit()
    db.refresh(new_item)

    return ApiResponse(data=FileOut.model_validate(new_item))


# ---------------------------------------------------------------------------
#  下载
# ---------------------------------------------------------------------------

@router.get("/{file_id}/download")
def download_file(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int,
):
    """下载文件（返回原始文件流）。"""
    file_item = db.get(FileItem, file_id)
    if file_item is None:
        raise NotFoundException("文件不存在")
    _check_ownership(file_item, current_user)

    if file_item.is_dir:
        raise BadRequestException("不能下载文件夹，请先打包")

    if file_item.is_deleted:
        raise BadRequestException("文件在回收站中，请先恢复")

    file_path = _resolve_upload_path(file_item.storage_path)
    if not file_path.exists():
        raise NotFoundException("文件在服务器上不存在")

    # 记录访问时间和下载次数
    file_item.last_accessed_at = datetime.now(timezone.utc)
    file_item.download_count += 1
    db.commit()

    encoded = quote(file_item.name)
    return FileResponse(
        path=str(file_path),
        filename=file_item.name,
        media_type=file_item.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        },
    )


# ---------------------------------------------------------------------------
#  预览
# ---------------------------------------------------------------------------

@router.get("/{file_id}/preview")
def preview_file(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int,
):
    """预览文件：可内联的类型直接返回，其余返回文件元信息。"""
    file_item = db.get(FileItem, file_id)
    if file_item is None:
        raise NotFoundException("文件不存在")
    _check_ownership(file_item, current_user)

    if file_item.is_dir:
        raise BadRequestException("不能预览文件夹")

    if file_item.is_deleted:
        raise BadRequestException("文件在回收站中，请先恢复")

    file_path = _resolve_upload_path(file_item.storage_path)
    if not file_path.exists():
        raise NotFoundException("文件在服务器上不存在")

    # 记录访问时间
    file_item.last_accessed_at = datetime.now(timezone.utc)
    db.commit()

    if _can_preview_inline(file_item.mime_type):
        encoded = quote(file_item.name)
        return FileResponse(
            path=str(file_path),
            filename=file_item.name,
            media_type=file_item.mime_type,
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{encoded}",
            },
        )

    return ApiResponse(
        data={
            "id": file_item.id,
            "name": file_item.name,
            "file_size": file_item.file_size,
            "mime_type": file_item.mime_type,
            "message": "该文件类型不支持在线预览，请下载后查看",
        }
    )


# ---------------------------------------------------------------------------
#  搜索
# ---------------------------------------------------------------------------

# 文件类型 -> SQLAlchemy filter 映射
_FILE_TYPE_FILTERS = {
    "image": FileItem.mime_type.like("image/%"),
    "video": FileItem.mime_type.like("video/%"),
    "audio": FileItem.mime_type.like("audio/%"),
    "pdf": FileItem.mime_type == "application/pdf",
    "text": or_(
        FileItem.mime_type.like("text/%"),
        FileItem.mime_type.in_([
            "application/json",
            "application/xml",
            "application/javascript",
            "text/html",
            "text/css",
        ]),
    ),
    "document": FileItem.mime_type.in_([
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ]),
    "archive": FileItem.mime_type.in_([
        "application/zip",
        "application/vnd.rar",
        "application/x-7z-compressed",
        "application/x-tar",
        "application/gzip",
    ]),
    "folder": FileItem.is_dir == True,
}

_KNOWN_OTHER_PREFIXES = ["image/", "video/", "audio/", "text/"]
_KNOWN_OTHER_EXACT = [
    "application/pdf", "application/json", "application/xml",
    "application/javascript", "text/html", "text/css",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/zip", "application/vnd.rar",
    "application/x-7z-compressed", "application/x-tar", "application/gzip",
]


# ---------------------------------------------------------------------------
#  从 URL 导入文件
# ---------------------------------------------------------------------------

@router.post("/import-url", response_model=ApiResponse[FileOut])
async def import_from_url(
    db: DbSession,
    current_user: CurrentUser,
    url: str = Form(...),
    filename: str = Form(""),
    parent_id: int | None = Form(None),
):
    """从公开 URL 下载文件到云盘（服务器端下载）。"""
    import urllib.request as _urllib
    import ssl as _ssl

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise BadRequestException("仅支持 http/https 链接")

    # 解析文件名
    if filename:
        filename = filename.strip()
    else:
        from pathlib import PurePath
        from urllib.parse import urlparse
        parsed = urlparse(url)
        filename = PurePath(parsed.path).name or "download"

    # 校验扩展名
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext and ext not in settings.allowed_extensions_set:
        raise BadRequestException(f"不支持的文件类型: .{ext}")

    # 验证目标目录
    if parent_id is not None:
        parent = db.get(FileItem, parent_id)
        if parent is None or parent.user_id != current_user.id or not parent.is_dir:
            raise NotFoundException("目标目录不存在")

    _check_name_conflict(db, filename, parent_id, current_user.id)

    # 下载文件
    try:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        req = _urllib.Request(url, headers={"User-Agent": "CloudDisk/1.0"})
        with _urllib.urlopen(req, timeout=30, context=ctx) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type", "")
    except Exception as e:
        raise BadRequestException(f"下载失败: {str(e)}")

    file_size = len(content)
    if file_size == 0:
        raise BadRequestException("下载的文件为空")

    # 配额检查
    _check_quota(current_user, file_size)

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size > max_bytes:
        raise BadRequestException(f"文件大小超过上限 {settings.MAX_UPLOAD_SIZE_MB} MB")

    # 推断 MIME
    mime_type = content_type.split(";")[0].strip() if content_type else _infer_mime_type(filename)
    if mime_type == "application/octet-stream":
        mime_type = _infer_mime_type(filename)

    # 存储
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    storage_path = f"{current_user.id}/{unique_name}"
    dest = _resolve_upload_path(storage_path)
    dest.write_bytes(content)

    file_item = FileItem(
        name=filename,
        storage_path=storage_path,
        file_size=file_size,
        mime_type=mime_type,
        is_dir=False,
        parent_id=parent_id,
        user_id=current_user.id,
    )
    db.add(file_item)
    current_user.storage_used += file_size
    _log(db, current_user.id, "import_url", f"从 URL 导入: {filename} ({url[:80]})")
    db.commit()
    db.refresh(file_item)

    return ApiResponse(data=FileOut.model_validate(file_item))


# ---------------------------------------------------------------------------
#  文件备注
# ---------------------------------------------------------------------------

@router.get("/{file_id}/notes", response_model=ApiResponse[list[dict]])
def get_file_notes(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int,
):
    """获取文件的备注列表。"""
    file_item = db.get(FileItem, file_id)
    if file_item is None or file_item.user_id != current_user.id:
        raise NotFoundException("文件不存在")
    notes = (
        db.query(FileNote)
        .filter(FileNote.file_id == file_id, FileNote.user_id == current_user.id)
        .order_by(FileNote.created_at.desc())
        .all()
    )
    return ApiResponse(data=[
        {"id": n.id, "content": n.content, "created_at": n.created_at.isoformat(), "updated_at": n.updated_at.isoformat()}
        for n in notes
    ])


@router.post("/{file_id}/notes", response_model=ApiResponse[dict])
def add_file_note(
    db: DbSession,
    current_user: CurrentUser,
    file_id: int,
    content: str = Form(...),
):
    """为文件添加备注。"""
    file_item = db.get(FileItem, file_id)
    if file_item is None or file_item.user_id != current_user.id:
        raise NotFoundException("文件不存在")
    if not content.strip():
        raise BadRequestException("备注内容不能为空")

    note = FileNote(file_id=file_id, user_id=current_user.id, content=content.strip())
    db.add(note)
    db.commit()
    db.refresh(note)
    return ApiResponse(data={"id": note.id, "content": note.content, "created_at": note.created_at.isoformat()})


@router.delete("/notes/{note_id}", response_model=ApiResponse)
def delete_file_note(
    db: DbSession,
    current_user: CurrentUser,
    note_id: int,
):
    """删除文件备注。"""
    note = db.get(FileNote, note_id)
    if note is None or note.user_id != current_user.id:
        raise NotFoundException("备注不存在")
    db.delete(note)
    db.commit()
    return ApiResponse(message="备注已删除")


@router.post("/search", response_model=ApiResponse[PaginatedData[FileOut]])
def search_files(
    db: DbSession,
    current_user: CurrentUser,
    body: FileSearch,
):
    """搜索文件：关键词模糊匹配 + 类型筛选 + 时间范围筛选，分页返回。"""
    page = max(body.page, 1)
    page_size = min(max(body.page_size, 1), 100)

    q = db.query(FileItem).filter(
        FileItem.user_id == current_user.id,
        FileItem.is_deleted == False,
    )

    # 关键词
    keyword = body.keyword.strip()
    if keyword:
        q = q.filter(FileItem.name.like(f"%{keyword}%"))

    # 文件类型
    file_type = body.file_type.strip().lower() if body.file_type else ""
    if file_type:
        if file_type == "other":
            q = q.filter(
                FileItem.is_dir == False,
                *[
                    ~FileItem.mime_type.like(prefix + "%")
                    for prefix in _KNOWN_OTHER_PREFIXES
                ],
                ~FileItem.mime_type.in_(_KNOWN_OTHER_EXACT),
            )
        elif file_type in _FILE_TYPE_FILTERS:
            q = q.filter(_FILE_TYPE_FILTERS[file_type])

    # 时间范围
    if body.start_time:
        q = q.filter(FileItem.created_at >= body.start_time)
    if body.end_time:
        q = q.filter(FileItem.created_at <= body.end_time)

    total = q.count()
    items = (
        q.order_by(FileItem.is_dir.desc(), FileItem.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ApiResponse(
        data=PaginatedData(
            items=[FileOut.model_validate(f) for f in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )
