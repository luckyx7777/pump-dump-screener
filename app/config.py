import os
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_alert_chat_id: int | None = Field(None, env="TELEGRAM_ALERT_CHAT_ID")

    # Binance
    binance_api_key: str | None = Field(None, env="BINANCE_API_KEY")
    binance_api_secret: str | None = Field(None, env="BINANCE_API_SECRET")

    # Bybit
    bybit_api_key: str | None = Field(None, env="BYBIT_API_KEY")
    bybit_api_secret: str | None = Field(None, env="BYBIT_API_SECRET")

    # Database
    database_url: str = Field("postgresql+asyncpg://user:pass@localhost/db", env="DATABASE_URL")
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")

    # Symbols — парсим вручную, чтобы избежать проблем с Railway
    symbols: List[str] = Field(default_factory=list)

    def __init__(self, **data):
        super().__init__(**data)
        if not self.symbols:
            env_symbols = os.getenv(
                "SYMBOLS", 
                "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT"
            )
            self.symbols = [
                s.strip().upper() 
                for s in env_symbols.split(",") 
                if s.strip()
            ]

    # Feature parameters
    wobi_levels: int = 10
    wobi_lambda: float = 0.3
    cvd_window_seconds: int = 60
    spoof_threshold: float = 10.0

    # Scoring
    zscore_window: int = 300
    pump_threshold: float = 0.65
    dump_threshold: float = -0.65

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
