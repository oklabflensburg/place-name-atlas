from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://atlas_runtime:local-development-runtime@127.0.0.1:5432/atlas"
    import_database_url: str | None = None
    migration_database_url: str | None = None
    query_timeout_ms: int = 10000
    export_limit: int = 10000
    tile_limit_bytes: int = 2000000


@lru_cache
def settings() -> Settings:
    return Settings()
