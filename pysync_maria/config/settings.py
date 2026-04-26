from pathlib import Path
from typing import Optional, Type, TypeVar
from pydantic import BaseModel, SecretStr, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import os

T = TypeVar("T", bound="BaseSettings")

class HostConfig(BaseModel):
    """Configuration for a single MariaDB host."""
    host: str
    port: int = 3306
    user: str
    password: SecretStr
    database: str
    charset: str = "utf8mb4"
    connect_timeout: int = 10

class AppSettings(BaseSettings):
    """Main application settings."""
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    source: HostConfig
    target: HostConfig
    batch_size: int = 5000
    dry_run: bool = False

def load_app_settings(source_env: Optional[Path] = None, target_env: Optional[Path] = None) -> AppSettings:
    """
    Load settings from environment variables and optional .env files.
    To support two different .env files for source and target, we load them into the environment
    manually if provided, using prefixes.
    """
    # Load source env file if exists
    if source_env and source_env.exists():
        load_dotenv(dotenv_path=source_env, override=True)
    
    # Load target env file if exists
    if target_env and target_env.exists():
        load_dotenv(dotenv_path=target_env, override=True)

    try:
        return AppSettings()
    except ValidationError as e:
        # Re-raise with a more user-friendly message if needed
        raise e
