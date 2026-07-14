"""
Configuration Settings for FastAPI Backend Service (Enterprise Architecture v5)
Uses Pydantic v2 type-safe defaults loaded directly from environment variables.
"""
import os
from pydantic import BaseModel, Field

class Settings(BaseModel):
    # Application Info
    APP_NAME: str = "J&T Sortation Center Logistics API"
    APP_VERSION: str = "5.0.0"
    ENVIRONMENT: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    
    # API Routing & Server
    API_PREFIX: str = "/api/v1"
    PORT: int = Field(default_factory=lambda: int(os.getenv("PORT", "8080")))
    HOST: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "https://jtcargo.com.vn",
        "*"
    ]
    
    # PostgreSQL Database Connection Parameters
    DATABASE_URL: str | None = Field(default_factory=lambda: os.getenv("DATABASE_URL"))
    PGHOST: str = Field(default_factory=lambda: os.getenv("PGHOST", "localhost"))
    PGPORT: int = Field(default_factory=lambda: int(os.getenv("PGPORT", "5433")))
    PGUSER: str = Field(default_factory=lambda: os.getenv("PGUSER", "postgres"))
    PGPASSWORD: str = Field(default_factory=lambda: os.getenv("PGPASSWORD", "postgres"))
    PGDATABASE: str = Field(default_factory=lambda: os.getenv("PGDATABASE", "postgres"))
    
    # Cloud Neon Pooler Fallback URL
    NEON_POOLER_URL: str = "postgresql://neondb_owner:npg_i0dyTk6oeEmD@ep-dawn-poetry-atfofe2l-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    
    # ThreadedConnectionPool Configuration
    DB_POOL_MIN_CONN: int = Field(default=5, description="Minimum pool connections for low latency P50 < 50ms")
    DB_POOL_MAX_CONN: int = Field(default=30, description="Maximum pool capacity before rate limiting")
    DB_CONNECT_TIMEOUT: int = Field(default=10, description="Connection acquisition timeout in seconds")
    
    # Latency Budget SLA Targets (for monitoring verification)
    SLA_P50_TARGET_MS: float = 50.0
    SLA_P95_TARGET_MS: float = 150.0

settings = Settings()
