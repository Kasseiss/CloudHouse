"""认证服务：登录、注册、个人资料、修改密码。"""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password, hash_password, create_access_token
from app.core.exceptions import (
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    QuotaExceededException,
)
from app.models.user import User
from app.schemas.user import UserLogin, UserRegister, UserOut, PasswordChange


def login(db: Session, data: UserLogin) -> dict:
    """用户登录，返回 JWT 令牌与用户信息。"""
    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        raise UnauthorizedException("用户名或密码错误")
    if not user.is_active:
        raise ForbiddenException("账号已被禁用，请联系管理员")
    if not verify_password(data.password, user.password_hash):
        raise UnauthorizedException("用户名或密码错误")

    token = create_access_token(data={"sub": str(user.id)})
    user_out = UserOut.model_validate(user)
    return {"token": token, "user": user_out.model_dump()}


def register(db: Session, data: UserRegister) -> UserOut:
    """注册新用户。"""
    if not settings.ALLOW_REGISTRATION:
        raise ForbiddenException("当前系统不允许公开注册")

    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise BadRequestException("用户名已被占用")

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        email=data.email or "",
        role="user",
        storage_quota=1073741824,  # 默认 1 GB
        storage_used=0,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


def get_profile(current_user: User) -> UserOut:
    """获取当前登录用户的个人资料。"""
    return UserOut.model_validate(current_user)


def change_password(db: Session, current_user: User, data: PasswordChange) -> None:
    """修改当前用户密码。"""
    if not verify_password(data.old_password, current_user.password_hash):
        raise BadRequestException("原密码错误")

    if len(data.new_password) < 6:
        raise BadRequestException("新密码长度不能少于 6 位")

    if data.old_password == data.new_password:
        raise BadRequestException("新密码不能与原密码相同")

    current_user.password_hash = hash_password(data.new_password)
    db.add(current_user)
    db.commit()
