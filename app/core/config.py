import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Medium Content Automation"
    
    # LLM Settings (OpenRouter)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "mistralai/mistral-7b-instruct:free")
    
    # Image Generation (ImageRouter + Gemini fallback)
    IMAGEROUTER_API_KEY: str = os.getenv("IMAGEROUTER_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # Medium (Playwright-based)
    MEDIUM_AUTH_JSON_PATH: str = os.getenv("MEDIUM_AUTH_JSON_PATH", "medium-automation/auth.json")
    
    # DB (Supabase PostgreSQL)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/content_automation")
    
    # Celery & Redis (Upstash)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    # Source API Keys
    GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")
    NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")
    
    # Config rules
    REQUIRE_MANUAL_APPROVAL: bool = os.getenv("REQUIRE_MANUAL_APPROVAL", "True").lower() in ("true", "1", "t")
    MIN_CONFIDENCE_SCORE: float = float(os.getenv("MIN_CONFIDENCE_SCORE", "0.85"))

settings = Settings()
