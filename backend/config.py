import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")

    DOCKER_HOST: str = os.getenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    IMAGE_CACHE_MAX_GB: int = int(os.getenv("IMAGE_CACHE_MAX_GB", "50"))
    IMAGE_CACHE_MAX_AGE_DAYS: int = int(os.getenv("IMAGE_CACHE_MAX_AGE_DAYS", "30"))
    CONTAINER_MEMORY_LIMIT: str = os.getenv("CONTAINER_MEMORY_LIMIT", "16g")
    CONTAINER_CPU_LIMIT: int = int(os.getenv("CONTAINER_CPU_LIMIT", "8"))
    EXECUTION_TIMEOUT_SECONDS: int = int(os.getenv("EXECUTION_TIMEOUT_SECONDS", "3600"))

    DATA_CACHE_DIR: Path = Path(os.getenv("DATA_CACHE_DIR", str(Path(__file__).parent.parent / "data" / "datasets")))
    WORKSPACE_DIR: Path = Path(os.getenv("WORKSPACE_DIR", str(Path(__file__).parent.parent / "workspaces")))
    SESSION_STATE_DIR: Path = Path(os.getenv("SESSION_STATE_DIR", str(WORKSPACE_DIR / "_sessions")))

    SKILLS_DIR: Path = Path(os.getenv("SKILLS_DIR", str(Path(__file__).parent / "skills" / "templates")))
    LESSONS_DIR: Path = Path(os.getenv("LESSONS_DIR", str(Path(__file__).parent / "memory" / "lessons")))

    CORS_ALLOWED_ORIGINS: list[str] = _parse_csv(
        os.getenv("CORS_ALLOWED_ORIGINS"),
        [
            "http://localhost",
            "http://127.0.0.1",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    )
    CONTROL_API_TOKEN: str = os.getenv("CONTROL_API_TOKEN", "")
    CONTROL_COOKIE_NAME: str = os.getenv("CONTROL_COOKIE_NAME", "biochat_control")
    CONTROL_COOKIE_SECURE: bool = _parse_bool(os.getenv("CONTROL_COOKIE_SECURE"), default=False)
    ENABLE_DEV_ENDPOINTS: bool = _parse_bool(os.getenv("ENABLE_DEV_ENDPOINTS"), default=False)

    # Self-hosted data mirror (S3, GCS, HTTP, NFS)
    # Set to your mirror URL to avoid downloading from Zenodo/UCSC directly
    # Example: "https://your-bucket.s3.amazonaws.com/biochat-data"
    # The mirror should have the same directory structure: models/, references/, atlases/
    DATA_MIRROR: str = os.getenv("DATA_MIRROR", "")

    IMAGE_PREFIX: str = "research-agent"


settings = Settings()
