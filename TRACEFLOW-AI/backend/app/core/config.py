from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "TRACEFLOW AI"
    APP_ENV: str = "development"
    APP_AUTH_MODE: str = "demo"  # "demo" for local no-login access, "jwt" for production
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "traceflow-dev-secret-key-change-in-production-64chars-min"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    DEMO_USER_PASSWORD: str = "TraceflowDemo@2026!"

    DATABASE_URL: str = "sqlite:///./traceflow.db"
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "traceflow_neo4j"
    REDIS_URL: str = "redis://localhost:6379/0"

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    MAX_UPLOAD_MB: int = 25

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
