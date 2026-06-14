"""FastAPI 依赖注入：数据库会话、当前用户鉴权。"""

from collections.abc import Generator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.core.security import decode_access_token
from app.models.user import User

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException("请先登录")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)
    if payload is None:
        raise UnauthorizedException("令牌无效或已过期")
    user_id = payload.get("sub")
    if user_id is None:
        raise UnauthorizedException("令牌无效")
    user = db.get(User, int(user_id))
    if user is None:
        raise UnauthorizedException("用户不存在")
    if not user.is_active:
        raise ForbiddenException("账号已被禁用")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_admin_user(current_user: CurrentUser) -> User:
    if current_user.role != "admin":
        raise ForbiddenException("需要管理员权限")
    return current_user


AdminUser = Annotated[User, Depends(get_admin_user)]
