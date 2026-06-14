"""FastAPI 应用入口——单文件启动，托管前端静态资源（SPA 路由回退支持）。"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import auth, files, shares, admin
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.models.base import Base
from app.models.file import FileItem
from app.core.security import hash_password
from app.models.user import User
from app.api.v1.dependencies import engine, SessionLocal

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    """自动建表，并创建默认管理员账号。"""
    Base.metadata.create_all(bind=engine)

    # 确保上传目录存在并设置安全权限
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        upload_dir.chmod(0o750)
        htaccess = upload_dir / ".htaccess"
        if not htaccess.exists():
            htaccess.write_text("Options -ExecCGI\nAddHandler cgi-script .php .pl .py .jsp .asp .sh .cgi\n")
    except (OSError, PermissionError):
        pass

    # 清理回收站中超过 30 天的文件
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    old_trash = (
        SessionLocal().query(FileItem)
        .filter(
            FileItem.is_deleted == True,
            FileItem.deleted_at <= thirty_days_ago,
        )
        .all()
    )
    if old_trash:
        for item in old_trash:
            if item.storage_path and not item.is_dir:
                try:
                    (Path(settings.UPLOAD_DIR) / item.storage_path).unlink(missing_ok=True)
                except OSError:
                    pass
            SessionLocal().delete(item)
        SessionLocal().commit()
        if old_trash:
            pass  # 清理完成

    # 清理超过 24 小时的过期分片上传临时文件
    chunk_dir = Path(settings.UPLOAD_DIR).parent / "chunks"
    if chunk_dir.exists():
        import time as _time
        cutoff = _time.time() - 86400
        for session_dir in chunk_dir.iterdir():
            try:
                if session_dir.is_dir() and session_dir.stat().st_mtime < cutoff:
                    import shutil as _shutil
                    _shutil.rmtree(session_dir, ignore_errors=True)
            except OSError:
                pass

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if admin is None:
            admin = User(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                email=settings.ADMIN_EMAIL,
                role="admin",
                storage_quota=0,  # 管理员不限空间
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# 健康检查端点
@app.get("/api/v1/health")
def health_check():
    import time as _time_module
    import platform as _platform
    from pathlib import Path as _Path
    disk = _Path(settings.UPLOAD_DIR)
    disk_usage = None
    try:
        import shutil as _shutil_module
        usage = _shutil_module.disk_usage(disk if disk.exists() else _Path("."))
        disk_usage = {"total": usage.total, "used": usage.used, "free": usage.free}
    except Exception:
        disk_usage = {"error": "unavailable"}

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "python": _platform.python_version(),
            "database": settings.DATABASE_URL.split("///")[-1] if "///" in settings.DATABASE_URL else "unknown",
            "upload_dir": str(disk),
            "disk": disk_usage,
        },
    }

# 注册 API 路由
app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(files.router, prefix="/api/v1/files", tags=["文件管理"])
app.include_router(shares.router, prefix="/api/v1/shares", tags=["分享"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["管理后台"])

# 托管前端静态资源 + SPA 路由回退
if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():

    @app.get("/")
    async def serve_root():
        return FileResponse(str(STATIC_DIR / "index.html"))

    # Catch-all：先检查是否有匹配的静态文件，否则返回 index.html（SPA 回退）
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = STATIC_DIR / full_path
        # 安全检查：防止路径遍历
        try:
            resolved = file_path.resolve()
            if not str(resolved).startswith(str(STATIC_DIR.resolve())):
                raise FileNotFoundError
        except (ValueError, OSError):
            return FileResponse(str(STATIC_DIR / "index.html"))

        if resolved.is_file():
            # 根据扩展名设置 MIME 类型
            from pathlib import PurePath
            ext_map = {
                ".html": "text/html", ".css": "text/css", ".js": "application/javascript",
                ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml",
                ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
                ".ttf": "font/ttf", ".eot": "application/vnd.ms-fontobject",
            }
            ext = PurePath(full_path).suffix.lower()
            media_type = ext_map.get(ext, "application/octet-stream")
            return FileResponse(str(resolved), media_type=media_type)

        # SPA 回退：返回 index.html
        return FileResponse(str(STATIC_DIR / "index.html"))
