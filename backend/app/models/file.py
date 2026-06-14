"""文件/文件夹模型。"""

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class FileItem(Base):
    __tablename__ = "file_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    storage_path = Column(String(512), default="")  # 服务器上的实际存储路径
    file_size = Column(Integer, default=0)  # bytes
    mime_type = Column(String(128), default="application/octet-stream")
    is_dir = Column(Boolean, default=False)
    parent_id = Column(Integer, ForeignKey("file_items.id"), nullable=True, default=None)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_accessed_at = Column(DateTime, nullable=True)

    owner = relationship("User", back_populates="files")
    shares = relationship("Share", back_populates="file", lazy="dynamic")
