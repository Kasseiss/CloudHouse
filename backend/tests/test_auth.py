"""认证模块测试。"""


class TestAuth:
    def test_login_success(self, client):
        """管理员登录成功。"""
        from app.core.security import hash_password
        from app.models.user import User
        from app.api.v1.dependencies import SessionLocal

        db = SessionLocal()
        db.add(User(username="admin", password_hash=hash_password("admin123"), role="admin"))
        db.commit()
        db.close()

        resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "token" in data["data"]
        assert data["data"]["user"]["username"] == "admin"

    def test_login_wrong_password(self, client):
        """错误密码返回 401。"""
        from app.core.security import hash_password
        from app.models.user import User
        from app.api.v1.dependencies import SessionLocal

        db = SessionLocal()
        db.add(User(username="admin", password_hash=hash_password("admin123"), role="admin"))
        db.commit()
        db.close()

        resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    def test_register_success(self, client):
        """注册成功返回令牌。"""
        resp = client.post("/api/v1/auth/register", json={
            "username": "newuser", "password": "pass123456", "email": "new@test.com"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "token" in data["data"]

    def test_register_duplicate(self, client):
        """重复用户名注册失败。"""
        client.post("/api/v1/auth/register", json={"username": "dup", "password": "pass123456"})
        resp = client.post("/api/v1/auth/register", json={"username": "dup", "password": "pass123456"})
        assert resp.status_code == 400

    def test_profile_authenticated(self, client, user_token):
        """已登录用户获取个人信息。"""
        resp = client.get("/api/v1/auth/profile", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "testuser"

    def test_profile_unauthenticated(self, client):
        """未登录获取个人信息返回 401。"""
        resp = client.get("/api/v1/auth/profile")
        assert resp.status_code == 401

    def test_change_password(self, client, user_token):
        """修改密码成功。"""
        resp = client.put("/api/v1/auth/password", json={
            "old_password": "test123456", "new_password": "newpass123"
        }, headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200

        # 用旧密码登录应失败
        resp2 = client.post("/api/v1/auth/login", json={"username": "testuser", "password": "test123456"})
        assert resp2.status_code == 401

        # 用新密码登录应成功
        resp3 = client.post("/api/v1/auth/login", json={"username": "testuser", "password": "newpass123"})
        assert resp3.status_code == 200
