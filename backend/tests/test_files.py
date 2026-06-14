"""文件管理模块测试。"""

import io


class TestFiles:
    def test_list_root_empty(self, client, user_token):
        """根目录初始为空。"""
        resp = client.get("/api/v1/files", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_mkdir_and_list(self, client, user_token):
        """创建文件夹后可在列表中看到。"""
        resp = client.post("/api/v1/files/mkdir", json={"name": "MyDocs"},
                           headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        folder_id = resp.json()["data"]["id"]

        resp2 = client.get("/api/v1/files", headers={"Authorization": f"Bearer {user_token}"})
        items = resp2.json()["data"]
        assert len(items) == 1
        assert items[0]["name"] == "MyDocs"
        assert items[0]["is_dir"] is True

    def test_upload_file(self, client, user_token):
        """上传文件成功。"""
        resp = client.post("/api/v1/files/upload",
                           files={"file": ("hello.txt", io.BytesIO(b"Hello World"), "text/plain")},
                           headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "hello.txt"
        assert data["file_size"] == 11
        assert data["mime_type"] == "text/plain"

    def test_upload_to_folder(self, client, user_token):
        """上传文件到指定文件夹。"""
        mkdir_resp = client.post("/api/v1/files/mkdir", json={"name": "Uploads"},
                                 headers={"Authorization": f"Bearer {user_token}"})
        folder_id = mkdir_resp.json()["data"]["id"]

        resp = client.post("/api/v1/files/upload",
                           files={"file": ("data.txt", io.BytesIO(b"data"), "text/plain")},
                           data={"parent_id": str(folder_id)},
                           headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["parent_id"] == folder_id

    def test_rename(self, client, user_token):
        """重命名文件。"""
        mkdir_resp = client.post("/api/v1/files/mkdir", json={"name": "OldName"},
                                 headers={"Authorization": f"Bearer {user_token}"})
        file_id = mkdir_resp.json()["data"]["id"]

        resp = client.put(f"/api/v1/files/{file_id}/rename", json={"name": "NewName"},
                          headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "NewName"

    def test_delete_and_trash(self, client, user_token):
        """删除文件进入回收站。"""
        mkdir_resp = client.post("/api/v1/files/mkdir", json={"name": "ToDelete"},
                                 headers={"Authorization": f"Bearer {user_token}"})
        file_id = mkdir_resp.json()["data"]["id"]

        # 删除
        del_resp = client.delete(f"/api/v1/files/{file_id}",
                                 headers={"Authorization": f"Bearer {user_token}"})
        assert del_resp.status_code == 200

        # 根目录看不到了
        list_resp = client.get("/api/v1/files", headers={"Authorization": f"Bearer {user_token}"})
        assert len(list_resp.json()["data"]) == 0

        # 回收站可见
        trash_resp = client.get("/api/v1/files/trash", headers={"Authorization": f"Bearer {user_token}"})
        assert len(trash_resp.json()["data"]) == 1

    def test_restore(self, client, user_token):
        """从回收站恢复文件。"""
        mkdir_resp = client.post("/api/v1/files/mkdir", json={"name": "RestoreMe"},
                                 headers={"Authorization": f"Bearer {user_token}"})
        file_id = mkdir_resp.json()["data"]["id"]

        client.delete(f"/api/v1/files/{file_id}", headers={"Authorization": f"Bearer {user_token}"})
        client.post(f"/api/v1/files/{file_id}/restore", headers={"Authorization": f"Bearer {user_token}"})

        resp = client.get("/api/v1/files", headers={"Authorization": f"Bearer {user_token}"})
        assert len(resp.json()["data"]) == 1

    def test_copy(self, client, user_token):
        """复制文件生成副本。"""
        mkdir_resp = client.post("/api/v1/files/mkdir", json={"name": "Original"},
                                 headers={"Authorization": f"Bearer {user_token}"})
        file_id = mkdir_resp.json()["data"]["id"]

        resp = client.post(f"/api/v1/files/{file_id}/copy",
                           headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert "副本" in resp.json()["data"]["name"]

        # 现在有两个文件
        list_resp = client.get("/api/v1/files", headers={"Authorization": f"Bearer {user_token}"})
        assert len(list_resp.json()["data"]) == 2

    def test_tree(self, client, user_token):
        """目录树返回正确结构。"""
        client.post("/api/v1/files/mkdir", json={"name": "Docs"},
                    headers={"Authorization": f"Bearer {user_token}"})
        client.post("/api/v1/files/mkdir", json={"name": "Pics"},
                    headers={"Authorization": f"Bearer {user_token}"})

        resp = client.get("/api/v1/files/tree", headers={"Authorization": f"Bearer {user_token}"})
        nodes = resp.json()["data"]
        names = {n["name"] for n in nodes}
        assert names == {"Docs", "Pics"}

    def test_search(self, client, user_token):
        """搜索文件。"""
        client.post("/api/v1/files/upload",
                    files={"file": ("report.pdf", io.BytesIO(b"pdf data"), "application/pdf")},
                    headers={"Authorization": f"Bearer {user_token}"})
        client.post("/api/v1/files/upload",
                    files={"file": ("photo.jpg", io.BytesIO(b"jpg data"), "image/jpeg")},
                    headers={"Authorization": f"Bearer {user_token}"})

        resp = client.post("/api/v1/files/search", json={"keyword": "report"},
                           headers={"Authorization": f"Bearer {user_token}"})
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["name"] == "report.pdf"

    def test_quota_enforcement(self, client, user_token):
        """配额检查：超配额上传失败。"""
        # 用户默认配额 1GB，上传一个超限文件应被拦截
        # 先修改配额到极小值
        from app.api.v1.dependencies import SessionLocal
        from app.models.user import User
        db = SessionLocal()
        user = db.query(User).filter(User.username == "testuser").first()
        user.storage_quota = 5  # 5 bytes
        db.commit()
        db.close()

        resp = client.post("/api/v1/files/upload",
                           files={"file": ("big.txt", io.BytesIO(b"Hello World!"), "text/plain")},
                           headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 413  # QuotaExceeded

    def test_chunked_upload(self, client, user_token):
        """分片上传大文件。"""
        # 生成 2 个分片的测试数据
        chunk_size = 1024 * 1024  # 1 MB
        data = b"A" * (chunk_size + 500)  # 1MB + 500 bytes, 2 chunks
        filename = "chunked_test.txt"
        total_chunks = 2

        # 1. Init
        init_resp = client.post("/api/v1/files/upload/chunk/init",
            data={"filename": filename, "total_size": str(len(data)),
                  "total_chunks": str(total_chunks)},
            headers={"Authorization": f"Bearer {user_token}"})
        assert init_resp.status_code == 200
        upload_id = init_resp.json()["data"]["upload_id"]

        # 2. Upload chunks
        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, len(data))
            chunk_resp = client.post(
                f"/api/v1/files/upload/chunk/{upload_id}",
                data={"chunk_index": str(i)},
                files={"chunk": (f"chunk_{i}", data[start:end], "application/octet-stream")},
                headers={"Authorization": f"Bearer {user_token}"})
            assert chunk_resp.status_code == 200

        # 3. Complete
        complete_resp = client.post(
            f"/api/v1/files/upload/chunk/{upload_id}/complete",
            headers={"Authorization": f"Bearer {user_token}"})
        assert complete_resp.status_code == 200
        result = complete_resp.json()["data"]
        assert result["name"] == filename
        assert result["file_size"] == len(data)

        # 验证文件在列表中
        list_resp = client.get("/api/v1/files", headers={"Authorization": f"Bearer {user_token}"})
        assert any(f["name"] == filename for f in list_resp.json()["data"])

    def test_batch_download(self, client, user_token):
        """批量下载打包为 ZIP。"""
        # 上传两个文件
        client.post("/api/v1/files/upload",
                    files={"file": ("a.txt", io.BytesIO(b"aaa"), "text/plain")},
                    headers={"Authorization": f"Bearer {user_token}"})
        client.post("/api/v1/files/upload",
                    files={"file": ("b.txt", io.BytesIO(b"bbb"), "text/plain")},
                    headers={"Authorization": f"Bearer {user_token}"})

        # 获取文件 ID
        list_resp = client.get("/api/v1/files", headers={"Authorization": f"Bearer {user_token}"})
        file_ids = [f["id"] for f in list_resp.json()["data"] if not f["is_dir"]]

        # 批量下载
        resp = client.post("/api/v1/files/batch-download", json=file_ids,
                           headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert len(resp.content) > 0  # 有内容

    def test_empty_trash(self, client, user_token):
        """一键清空回收站。"""
        # 创建并删除两个文件
        for name in ("del1.txt", "del2.txt"):
            up = client.post("/api/v1/files/upload",
                             files={"file": (name, io.BytesIO(b"x"), "text/plain")},
                             headers={"Authorization": f"Bearer {user_token}"})
            fid = up.json()["data"]["id"]
            client.delete(f"/api/v1/files/{fid}", headers={"Authorization": f"Bearer {user_token}"})

        # 确认回收站有 2 个
        trash = client.get("/api/v1/files/trash", headers={"Authorization": f"Bearer {user_token}"})
        assert len(trash.json()["data"]) == 2

        # 清空
        resp = client.post("/api/v1/files/trash/empty", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted_count"] == 2

        # 确认回收站为空
        trash2 = client.get("/api/v1/files/trash", headers={"Authorization": f"Bearer {user_token}"})
        assert len(trash2.json()["data"]) == 0

    def test_recent_activity(self, client, user_token):
        """最近操作记录。"""
        # 做几个操作
        client.post("/api/v1/files/mkdir", json={"name": "TestDir"},
                    headers={"Authorization": f"Bearer {user_token}"})
        client.post("/api/v1/files/upload",
                    files={"file": ("log.txt", io.BytesIO(b"test"), "text/plain")},
                    headers={"Authorization": f"Bearer {user_token}"})

        # 获取活动日志
        resp = client.get("/api/v1/files/activity", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert len(items) >= 2
        actions = [item["action"] for item in items]
        assert "upload" in actions
        assert "mkdir" in actions

    def test_recent_files(self, client, user_token):
        """最近访问文件记录。"""
        # 上传文件
        up = client.post("/api/v1/files/upload",
                         files={"file": ("recent.txt", io.BytesIO(b"recent"), "text/plain")},
                         headers={"Authorization": f"Bearer {user_token}"})
        fid = up.json()["data"]["id"]

        # 预览（记录访问）
        client.get(f"/api/v1/files/{fid}/preview", headers={"Authorization": f"Bearer {user_token}"})

        # 查最近
        resp = client.get("/api/v1/files/recent", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        items = resp.json()["data"]
        names = [f["name"] for f in items]
        assert "recent.txt" in names

    def test_file_notes(self, client, user_token):
        """文件备注 CRUD。"""
        up = client.post("/api/v1/files/upload",
                         files={"file": ("noted.txt", io.BytesIO(b"test"), "text/plain")},
                         headers={"Authorization": f"Bearer {user_token}"})
        fid = up.json()["data"]["id"]

        # 添加备注
        add = client.post(f"/api/v1/files/{fid}/notes",
                          data={"content": "这是一个重要文件"},
                          headers={"Authorization": f"Bearer {user_token}"})
        assert add.status_code == 200
        note_id = add.json()["data"]["id"]

        # 获取备注
        get = client.get(f"/api/v1/files/{fid}/notes",
                         headers={"Authorization": f"Bearer {user_token}"})
        assert get.status_code == 200
        assert len(get.json()["data"]) == 1
        assert get.json()["data"][0]["content"] == "这是一个重要文件"

        # 删除备注
        delete = client.delete(f"/api/v1/files/notes/{note_id}",
                              headers={"Authorization": f"Bearer {user_token}"})
        assert delete.status_code == 200

        # 确认已删除
        get2 = client.get(f"/api/v1/files/{fid}/notes",
                          headers={"Authorization": f"Bearer {user_token}"})
        assert len(get2.json()["data"]) == 0

    def test_import_url_invalid(self, client, user_token):
        """URL导入：无效URL应失败。"""
        resp = client.post("/api/v1/files/import-url",
                          data={"url": "not-a-url", "filename": "test.txt"},
                          headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 400

    def test_batch_rename(self, client, user_token):
        """批量重命名。"""
        # 上传两个文件
        ids = []
        for name in ("a.txt", "b.txt"):
            up = client.post("/api/v1/files/upload",
                             files={"file": (name, io.BytesIO(b"x"), "text/plain")},
                             headers={"Authorization": f"Bearer {user_token}"})
            ids.append(str(up.json()["data"]["id"]))

        # 批量重命名
        resp = client.post("/api/v1/files/batch-rename",
                          data={"pattern": "doc_{n}{ext}", "file_ids": ",".join(ids)},
                          headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["renamed_count"] == 2

        # 验证文件名
        lst = client.get("/api/v1/files", headers={"Authorization": f"Bearer {user_token}"})
        names = [f["name"] for f in lst.json()["data"]]
        assert "doc_1.txt" in names
        assert "doc_2.txt" in names

    def test_touch_file(self, client, user_token):
        """新建文本文件。"""
        resp = client.post("/api/v1/files/touch",
                          data={"name": "readme.txt", "content": "# Hello"},
                          headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "readme.txt"
        assert resp.json()["data"]["file_size"] > 0
