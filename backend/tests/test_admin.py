"""管理后台模块测试。"""

import io


class TestAdmin:
    def test_list_users(self, client, admin_token):
        """管理员查看用户列表。"""
        resp = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1  # 至少包含 admin

    def test_non_admin_denied(self, client, user_token):
        """普通用户无法访问管理员接口。"""
        resp = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 403

    def test_create_user(self, client, admin_token):
        """管理员创建用户。"""
        resp = client.post("/api/v1/admin/users", json={
            "username": "created_by_admin",
            "password": "pass123456",
            "email": "created@test.com",
            "role": "user",
            "storage_quota": 536870912,  # 512 MB
        }, headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "created_by_admin"
        assert resp.json()["data"]["storage_quota"] == 536870912

    def test_update_quota(self, client, admin_token):
        """修改用户配额。"""
        # 先创建用户
        create = client.post("/api/v1/admin/users", json={
            "username": "quota_user", "password": "pass123456", "role": "user"
        }, headers={"Authorization": f"Bearer {admin_token}"})
        user_id = create.json()["data"]["id"]

        resp = client.put(f"/api/v1/admin/users/{user_id}/quota",
                          json={"storage_quota": 1048576},  # 1 MB
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["storage_quota"] == 1048576

    def test_toggle_status(self, client, admin_token):
        """启用/禁用用户。"""
        create = client.post("/api/v1/admin/users", json={
            "username": "status_user", "password": "pass123456", "role": "user"
        }, headers={"Authorization": f"Bearer {admin_token}"})
        user_id = create.json()["data"]["id"]

        # 禁用
        resp = client.put(f"/api/v1/admin/users/{user_id}/status",
                          json={"is_active": False},
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False

        # 该用户无法登录
        login_resp = client.post("/api/v1/auth/login",
                                 json={"username": "status_user", "password": "pass123456"})
        assert login_resp.status_code == 401

    def test_delete_user(self, client, admin_token):
        """管理员删除用户。"""
        create = client.post("/api/v1/admin/users", json={
            "username": "to_delete", "password": "pass123456", "role": "user"
        }, headers={"Authorization": f"Bearer {admin_token}"})
        user_id = create.json()["data"]["id"]

        resp = client.delete(f"/api/v1/admin/users/{user_id}",
                            headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    def test_system_logs(self, client, admin_token):
        """查看系统日志。"""
        resp = client.get("/api/v1/admin/logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        assert "items" in resp.json()["data"]

    def test_system_config(self, client, admin_token):
        """获取和更新系统配置。"""
        get_resp = client.get("/api/v1/admin/config",
                              headers={"Authorization": f"Bearer {admin_token}"})
        assert get_resp.status_code == 200
        assert "max_upload_size_mb" in get_resp.json()["data"]

        put_resp = client.put("/api/v1/admin/config",
                              json={"max_upload_size_mb": 100},
                              headers={"Authorization": f"Bearer {admin_token}"})
        assert put_resp.status_code == 200
        assert put_resp.json()["data"]["max_upload_size_mb"] == 100

    def test_dashboard(self, client, admin_token):
        """仪表盘统计数据。"""
        resp = client.get("/api/v1/admin/dashboard",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_users" in data
        assert "total_files" in data
        assert "total_shares" in data

    def test_trash_cleanup(self, client, admin_token):
        """管理员手动触发回收站清理。"""
        resp = client.post("/api/v1/admin/trash/cleanup?days=1",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        assert "cleaned" in resp.json()["data"]

    def test_health_check(self, client):
        """健康检查端点无需认证。"""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["app"] == "CloudDisk"
        assert "version" in data
