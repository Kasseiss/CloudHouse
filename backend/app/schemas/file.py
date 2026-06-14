"""文件相关 Pydantic 模型。"""

from datetime import datetime
from pydantic import BaseModel, field_validator


class FileOut(BaseModel):
    id: int
    name: str
    file_size: int
    mime_type: str
    is_dir: bool
    parent_id: int | None
    user_id: int
    is_deleted: bool
    download_count: int = 0
    last_accessed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FileRename(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 256:
            raise ValueError("文件名长度需在 1-256 个字符之间")
        if "/" in v or "\\" in v:
            raise ValueError("文件名不能包含路径分隔符")
        return v


class MkdirRequest(BaseModel):
    name: str
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 256:
            raise ValueError("文件夹名长度需在 1-256 个字符之间")
        return v


class FileMove(BaseModel):
    target_parent_id: int | None = None
    file_ids: list[int]


class FileSearch(BaseModel):
    keyword: str = ""
    file_type: str = ""  # 空表示全部，或 image/video/pdf/text/other
    start_time: datetime | None = None
    end_time: datetime | None = None
    page: int = 1
    page_size: int = 20
