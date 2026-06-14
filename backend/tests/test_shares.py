"""分享模块测试。"""

import io


class TestShares:
    def test_create_share(self, client, user_token):
        """创建分享链接成功。"""
        upload = client.post("/api/v1/files/upload",
                             files={"file": ("secret.txt", io.BytesIO(b"secret"), "text/plain")},
                             headers={"Authorization": f"Bearer {user_token}"})
        file_id = upload.json()["data"]["id"]

        resp = client.post("/api/v1/shares", json={"file_id": file_id, "password": "123", "expire_hours": 24},
                           headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["code"]) == 8
        assert data["password"] == "123"

    def test_access_share_wrong_password(self, client, user_token):
        """提取码错误无法访问。"""
        upload = client.post("/api/v1/files/upload",
                             files={"file": ("file.txt", io.BytesIO(b"data"), "text/plain")},
                             headers={"Authorization": f"Bearer {user_token}"})
        file_id = upload.json()["data"]["id"]

        share = client.post("/api/v1/shares", json={"file_id": file_id, "password": "correct"},
                           headers={"Authorization": f"Bearer {user_token}"})
        code = share.json()["data"]["code"]

        resp = client.get(f"/api/v1/shares/{code}?password=wrong")
        assert resp.status_code == 400

    def test_access_share_correct_password(self, client, user_token):
        """正确提取码可以访问。"""
        upload = client.post("/api/v1/files/upload",
                             files={"file": ("public.txt", io.BytesIO(b"hello"), "text/plain")},
                             headers={"Authorization": f"Bearer {user_token}"})
        file_id = upload.json()["data"]["id"]

        share = client.post("/api/v1/shares", json={"file_id": file_id, "password": "pw"},
                           headers={"Authorization": f"Bearer {user_token}"})
        code = share.json()["data"]["code"]

        resp = client.get(f"/api/v1/shares/{code}?password=pw")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["file"]["name"] == "public.txt"
        assert data["share"]["view_count"] >= 1

    def test_share_folder(self, client, user_token):
        """分享文件夹。"""
        mkdir = client.post("/api/v1/files/mkdir", json={"name": "SharedFolder"},
                           headers={"Authorization": f"Bearer {user_token}"})
        folder_id = mkdir.json()["data"]["id"]

        resp = client.post("/api/v1/shares", json={"file_id": folder_id},
                           headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        code = resp.json()["data"]["code"]

        access = client.get(f"/api/v1/shares/{code}")
        assert access.status_code == 200
        assert access.json()["data"]["file"]["is_dir"] is True

    def test_list_my_shares(self, client, user_token):
        """查看我的分享列表。"""
        upload = client.post("/api/v1/files/upload",
                             files={"file": ("f.txt", io.BytesIO(b"x"), "text/plain")},
                             headers={"Authorization": f"Bearer {user_token}"})
        file_id = upload.json()["data"]["id"]
        client.post("/api/v1/shares", json={"file_id": file_id},
                    headers={"Authorization": f"Bearer {user_token}"})

        resp = client.get("/api/v1/shares", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    def test_delete_share(self, client, user_token):
        """删除分享链接。"""
        upload = client.post("/api/v1/files/upload",
                             files={"file": ("del.txt", io.BytesIO(b"x"), "text/plain")},
                             headers={"Authorization": f"Bearer {user_token}"})
        file_id = upload.json()["data"]["id"]
        share = client.post("/api/v1/shares", json={"file_id": file_id},
                           headers={"Authorization": f"Bearer {user_token}"})
        share_id = share.json()["data"]["id"]

        resp = client.delete(f"/api/v1/shares/{share_id}",
                            headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200

        # 确认已删除
        list_resp = client.get("/api/v1/shares", headers={"Authorization": f"Bearer {user_token}"})
        assert list_resp.json()["data"]["total"] == 0
