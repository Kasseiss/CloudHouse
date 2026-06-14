"""Pytest fixtures — 测试数据库、客户端、用户令牌。"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 确保 backend 在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 临时覆盖数据库和上传目录到临时路径
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.gettempdir()}/test_clouddisk.db"
os.environ["UPLOAD_DIR"] = str(Path(tempfile.gettempdir()) / "test_uploads")
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest"

# 必须在覆盖环境变量之后导入 app
from app.main import app
from app.core.config import settings
from app.models.base import Base
from app.api.v1.dependencies import engine, SessionLocal


@pytest.fixture(autouse=True)
def setup_db():
    """每个测试前重建数据库表。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    yield
    # 清理
    Base.metadata.drop_all(bind=engine)
    import shutil
    if Path(settings.UPLOAD_DIR).exists():
        shutil.rmtree(settings.UPLOAD_DIR, ignore_errors=True)


@pytest.fixture
def client():
    """FastAPI TestClient。"""
    return TestClient(app)


@pytest.fixture
def db():
    """数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def admin_token(client):
    """获取管理员 JWT 令牌。"""
    from app.core.security import hash_password
    from app.models.user import User

    db = SessionLocal()
    user = User(
        username="admin",
        password_hash=hash_password("admin123"),
        email="admin@test.local",
        role="admin",
        storage_quota=0,
    )
    db.add(user)
    db.commit()
    db.close()

    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["data"]["token"]


@pytest.fixture
def user_token(client):
    """获取普通用户 JWT 令牌。"""
    client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "password": "test123456",
        "email": "test@test.local",
    })
    resp = client.post("/api/v1/auth/login", json={"username": "testuser", "password": "test123456"})
    return resp.json()["data"]["token"]
