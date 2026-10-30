import os

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: str = "*"
    ALLOWED_HOST: str = "http://localhost:8001"

    model_config = {"env_file": ".env"}

    @field_validator("DATABASE_URL")
    @classmethod
    def _sqlalchemy_scheme(cls, v: str) -> str:
        return "postgresql://" + v[len("postgres://"):] if v.startswith("postgres://") else v

    @field_validator("SECRET_KEY")
    @classmethod
    def _strong_secret(cls, v: str) -> str:
        if len(v) < 32 or v.startswith("change-this"):
            raise ValueError("SECRET_KEY must be a random string of at least 32 characters (not the example value).")
        return v


settings = Settings()


from pathlib import Path as _Path

UPLOAD_ROOT = _Path(os.environ.get("UPLOAD_DIR") or (_Path(__file__).resolve().parents[1] / "uploads"))
