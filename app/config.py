"""QueryMind application configuration."""

import os
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    """Like os.getenv, but treats an empty string in the .env file the
    same as an unset variable, so a blank `KEY=` line falls back to
    `default` instead of resolving to ''."""
    value = os.getenv(key)
    return value if value else default


class Config:
    """Base configuration."""

    SECRET_KEY = _env("SECRET_KEY", "dev-secret-key-change-in-production")
    GROQ_API_KEY = _env("GROQ_API_KEY", "")

    # Upload
    MAX_CONTENT_LENGTH = int(_env("MAX_CONTENT_LENGTH", "52428800"))  # 50MB
    MAX_ROWS = 500000
    MAX_COLUMNS = 200
    ALLOWED_EXTENSIONS = {"csv"}

    # Dataset storage
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    DATABASES_DIR = os.path.join(DATA_DIR, "databases")
    EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")
    LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

    # Database (master metadata DB — sessions, dataset registry, query history)
    SQLALCHEMY_DATABASE_URI = _env(
        "SQLALCHEMY_DATABASE_URI", f"sqlite:///{os.path.join(DATA_DIR, 'master.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sample datasets
    SAMPLE_DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_data")

    # Pagination
    RESULTS_PER_PAGE = 50

    # Groq / AI
    GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-120b")
    AI_MAX_RETRIES = 3  # self-healing SQL retry loop

    # Forecasting
    FORECAST_MIN_POINTS = 8
    FORECAST_DEFAULT_HORIZON = 12

    # Query safety
    SQL_STATEMENT_TIMEOUT_ROWS = 100000
    SQL_QUERY_TIMEOUT_SECONDS = int(_env("SQL_QUERY_TIMEOUT_SECONDS", "10"))

    # AI / prompt safety — bound the untrusted question and the model's output
    # so a malicious or oversized request can't consume the entire Groq quota.
    MAX_QUESTION_LENGTH = int(_env("MAX_QUESTION_LENGTH", "20000"))
    AI_MAX_OUTPUT_TOKENS_SQL = int(_env("AI_MAX_OUTPUT_TOKENS_SQL", "500"))
    AI_MAX_OUTPUT_TOKENS_SUMMARY = int(_env("AI_MAX_OUTPUT_TOKENS_SUMMARY", "1000"))

    # Rate limiting (in-memory, per-process — see app/extensions.py). Set
    # explicitly here (rather than relying on Flask-Limiter's own default) so
    # behavior is deterministic regardless of call order if create_app() is
    # ever invoked more than once in the same process (e.g. in tooling/tests).
    RATELIMIT_ENABLED = True
    RATE_LIMIT_DEFAULT = _env("RATE_LIMIT_DEFAULT", "60 per minute")
    RATE_LIMIT_ASK = _env("RATE_LIMIT_ASK", "20 per minute")

    # CORS — same-origin only unless explicitly configured. QueryMind's own
    # frontend calls these routes same-origin, so an empty list here does not
    # affect normal use.
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _env("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]

    # Session cookie security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Logging
    LOG_LEVEL = _env("LOG_LEVEL", "INFO")
    LOG_FILE = os.path.join(LOG_DIR, _env("LOG_FILE", "app.log"))

    # Pagination
    PAGE_SIZE = 50


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    # Only send the session cookie over HTTPS in production; local dev (and
    # the testing config below) keep the base class's default so http://
    # localhost keeps working.
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """Testing configuration — in-memory master DB, isolated tmp dirs."""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Off by default so unrelated tests aren't affected by shared limiter
    # state; tests that specifically exercise rate limiting turn it back on.
    RATELIMIT_ENABLED = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
