from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: str = "*"
    ALLOWED_HOST: str = "http://localhost:8001"

    model_config = {"env_file": ".env"}


settings = Settings()


from pathlib import Path as _Path

UPLOAD_ROOT = _Path(__file__).resolve().parents[1] / "uploads"
