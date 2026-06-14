"""分享模型。"""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class Share(Base):
    __tablename__ = "shares"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("file_items.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code = Column(String(32), unique=True, nullable=False, index=True)
    password = Column(String(16), default="")  # 提取码，为空则不校验
    expire_at = Column(DateTime, nullable=True)  # 过期时间，为空则永不过期
    view_count = Column(Integer, default=0)
    max_downloads = Column(Integer, default=0)  # 0 = 无限
    one_time = Column(Boolean, default=False)  # 一次性分享
    require_login = Column(Boolean, default=False)  # 需要登录才能访问
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    file = relationship("FileItem", back_populates="shares")
    owner = relationship("User", back_populates="shares")
