import os
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    telegram_bot_token: str = Field(..., validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_alert_chat_id: int | None = Field(None, validation_alias="TELEGRAM_ALERT_CHAT_ID")

    binance_api_key: str | None = Field(None, validation_alias="BINANCE_API_KEY")
    binance_api_secret: str | None = Field(None, validation_alias="BINANCE_API_SECRET")

    bybit_api_key: str | None = Field(None, validation_alias="BYBIT_API_KEY")
    bybit_api_secret: str | None = Field(None, validation_alias="BYBIT_API_SECRET")

    database_url: str = Field(..., validation_alias="DATABASE_URL")
    redis_url: str = Field(..., validation_alias="REDIS_URL")

    # symbols_raw ловит SYMBOLS как обычную строку (без попытки json.loads)
    symbols_raw: str = Field("", validation_alias="SYMBOLS", exclude=True)

    symbols: List[str] = Field(default_factory=list)

    wobi_levels: int = Field(10, validation_alias="WOBI_LEVELS")
    wobi_lambda: float = Field(0.35, validation_alias="WOBI_LAMBDA")
    cvd_window_seconds: int = Field(90, validation_alias="CVD_WINDOW_SECONDS")
    spoof_threshold: float = Field(10.0, validation_alias="SPOOF_THRESHOLD")

    zscore_window: int = Field(300, validation_alias="ZSCORE_WINDOW")
    pump_threshold: float = Field(0.68, validation_alias="PUMP_THRESHOLD")
    dump_threshold: float = Field(-0.68, validation_alias="DUMP_THRESHOLD")

    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def parse_symbols_list(self):
        if not self.symbols and self.symbols_raw:
            raw = self.symbols_raw.strip().strip("\"'")
            if raw:
                self.symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]

        if not self.symbols:
            self.symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
        return self


# === ВАЖНО: эта строка обязательна ===
settings = Settings()
