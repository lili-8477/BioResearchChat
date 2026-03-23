"""Manage cached Docker images — lookup and cleanup."""

from datetime import datetime, timedelta, timezone

import docker

from config import settings


class ImageCache:
    """Manages the cache of agent-extended Docker images."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def list_cached_images(self) -> list[dict]:
        """List all research-agent images with their metadata."""
        images = self.client.images.list(name=f"{settings.IMAGE_PREFIX}/*")
        result = []
        for img in images:
            tags = img.tags
            created = img.attrs.get("Created", "")
            size_mb = img.attrs.get("Size", 0) / (1024 * 1024)
            for tag in tags:
                result.append({
                    "tag": tag,
                    "created": created,
                    "size_mb": round(size_mb, 1),
                    "is_base": tag.endswith(":base"),
                })
        return result

    def get_total_cache_size_gb(self) -> float:
        """Get total size of all cached images in GB."""
        images = self.list_cached_images()
        total_mb = sum(img["size_mb"] for img in images)
        return round(total_mb / 1024, 2)

    def prune_old_images(self, max_age_days: int | None = None):
        """Remove cached (non-base) images older than max_age_days."""
        max_age_days = max_age_days or settings.IMAGE_CACHE_MAX_AGE_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        images = self.list_cached_images()
        removed = []

        for img_info in images:
            if img_info["is_base"]:
                continue  # Never prune base images

            created_str = img_info["created"]
            if not created_str:
                continue

            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created < cutoff:
                    self.client.images.remove(img_info["tag"])
                    removed.append(img_info["tag"])
            except (ValueError, docker.errors.APIError):
                continue

        return removed

    def prune_by_size(self, max_gb: float | None = None):
        """Remove oldest cached images until total size is under max_gb."""
        max_gb = max_gb or settings.IMAGE_CACHE_MAX_GB

        while self.get_total_cache_size_gb() > max_gb:
            images = [i for i in self.list_cached_images() if not i["is_base"]]
            if not images:
                break

            # Sort by creation date, oldest first
            images.sort(key=lambda x: x["created"])
            oldest = images[0]

            try:
                self.client.images.remove(oldest["tag"])
            except docker.errors.APIError:
                break
