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
            str(Path(__file__).resolve().parents[1] / "templates" / "assessment-notice-template-v20261013.docx"),
        )
    )
    document_template_version: str = os.getenv("DOCUMENT_TEMPLATE_VERSION", "20261014-1")
    libreoffice_binary: str = os.getenv("LIBREOFFICE_BINARY", "soffice")
    libreoffice_timeout_seconds: int = int(os.getenv("LIBREOFFICE_TIMEOUT_SECONDS", "60"))
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_api_url: str = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    ai_max_tokens: int = int(os.getenv("AI_MAX_TOKENS", "900"))
    ai_cache_ttl_seconds: int = int(os.getenv("AI_CACHE_TTL_SECONDS", "900"))
    ai_cache_capacity: int = int(os.getenv("AI_CACHE_CAPACITY", "256"))
    ai_error_cache_seconds: int = int(os.getenv("AI_ERROR_CACHE_SECONDS", "20"))
    ai_prompt_version: str = os.getenv("AI_PROMPT_VERSION", "short-rules-v2")
    ai_peak_hit_cny: str = os.getenv("AI_PEAK_HIT_CNY_PER_M", "0.04")
    ai_peak_miss_cny: str = os.getenv("AI_PEAK_MISS_CNY_PER_M", "2")
    ai_peak_output_cny: str = os.getenv("AI_PEAK_OUTPUT_CNY_PER_M", "8")
    ai_offpeak_hit_cny: str = os.getenv("AI_OFFPEAK_HIT_CNY_PER_M", "0.02")
    ai_offpeak_miss_cny: str = os.getenv("AI_OFFPEAK_MISS_CNY_PER_M", "1")
    ai_offpeak_output_cny: str = os.getenv("AI_OFFPEAK_OUTPUT_CNY_PER_M", "4")
    ai_price_model: str = os.getenv("AI_PRICE_MODEL", "deepseek-flash")
    ai_price_holidays: str = os.getenv("AI_PRICE_HOLIDAYS", "")
    require_trusted_device: bool = os.getenv("REQUIRE_TRUSTED_DEVICE", "false").lower() == "true"
    require_policy_approval: bool = os.getenv("REQUIRE_POLICY_APPROVAL", "false").lower() == "true"


settings = Settings()
