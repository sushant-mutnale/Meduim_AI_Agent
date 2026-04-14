import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Medium Content Automation"
    
    # LLM Settings (OpenRouter)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "google/gemini-pro") # Example OpenRouter model
    
    # Medium
    MEDIUM_API_TOKEN: str = os.getenv("MEDIUM_API_TOKEN", "")
    MEDIUM_USER_ID: str = os.getenv("MEDIUM_USER_ID", "")
    
    # DB
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/content_automation")
    
    # Celery & Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # API Keys
    GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")
    REDDIT_CLIENT_ID: Optional[str] = os.getenv("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET: Optional[str] = os.getenv("REDDIT_CLIENT_SECRET")
    REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "AgenticContentPlatform/1.0")
    
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    
    # Config rules
    REQUIRE_MANUAL_APPROVAL: bool = os.getenv("REQUIRE_MANUAL_APPROVAL", "True").lower() in ("true", "1", "t")
    MIN_CONFIDENCE_SCORE: float = float(os.getenv("MIN_CONFIDENCE_SCORE", "0.85"))

settings = Settings()
