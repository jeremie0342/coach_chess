from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_debug: bool = True

    database_url: str
    database_url_sync: str
    test_database_url: str | None = None
    test_database_url_sync: str | None = None

    stockfish_path: str
    stockfish_threads: int = 4
    stockfish_hash_mb: int = 512
    stockfish_default_depth: int = 20

    chesscom_username: str
    chesscom_base_url: str = "https://api.chess.com/pub"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    coach_api_key: str = "changeme"
    coach_cors_origins: str = "http://localhost,http://127.0.0.1"
    redis_url: str = "redis://localhost:6379/0"
    lichess_token: str | None = None
    discord_webhook_url: str | None = None
    slack_webhook_url: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.coach_cors_origins.split(",") if o.strip()]

    @property
    def stockfish_abs_path(self) -> Path:
        p = Path(self.stockfish_path)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
