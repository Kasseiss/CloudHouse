@echo off
chcp 65001 >nul
echo ================================
echo   ☁ CloudDisk 私有云盘
echo ================================
echo.

cd /d "%~dp0backend"

if not exist ".env" (
    echo [*] 首次运行，创建 .env 配置文件...
    copy .env.example .env >nul
)

if not exist "static\index.html" (
    echo [!] 前端尚未构建，请先在 web 目录执行: npm install && npm run build
    echo [*] 现在仅启动后端 API 服务...
)

echo [*] 安装依赖...
pip install -r requirements.txt -q

echo [*] 启动服务...
echo.
echo   访问地址: http://localhost:8000
echo   默认账号: admin / admin123
echo   API 文档: http://localhost:8000/docs
echo.
echo   按 Ctrl+C 停止服务
echo ================================
echo.

uvicorn app.main:app --host 0.0.0.0 --port 8000
