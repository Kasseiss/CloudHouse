# ☁ CloudDisk - 私有云盘系统

基于 FastAPI + SQLite + React 的轻量级私有云盘，单服务运行，零额外中间件依赖。

## 功能特性

### 用户端
- 📁 文件/文件夹上传（支持拖拽、进度显示）
- 📥 文件下载、在线预览（图片、视频、PDF、文本）
- 📂 目录管理：新建文件夹、重命名、移动、删除
- 🗑 回收站机制：软删除、可恢复、永久删除
- 🔍 文件搜索（按名称、类型、时间筛选）
- 📊 个人存储空间统计

### 分享功能
- 🔗 生成公开分享链接，支持提取码、有效期
- 📋 分享记录管理、一键取消分享
- 👁 分享访问次数统计

### 管理后台
- 👥 用户全生命周期管理（增删改查、启用/禁用）
- 💾 单用户存储空间配额设置
- 📝 系统操作日志审计
- ⚙ 系统配置：上传大小限制、文件类型白名单、注册开关

## 快速启动

### 方式一：裸机运行（Python 3.10+）

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000

### 方式二：Docker 一键部署

```bash
docker-compose up -d
```

### 默认账号
- 用户名：`admin`
- 密码：`admin123`

## 项目结构

```
cloud-disk/
├── backend/
│   ├── app/
│   │   ├── api/v1/        # 路由层 (auth, files, shares, admin)
│   │   ├── core/           # 配置、安全、异常
│   │   ├── models/         # SQLAlchemy 模型
│   │   ├── schemas/        # Pydantic 模型
│   │   ├── services/       # 业务逻辑
│   │   └── main.py         # 入口，托管前端
│   ├── data/               # 数据库 + 上传文件
│   ├── static/             # 前端构建产物
│   └── requirements.txt
├── web/                    # React 前端
│   ├── src/
│   │   ├── api/            # API 请求封装
│   │   ├── components/     # 公共组件
│   │   ├── pages/          # 页面组件
│   │   └── store/          # 状态管理
│   └── package.json
├── docker-compose.yml
└── README.md
```

## API 文档

启动服务后访问 http://localhost:8000/docs 查看 FastAPI 自动生成的接口文档。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI |
| 数据库 | SQLite + SQLAlchemy 2.0 |
| 认证 | JWT + bcrypt |
| 前端 | React + TypeScript + Vite + Ant Design |
| 部署 | Docker / 裸机 |

## 环境变量

参考 `backend/.env.example`，可通过 `.env` 文件或环境变量配置。
