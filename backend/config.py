import os
import secrets
from pathlib import Path


class Config:
    # Auth
    AUTH_SECRET: str = os.environ.get("AUTH_SECRET", "")
    JWT_SECRET: str = os.environ.get("JWT_SECRET", secrets.token_hex(32))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = int(os.environ.get("JWT_EXPIRE_HOURS", "72"))

    # Server
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", "8000"))

    # CORS origins (comma-separated, or * for all)
    CORS_ORIGINS: list[str] = os.environ.get("CORS_ORIGINS", "*").split(",")

    # Claude Code
    CLAUDE_BINARY: str = os.environ.get("CLAUDE_BINARY", "claude")
    DEFAULT_WORKING_DIR: str = os.environ.get(
        "DEFAULT_WORKING_DIR", str(Path.home())
    )

    # Sessions
    MAX_SESSIONS: int = int(os.environ.get("MAX_SESSIONS", "10"))
    SESSION_TIMEOUT_SECONDS: int = int(
        os.environ.get("SESSION_TIMEOUT_SECONDS", "7200")
    )

    # Output buffer kept per session (bytes, roughly)
    OUTPUT_BUFFER_MAX: int = int(os.environ.get("OUTPUT_BUFFER_MAX", str(500 * 1024)))


config = Config()
