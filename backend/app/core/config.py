import os
from pathlib import Path
from dotenv import load_dotenv

from app.core.network import detect_lan_ip

# 首次运行时自动从 .env.example 创建 .env
_env_path = Path(__file__).parent.parent.parent / ".env"
if not _env_path.exists():
    _example_path = _env_path.with_name(".env.example")
    if _example_path.exists():
        import shutil
        shutil.copyfile(_example_path, _env_path)
        print(f"[setup] 已从 .env.example 自动创建 .env，请按需修改配置")

load_dotenv()


class Settings:
    DB_HOST: str = os.getenv("DB_HOST", "bj-cdb-mcxp1yss.sql.tencentcdb.com")
    DB_PORT: int = int(os.getenv("DB_PORT", "23196"))
    DB_USER: str = os.getenv("DB_USER", "zbl")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "zbl123456")
    DB_NAME: str = os.getenv("DB_NAME", "carmate")

    JWT_SECRET: str = os.getenv("JWT_SECRET", "carmate-dev-secret-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "72"))

    CODE_TTL_SECONDS: int = int(os.getenv("CODE_TTL_SECONDS", "300"))

    WECHAT_MOCK_ENABLED: bool = os.getenv("WECHAT_MOCK_ENABLED", "true").lower() == "true"
    WECHAT_SESSION_TTL_SECONDS: int = int(os.getenv("WECHAT_SESSION_TTL_SECONDS", "300"))
    WECHAT_CONFIRM_BASE_URL: str = os.getenv("WECHAT_CONFIRM_BASE_URL", "")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # ── AlertAgent ──
    ALERT_AGENT_ENABLED: bool = os.getenv("ALERT_AGENT_ENABLED", "true").lower() == "true"
    ALERT_DEDUP_WINDOW_SECONDS: int = int(os.getenv("ALERT_DEDUP_WINDOW_SECONDS", "300"))
    ALERT_MIN_INTERVAL_SECONDS: int = int(os.getenv("ALERT_MIN_INTERVAL_SECONDS", "60"))

    # ── LLM API (OpenAI 兼容接口) ──
    LLM_ENABLED: bool = os.getenv("LLM_ENABLED", "true").lower() == "true"
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_API_BASE_URL: str = os.getenv("LLM_API_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "30"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "500"))

    # ── 通知渠道 ──
    ALERT_NOTIFICATION_ENABLED: bool = os.getenv("ALERT_NOTIFICATION_ENABLED", "true").lower() == "true"
    ALERT_WEBSOCKET_ENABLED: bool = os.getenv("ALERT_WEBSOCKET_ENABLED", "true").lower() == "true"
    ALERT_FEISHU_WEBHOOK_URL: str = os.getenv(
        "ALERT_FEISHU_WEBHOOK_URL",
        "https://open.feishu.cn/open-apis/bot/v2/hook/f2026cea-209f-46e7-8243-44c318ddbe15",
    )
    ALERT_FEISHU_ENABLED: bool = os.getenv("ALERT_FEISHU_ENABLED", "true").lower() == "true"

    @property
    def wechat_confirm_base_url(self) -> str:
        if self.WECHAT_CONFIRM_BASE_URL:
            return self.WECHAT_CONFIRM_BASE_URL.rstrip("/")
        return f"http://{detect_lan_ip()}:{self.API_PORT}"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )


settings = Settings()
