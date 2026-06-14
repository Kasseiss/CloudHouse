"""用户模型。"""

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    email = Column(String(128), default="")
    role = Column(String(16), default="user")  # user / admin
    storage_quota = Column(Integer, default=1073741824)  # 1 GB in bytes
    storage_used = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    files = relationship("FileItem", back_populates="owner", lazy="dynamic")
    shares = relationship("Share", back_populates="owner", lazy="dynamic")
    logs = relationship("SystemLog", back_populates="user", lazy="dynamic")
