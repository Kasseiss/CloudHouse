"""管理后台相关 Pydantic 模型。"""

from datetime import datetime
from pydantic import BaseModel


class SystemConfigOut(BaseModel):
    max_upload_size_mb: int
    allowed_extensions: str
    allow_registration: bool


class SystemConfigUpdate(BaseModel):
    max_upload_size_mb: int | None = None
    allowed_extensions: str | None = None
    allow_registration: bool | None = None


class UserQuotaUpdate(BaseModel):
    storage_quota: int  # bytes


class UserStatusUpdate(BaseModel):
    is_active: bool


class AdminUserCreate(BaseModel):
    username: str
    password: str
    email: str = ""
    role: str = "user"
    storage_quota: int = 1073741824


class LogOut(BaseModel):
    id: int
    user_id: int | None
    action: str
    detail: str
    ip_address: str
    created_at: datetime

    model_config = {"from_attributes": True}
