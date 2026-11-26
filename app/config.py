"""Configuration for the Commercial Auto Loss Rating Engine."""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load .env if present
load_dotenv()


class Settings(BaseSettings):
    """Application settings from environment variables."""

    app_name: str = "Commercial Auto Loss Rating Engine"
    debug: bool = False

    # Supabase
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    supabase_db_password: str = os.getenv("SUPABASE_DB_PASSWORD", "")
    supabase_db_url: str = os.getenv(
        "SUPABASE_DB_URL",
        f"postgresql+asyncpg://postgres:{os.getenv('SUPABASE_DB_PASSWORD', '')}"
        f"@{os.getenv('SUPABASE_DB_HOST', 'db.quilgtlvmtdsqoxbzeeo.supabase.co')}"
        f":5432/postgres",
    )

    # Rating engine
    ldf_table_path: Optional[str] = None
    retention_table_path: Optional[str] = None
    trend_factor_path: Optional[str] = None
    state_rules_path: Optional[str] = None

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"


settings = Settings()