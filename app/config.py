from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    telegram_bot_token: str = Field(..., validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_alert_chat_id: int | None = Field(None, validation_alias="TELEGRAM_ALERT_CHAT_ID")

    binance_api_key: str | None = Field(None, validation_alias="BINANCE_API_KEY")
    binance_api_secret: str | None = Field(None, validation_alias="BINANCE_API_SECRET")

    bybit_api_key: str | None = Field(None, validation_alias="BYBIT_API_KEY")
    bybit_api_secret: str | None = Field(None, validation_alias="BYBIT_API_SECRET")

    database_url: str = Field(
        "postgresql+asyncpg://user:pass@localhost/db",
        validation_alias="DATABASE_URL"
    )
    redis_url: str = Field(
        "redis://localhost:6379/0",
        validation_alias="REDIS_URL"
    )

    symbols: List[str] = Field(default_factory=list, validation_alias="SYMBOLS")

    wobi_levels: int = Field(10, validation_alias="WOBI_LEVELS")
    wobi_lambda: float = Field(0.3, validation_alias="WOBI_LAMBDA")
    cvd_window_seconds: int = Field(60, validation_alias="CVD_WINDOW_SECONDS")
    spoof_threshold: float = Field(10.0, validation_alias="SPOOF_THRESHOLD")

    zscore_window: int = Field(300, validation_alias="ZSCORE_WINDOW")
    pump_threshold: float = Field(0.65, validation_alias="PUMP_THRESHOLD")
    dump_threshold: float = Field(-0.65, validation_alias="DUMP_THRESHOLD")

    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("symbols", mode="before")
    @classmethod
    def parse_symbols(cls, v):
        if isinstance(v, str):
            # Убираем возможные кавычки и пробелы
            v = v.strip().strip('"\'')
            return [s.strip().upper() for s in v.split(",") if s.strip()]
        if isinstance(v, (list, tuple)):
            return [str(s).strip().upper() for s in v if str(s).strip()]
        return v or []


settings = Settings()
