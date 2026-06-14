"""分享相关 Pydantic 模型。"""

from datetime import datetime
from pydantic import BaseModel, field_validator


class ShareCreate(BaseModel):
    file_id: int
    password: str = ""
    expire_hours: int = 0  # 0 表示永不过期
    max_downloads: int = 0
    one_time: bool = False
    require_login: bool = False
    custom_code: str = ""


class ShareOut(BaseModel):
    id: int
    file_id: int
    code: str
    password: str
    expire_at: datetime | None
    view_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ShareAccess(BaseModel):
    code: str
    password: str = ""
