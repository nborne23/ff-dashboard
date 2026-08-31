"""Environment-driven application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gridiron_secret_key: str = ""
    yahoo_client_id: str = ""
    yahoo_client_secret: str = ""
    gridiron_base_url: str = "http://localhost:8000"
    espn_base_url: str = "https://lm-api-reads.fantasy.espn.com"
    gridiron_scheduler_enabled: bool = False
    gridiron_db_path: str = "data/gridiron.db"
    gridiron_headshots_path: str = "data/headshots"
    gridiron_team_logos_path: str = "data/team-logos"
    # Task 11.3: empty (default) means console-only logging, matching today's dev
    # behavior unchanged. Set to a directory (e.g. ~/Library/Logs/gridiron on the iMac)
    # to also rotate app + scheduler logs to a file there.
    gridiron_log_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
