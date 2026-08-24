from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    environment: str
    database_url: str
    log_level: str
    llm_provider: str | None
    langchain_model: str | None
    langchain_base_url: str | None
    langchain_api_key_env: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from: str | None
    smtp_use_tls: bool
    sms_webhook_url: str | None
    notification_poll_seconds: int
    auth_required: bool
    jwt_secret: str | None
    access_token_minutes: int
    bootstrap_token: str | None
    data_encryption_key: str | None
    celery_broker_url: str | None
    celery_result_backend: str | None
    allowed_hosts: tuple[str, ...]
    cors_origins: tuple[str, ...]
    docs_enabled: bool


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@lru_cache
def get_settings() -> Settings:
    configured_provider = os.getenv("HR_LLM_PROVIDER")
    if configured_provider:
        provider = configured_provider.strip().lower()
    elif os.getenv("DASHSCOPE_API_KEY"):
        provider = "bailian"
    elif os.getenv("OPENAI_API_KEY"):
        provider = "openai"
    else:
        provider = None

    configured_model = os.getenv("HR_LANGCHAIN_MODEL")
    configured_base_url = os.getenv("HR_LANGCHAIN_BASE_URL")
    provider_defaults = {
        "bailian": {
            "model": "qwen-flash",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key_env": "DASHSCOPE_API_KEY",
        },
        "openai": {
            "model": "gpt-5-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
        },
    }
    defaults = provider_defaults.get(provider or "", {})
    return Settings(
        app_name=os.getenv("HR_APP_NAME", "HR Agent Platform"),
        environment=os.getenv("HR_ENVIRONMENT", "development"),
        database_url=os.getenv("HR_DATABASE_URL", "sqlite:///./hr_agent.db"),
        log_level=os.getenv("HR_LOG_LEVEL", "INFO"),
        llm_provider=provider,
        langchain_model=configured_model or defaults.get("model"),
        langchain_base_url=configured_base_url or defaults.get("base_url"),
        langchain_api_key_env=defaults.get("api_key_env"),
        smtp_host=os.getenv("HR_SMTP_HOST") or None,
        smtp_port=int(os.getenv("HR_SMTP_PORT", "587")),
        smtp_username=os.getenv("HR_SMTP_USERNAME") or None,
        smtp_password=os.getenv("HR_SMTP_PASSWORD") or None,
        smtp_from=os.getenv("HR_SMTP_FROM") or os.getenv("HR_SMTP_USERNAME") or None,
        smtp_use_tls=_bool_env("HR_SMTP_USE_TLS", True),
        sms_webhook_url=os.getenv("HR_SMS_WEBHOOK_URL") or None,
        notification_poll_seconds=max(10, int(os.getenv("HR_NOTIFICATION_POLL_SECONDS", "30"))),
        auth_required=_bool_env("HR_AUTH_REQUIRED", True),
        jwt_secret=os.getenv("HR_JWT_SECRET") or None,
        access_token_minutes=max(5, int(os.getenv("HR_ACCESS_TOKEN_MINUTES", "60"))),
        bootstrap_token=os.getenv("HR_BOOTSTRAP_TOKEN") or None,
        data_encryption_key=os.getenv("HR_DATA_ENCRYPTION_KEY") or None,
        celery_broker_url=os.getenv("HR_CELERY_BROKER_URL") or None,
        celery_result_backend=os.getenv("HR_CELERY_RESULT_BACKEND") or None,
        allowed_hosts=_list_env("HR_ALLOWED_HOSTS", ("127.0.0.1", "localhost", "testserver")),
        cors_origins=_list_env(
            "HR_CORS_ORIGINS", ("http://127.0.0.1:5173", "http://localhost:5173")
        ),
        docs_enabled=_bool_env("HR_DOCS_ENABLED", os.getenv("HR_ENVIRONMENT", "development") != "production"),
    )


def get_langchain_api_key(settings: Settings | None = None) -> str | None:
    current = settings or get_settings()
    if not current.langchain_api_key_env:
        return None
    value = os.getenv(current.langchain_api_key_env)
    return value.strip() if value and value.strip() else None
