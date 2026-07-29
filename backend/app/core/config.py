import os
from typing import List, Union
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "POSP Support Chatbot"
    API_V1_STR: str = "/api/v1"
    ENV: str = "development"

    # Security
    SECRET_KEY: str = "supersecretkeychangeinproduction1234567890"  # Default for dev, override in .env
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: str = "sqlite:///./insurance_chatbot.db"

    # OAuth Providers
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:3000/auth/callback/google"
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    MICROSOFT_TENANT_ID: str = "common"  # 'common' for multi-tenant, or tenant ID for single-tenant
    MICROSOFT_OAUTH_REDIRECT_URI: str = "http://localhost:3000/auth/callback/microsoft"
    FRONTEND_URL: str = "http://localhost:3000"

    # AI & Vector DB
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    CHROMADB_HOST: str = "localhost"
    CHROMADB_PORT: int = 8001

    # RAG Retrieval Reranker Weights (Tuned via Grid Search on Human Benchmark)
    RERANK_RETRIEVED_WEIGHT: float = 0.65
    RERANK_META_WEIGHT: float = 0.25
    RERANK_SPECIFICITY_WEIGHT: float = 0.00
    RERANK_COVERAGE_WEIGHT: float = 0.10

    # Embeddable widget authentication (enterprise deployments)
    WIDGET_API_KEY: str = ""
    WIDGET_SERVICE_USER_EMAIL: str = "widget-service@internal.local"
    
    # Storage
    UPLOAD_DIR: str = "uploads"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
