"""应用核心配置，使用 pydantic-settings 读取环境变量。"""

from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    APP_NAME: str = "CloudDisk"
    APP_VERSION: str = "1.0.0"
    SECRET_KEY: str = "change-me-to-a-random-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'data' / 'database.db'}"

    UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    MAX_UPLOAD_SIZE_MB: int = 500
    ALLOWED_EXTENSIONS: str = (
        "jpg,jpeg,png,gif,bmp,webp,pdf,doc,docx,xls,xlsx,"
        "ppt,pptx,txt,zip,rar,7z,tar.gz,mp4,avi,mkv,mp3,wav,flac,bin,md,csv,json,xml,html,css,js,py"
    )

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_EMAIL: str = "admin@cloud-disk.local"

    ALLOW_REGISTRATION: bool = True

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {ext.strip().lower() for ext in self.ALLOWED_EXTENSIONS.split(",") if ext.strip()}

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
