from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


class Settings(BaseSettings):
    app_name: str = "トレード補佐ツール MVP"
    app_env: str = "development"
    debug: bool = True

    oanda_token: str | None = None
    oanda_account_id: str | None = None
    oanda_base_url: str = "https://api-fxpractice.oanda.com"

    alpaca_key_id: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_data_url: str = "https://data.alpaca.markets"
    alpaca_feed: str = "iex"

    default_limit: int = 300
    default_provider: str = "demo"
    default_stock_symbol: str = "7203"
    default_fx_symbol: str = "USDJPY"

    default_fx_watchlist: str = "USDJPY,EURUSD,GBPJPY,AUDJPY,EURJPY,GBPUSD"
    default_jp_stock_watchlist: str = "7203,6758,9984,8306,9432,7974"
    default_us_stock_watchlist: str = "AAPL,NVDA,MSFT,TSLA,AMD,AMZN"
    default_demo_fx_watchlist: str = "BOT_USDJPY,TOP_EURUSD,USDJPY,EURUSD"
    default_demo_stock_watchlist: str = "BOT_7203,TOP_9984,7203,6758"
    recommendation_scan_limit: int = 6

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env",),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
