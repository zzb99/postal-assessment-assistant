from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = "邮件处理中心考核管理系统"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./assessment.db")
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
        if origin.strip()
    )
    base_dir: Path = Path(__file__).resolve().parents[2]
    document_root: Path = Path(os.getenv("DOCUMENT_ROOT", "/data/documents"))
    document_template: Path = Path(
        os.getenv(
            "DOCUMENT_TEMPLATE",
            str(Path(__file__).resolve().parents[1] / "templates" / "assessment-notice-template-v20260819.docx"),
        )
    )
    document_template_version: str = os.getenv("DOCUMENT_TEMPLATE_VERSION", "20260819-1")
    libreoffice_binary: str = os.getenv("LIBREOFFICE_BINARY", "soffice")
    libreoffice_timeout_seconds: int = int(os.getenv("LIBREOFFICE_TIMEOUT_SECONDS", "60"))
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_api_url: str = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


settings = Settings()
