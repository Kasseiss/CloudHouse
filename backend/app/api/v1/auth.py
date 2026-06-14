"""认证相关 API 路由：登录、注册、个人信息、修改密码。"""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.v1.dependencies import DbSession, CurrentUser
from app.core.config import settings
from app.core.exceptions import BadRequestException, UnauthorizedException
from app.core.security import verify_password, hash_password, create_access_token
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.user import UserLogin, UserRegister, UserOut, PasswordChange

router = APIRouter()


@router.post("/login", response_model=ApiResponse[dict])
def login(db: DbSession, body: UserLogin) -> ApiResponse[dict]:
    """用户登录，返回 JWT 令牌与用户信息。"""
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise UnauthorizedException("用户名或密码错误")

    if not user.is_active:
        raise UnauthorizedException("账号已被禁用，请联系管理员")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token(data={"sub": str(user.id)})
    user_data = UserOut.model_validate(user)

    return ApiResponse(
        code=0,
        message="登录成功",
        data={"token": token, "user": user_data.model_dump()},
    )


@router.post("/register", response_model=ApiResponse[dict])
def register(db: DbSession, body: UserRegister) -> ApiResponse[dict]:
    """用户注册，成功后自动登录并返回 JWT 令牌。"""
    if not settings.ALLOW_REGISTRATION:
        raise BadRequestException("当前系统不允许公开注册")

    existing = db.query(User).filter(User.username == body.username).first()
    if existing is not None:
        raise BadRequestException("用户名已被占用")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        email=body.email or "",
        role="user",
        storage_quota=1073741824,  # 1 GB
        storage_used=0,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    user_data = UserOut.model_validate(user)

    return ApiResponse(
        code=0,
        message="注册成功",
        data={"token": token, "user": user_data.model_dump()},
    )


@router.get("/profile", response_model=ApiResponse[dict])
def get_profile(current_user: CurrentUser) -> ApiResponse[dict]:
    """获取当前登录用户的个人信息。"""
    user_data = UserOut.model_validate(current_user)
    return ApiResponse(
        code=0,
        message="success",
        data=user_data.model_dump(),
    )


@router.put("/password", response_model=ApiResponse)
def change_password(
    db: DbSession,
    current_user: CurrentUser,
    body: PasswordChange,
) -> ApiResponse:
    """修改当前用户的登录密码。"""
    if not verify_password(body.old_password, current_user.password_hash):
        raise BadRequestException("原密码不正确")

    current_user.password_hash = hash_password(body.new_password)
    db.add(current_user)
    db.commit()

    return ApiResponse(
        code=0,
        message="密码修改成功",
        data=None,
    )
