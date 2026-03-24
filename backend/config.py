import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


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

    SKILLS_DIR: Path = Path(os.getenv("SKILLS_DIR", str(Path(__file__).parent / "skills" / "templates")))
    LESSONS_DIR: Path = Path(os.getenv("LESSONS_DIR", str(Path(__file__).parent / "memory" / "lessons")))

    # Self-hosted data mirror (S3, GCS, HTTP, NFS)
    # Set to your mirror URL to avoid downloading from Zenodo/UCSC directly
    # Example: "https://your-bucket.s3.amazonaws.com/biochat-data"
    # The mirror should have the same directory structure: models/, references/, atlases/
    DATA_MIRROR: str = os.getenv("DATA_MIRROR", "")

    IMAGE_PREFIX: str = "research-agent"


settings = Settings()
