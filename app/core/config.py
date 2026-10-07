"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Geospatial File Measurement API"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False

    # File upload
    max_file_size_mb: int = 50
    max_uncompressed_size_mb: int = 200
    max_zip_entries: int = 10_000
    data_dir: str = "./data"

    # Supported formats
    supported_extensions: list[str] = [".kml", ".zip"]

    # Required shapefile components
    required_shapefile_extensions: list[str] = [".shp", ".shx", ".dbf"]

    @property
    def max_file_size_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_uncompressed_size_bytes(self) -> int:
        """Maximum total size of files extracted from one ZIP archive."""
        return self.max_uncompressed_size_mb * 1024 * 1024

    @property
    def data_path(self) -> Path:
        """Resolved absolute path to the data directory."""
        return Path(self.data_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
