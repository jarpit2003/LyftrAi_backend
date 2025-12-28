import os
from functools import lru_cache
from typing import Optional
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Server settings
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Database settings
    database_url: str = Field(env="DATABASE_URL")
    
    # Logging settings
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")
    log_file: Optional[str] = Field(default=None, env="LOG_FILE")
    
    # Security settings
    webhook_secret: Optional[str] = Field(env="WEBHOOK_SECRET")
    
    # API settings
    api_title: str = Field(default="Webhook Message Service", env="API_TITLE")
    api_version: str = Field(default="1.0.0", env="API_VERSION")
    api_description: str = Field(
        default="A service for receiving webhook messages and retrieving statistics",
        env="API_DESCRIPTION"
    )
    
    # CORS settings
    cors_origins: str = Field(default="*", env="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")
    cors_allow_methods: str = Field(default="*", env="CORS_ALLOW_METHODS")
    cors_allow_headers: str = Field(default="*", env="CORS_ALLOW_HEADERS")
    
    # Pagination settings
    default_page_size: int = Field(default=100, env="DEFAULT_PAGE_SIZE")
    max_page_size: int = Field(default=1000, env="MAX_PAGE_SIZE")
    
    # Cleanup settings
    cleanup_interval_hours: int = Field(default=24, env="CLEANUP_INTERVAL_HOURS")
    retention_days: int = Field(default=30, env="RETENTION_DAYS")
    
    # Metrics settings
    enable_metrics: bool = Field(default=True, env="ENABLE_METRICS")
    metrics_endpoint: str = Field(default="/metrics", env="METRICS_ENDPOINT")
    
    # Rate limiting settings
    enable_rate_limiting: bool = Field(default=False, env="ENABLE_RATE_LIMITING")
    rate_limit_requests: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(default=60, env="RATE_LIMIT_WINDOW")
    
    # Health check settings
    health_check_interval: int = Field(default=30, env="HEALTH_CHECK_INTERVAL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @property
    def cors_origins_list(self) -> list:
        """Convert CORS origins string to list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    @property
    def cors_methods_list(self) -> list:
        """Convert CORS methods string to list"""
        return [method.strip() for method in self.cors_allow_methods.split(",")]
    
    @property
    def cors_headers_list(self) -> list:
        """Convert CORS headers string to list"""
        return [header.strip() for header in self.cors_allow_headers.split(",")]
    
    def get_database_connection_string(self) -> str:
        """Get properly formatted database connection string"""
        if self.database_url.startswith("sqlite:///"):
            # Ensure the directory exists
            db_path = self.database_url.replace("sqlite:///", "")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return self.database_url
    
    def validate_settings(self) -> None:
        """Validate critical settings"""
        if self.port < 1 or self.port > 65535:
            raise ValueError("Port must be between 1 and 65535")
        
        if self.default_page_size < 1 or self.default_page_size > self.max_page_size:
            raise ValueError("Default page size must be between 1 and max page size")
        
        if self.retention_days < 1:
            raise ValueError("Retention days must be at least 1")
    
    def is_ready(self) -> bool:
        """Check if application is ready to serve requests"""
        return bool(self.webhook_secret and self.webhook_secret.strip())


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    settings = Settings()
    try:
        settings.validate_settings()
    except ValueError as e:
        print(f"Configuration error: {e}")
        raise
    return settings


def get_database_url() -> str:
    """Get database URL from settings"""
    return get_settings().get_database_connection_string()


def is_development() -> bool:
    """Check if running in development mode"""
    return get_settings().debug


def is_production() -> bool:
    """Check if running in production mode"""
    return not get_settings().debug


# Environment variable documentation
ENVIRONMENT_VARIABLES = {
    "HOST": "Server host address (default: 0.0.0.0)",
    "PORT": "Server port (default: 8000)",
    "DEBUG": "Enable debug mode (default: False)",
    "DATABASE_URL": "Database connection URL (required)",
    "LOG_LEVEL": "Logging level (DEBUG, INFO, WARNING, ERROR, default: INFO)",
    "LOG_FORMAT": "Log format (json, text, default: json)",
    "LOG_FILE": "Optional log file path",
    "WEBHOOK_SECRET": "Webhook secret key (required for readiness)",
    "API_TITLE": "API title",
    "API_VERSION": "API version",
    "API_DESCRIPTION": "API description",
    "CORS_ORIGINS": "Comma-separated CORS origins (default: *)",
    "CORS_ALLOW_CREDENTIALS": "Allow CORS credentials (default: True)",
    "CORS_ALLOW_METHODS": "Comma-separated CORS methods (default: *)",
    "CORS_ALLOW_HEADERS": "Comma-separated CORS headers (default: *)",
    "DEFAULT_PAGE_SIZE": "Default pagination size (default: 100)",
    "MAX_PAGE_SIZE": "Maximum pagination size (default: 1000)",
    "CLEANUP_INTERVAL_HOURS": "Cleanup interval in hours (default: 24)",
    "RETENTION_DAYS": "Data retention period in days (default: 30)",
    "ENABLE_METRICS": "Enable metrics collection (default: True)",
    "METRICS_ENDPOINT": "Metrics endpoint path (default: /metrics)",
    "ENABLE_RATE_LIMITING": "Enable rate limiting (default: False)",
    "RATE_LIMIT_REQUESTS": "Rate limit requests per window (default: 100)",
    "RATE_LIMIT_WINDOW": "Rate limit window in seconds (default: 60)",
    "HEALTH_CHECK_INTERVAL": "Health check interval in seconds (default: 30)",
}
