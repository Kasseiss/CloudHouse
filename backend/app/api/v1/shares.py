"""分享 API 路由：创建、公开访问、公开下载、列表、删除。"""

import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.models.file import FileItem
from app.models.share import Share
from app.models.log import SystemLog
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.share import ShareCreate, ShareOut
from app.api.v1.dependencies import DbSession, CurrentUser

router = APIRouter()


def _generate_share_code(length: int = 8) -> str:
    """生成随机的分享码（字母+数字）。"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# POST /shares  — 创建分享链接
# ---------------------------------------------------------------------------

@router.post("", response_model=ApiResponse[ShareOut])
def create_share(
    body: ShareCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """为指定文件创建一个分享链接。"""

    # 1. 校验文件存在且属于当前用户
    file_item = db.get(FileItem, body.file_id)
    if file_item is None:
        raise NotFoundException("文件不存在")
    if file_item.user_id != current_user.id:
        raise ForbiddenException("不能分享他人的文件")
    if file_item.is_deleted:
        raise BadRequestException("文件已被删除，无法分享")

    # 2. 计算过期时间：0 表示永不过期
    expire_at = None
    if body.expire_hours > 0:
        expire_at = datetime.now(timezone.utc) + timedelta(hours=body.expire_hours)
        if expire_at < datetime.now(timezone.utc):
            raise BadRequestException("过期时间不能是过去的时间")

    # 3. 生成唯一分享码
    for _ in range(10):  # 最多重试 10 次避免冲突
        code = _generate_share_code()
        existing = db.query(Share).filter(Share.code == code).first()
        if existing is None:
            break
    else:
        # 如果冲突太多，换更长码重试
        code = _generate_share_code(12)

    # 4. 写入数据库
    share = Share(
        file_id=body.file_id,
        user_id=current_user.id,
        code=code,
        password=body.password.strip() if body.password else "",
        expire_at=expire_at,
        max_downloads=getattr(body, 'max_downloads', 0) or 0,
        one_time=getattr(body, 'one_time', False) or False,
    )
    db.add(share)
    db.flush()

    # 5. 记录操作日志
    log = SystemLog(
        user_id=current_user.id,
        action="share_create",
        detail=f"创建分享：文件 ID {body.file_id}，分享码 {code}，有效期 {'永久' if expire_at is None else f'{body.expire_hours} 小时'}",
    )
    db.add(log)
    db.commit()
    db.refresh(share)

    return {"code": 0, "message": "success", "data": ShareOut.model_validate(share)}


# ---------------------------------------------------------------------------
# GET /shares/{code}  — 公开访问分享（无需登录）
# ---------------------------------------------------------------------------

@router.get("/{code}", response_model=ApiResponse[dict])
def access_share(
    code: str,
    db: DbSession,
    password: str = Query(default="", description="提取码"),
) -> dict:
    """通过分享码公开访问一个已分享的文件。"""

    share = db.query(Share).options(joinedload(Share.file)).filter(Share.code == code).first()
    if share is None:
        raise NotFoundException("分享不存在或已被删除")

    # 检查是否过期
    if share.expire_at is not None and share.expire_at < datetime.now(timezone.utc):
        raise BadRequestException("分享已过期")

    # 校验提取码
    if share.password and share.password != password:
        raise BadRequestException("提取码错误")

    # 检查源文件是否还存在
    if share.file is None or share.file.is_deleted:
        raise NotFoundException("原文件已被删除")

    # 增加浏览次数
    share.view_count += 1

    # 一次性分享：访问后自动删除
    if share.one_time:
        db.delete(share)
        db.commit()
        data = {
            "share": {**ShareOut.model_validate(share).model_dump(), "one_time": True, "max_downloads": 0, "downloads_remaining": 0},
            "file": None,
            "children": [],
        }
        return {"code": 0, "message": "这是一次性分享，链接已失效", "data": data}

    db.commit()

    # 如果是文件夹，返回其内容列表
    children = []
    if share.file.is_dir:
        child_items = (
            db.query(FileItem)
            .filter(
                FileItem.parent_id == share.file.id,
                FileItem.is_deleted == False,
            )
            .order_by(FileItem.is_dir.desc(), FileItem.name.asc())
            .all()
        )
        children = [
            {
                "id": c.id,
                "name": c.name,
                "file_size": c.file_size,
                "mime_type": c.mime_type,
                "is_dir": c.is_dir,
                "created_at": c.created_at.isoformat(),
            }
            for c in child_items
        ]

    data = {
        "share": {
            **ShareOut.model_validate(share).model_dump(),
            "max_downloads": share.max_downloads,
            "downloads_remaining": share.max_downloads - share.view_count if share.max_downloads > 0 else -1,
        },
        "file": {
            "id": share.file.id,
            "name": share.file.name,
            "file_size": share.file.file_size,
            "mime_type": share.file.mime_type,
            "is_dir": share.file.is_dir,
            "created_at": share.file.created_at.isoformat(),
        },
        "children": children,
    }
    return {"code": 0, "message": "success", "data": data}


# ---------------------------------------------------------------------------
# GET /shares/{code}/download  — 公开下载分享文件（无需登录）
# ---------------------------------------------------------------------------

@router.get("/{code}/download-all")
def download_shared_folder(
    code: str,
    db: DbSession,
    password: str = Query(default="", description="提取码"),
):
    """将分享文件夹的所有内容打包为 ZIP 下载（无需登录）。"""
    import io as _io
    import zipfile as _zipfile

    share = db.query(Share).options(joinedload(Share.file)).filter(Share.code == code).first()
    if share is None:
        raise NotFoundException("分享不存在或已被删除")
    if share.expire_at is not None and share.expire_at < datetime.now(timezone.utc):
        raise BadRequestException("分享已过期")
    if share.password and share.password != password:
        raise BadRequestException("提取码错误")
    if share.file is None or share.file.is_deleted:
        raise NotFoundException("原文件已被删除")
    if not share.file.is_dir:
        raise BadRequestException("仅文件夹支持打包下载")

    # 收集所有文件
    def collect_files(folder_id: int) -> list[FileItem]:
        results = []
        children = db.query(FileItem).filter(
            FileItem.parent_id == folder_id, FileItem.is_deleted == False
        ).all()
        for child in children:
            if child.is_dir:
                results.extend(collect_files(child.id))
            elif child.storage_path:
                results.append(child)
        return results

    all_files = collect_files(share.file.id)
    if not all_files:
        raise BadRequestException("文件夹为空")

    # 下载限制检查
    if share.max_downloads > 0 and share.view_count >= share.max_downloads:
        raise BadRequestException("该分享已达到下载次数上限")
    share.view_count += 1
    db.commit()

    buf = _io.BytesIO()
    seen_names: dict[str, int] = {}
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        for item in all_files:
            disk_path = Path(settings.UPLOAD_DIR) / item.storage_path
            if not disk_path.exists():
                continue
            name = item.name
            if name in seen_names:
                seen_names[name] += 1
                base, ext = os.path.splitext(name)
                name = f"{base} ({seen_names[name]}){ext}"
            else:
                seen_names[name] = 0
            zf.write(str(disk_path), arcname=name)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={share.file.name}.zip"},
    )


@router.get("/{code}/download")
def download_shared_file(
    code: str,
    db: DbSession,
    password: str = Query(default="", description="提取码"),
    child_id: int | None = Query(None, description="分享文件夹时，指定下载的子文件ID"),
):
    """通过分享码公开下载文件（无需登录）。支持分享文件夹内的子文件下载。"""
    share = db.query(Share).options(joinedload(Share.file)).filter(Share.code == code).first()
    if share is None:
        raise NotFoundException("分享不存在或已被删除")

    if share.expire_at is not None and share.expire_at < datetime.now(timezone.utc):
        raise BadRequestException("分享已过期")

    if share.password and share.password != password:
        raise BadRequestException("提取码错误")

    if share.file is None or share.file.is_deleted:
        raise NotFoundException("原文件已被删除")

    # 确定要下载的文件
    target_file = share.file
    if child_id is not None:
        child = db.get(FileItem, child_id)
        if child is None or child.is_deleted or child.is_dir:
            raise NotFoundException("文件不存在")
        # 验证子文件确实在分享的文件夹内
        if share.file.is_dir and child.parent_id == share.file.id:
            target_file = child
        else:
            raise ForbiddenException("无权访问该文件")

    if target_file.is_dir:
        raise BadRequestException("不能下载文件夹")

    file_path = Path(settings.UPLOAD_DIR) / target_file.storage_path
    if not file_path.exists():
        raise NotFoundException("文件在服务器上不存在")

    # 下载次数限制检查
    if share.max_downloads > 0 and share.view_count >= share.max_downloads:
        raise BadRequestException("该分享已达到下载次数上限")

    share.view_count += 1
    db.commit()

    encoded = quote(target_file.name)
    return FileResponse(
        path=str(file_path),
        filename=target_file.name,
        media_type=target_file.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        },
    )


# ---------------------------------------------------------------------------
# GET /shares  — 我的分享列表
# ---------------------------------------------------------------------------

@router.get("", response_model=ApiResponse[PaginatedData[ShareOut]])
def list_my_shares(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
) -> dict:
    """获取当前用户创建的所有分享链接。"""

    query = db.query(Share).filter(Share.user_id == current_user.id)
    total = query.count()
    shares = (
        query.order_by(Share.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    data = PaginatedData(
        items=[ShareOut.model_validate(s) for s in shares],
        total=total,
        page=page,
        page_size=page_size,
    )
    return {"code": 0, "message": "success", "data": data}


# ---------------------------------------------------------------------------
# DELETE /shares/{id}  — 删除分享链接
# ---------------------------------------------------------------------------

@router.delete("/{id}", response_model=ApiResponse[None])
def delete_share(
    id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """删除一个分享链接。仅创建者或管理员可删除。"""

    share = db.get(Share, id)
    if share is None:
        raise NotFoundException("分享不存在或已被删除")

    if share.user_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException("只能删除自己创建的分享")

    # 记录操作日志
    log = SystemLog(
        user_id=current_user.id,
        action="share_delete",
        detail=f"删除分享：ID {id}，分享码 {share.code}，文件 ID {share.file_id}",
    )
    db.add(log)
    db.delete(share)
    db.commit()

    return {"code": 0, "message": "success", "data": None}
