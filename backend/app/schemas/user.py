"""用户相关 Pydantic 模型。"""

from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator


class UserLogin(BaseModel):
    username: str
    password: str


class UserRegister(BaseModel):
    username: str
    password: str
    email: str = ""

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if not (3 <= len(v) <= 32):
            raise ValueError("用户名长度需在 3-32 个字符之间")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码长度不能少于 6 位")
        return v


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    storage_quota: int
    storage_used: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PasswordChange(BaseModel):
    old_password: str
    new_password: str
