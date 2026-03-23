"""Database API — manage dataset access and mounting."""

from pathlib import Path

from config import settings
from data.geo import download_geo_dataset
from data.tcga import download_tcga_dataset


class DataAPI:
    """Manages dataset downloads and provides mount paths for containers."""

    def __init__(self):
        self.cache_dir = settings.DATA_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def get_dataset_path(self, dataset_id: str) -> str:
        """Get local path for a dataset, downloading if needed.

        Returns host path suitable for Docker volume mounting.
        """
        path = self.cache_dir / dataset_id
        if path.exists() and any(path.iterdir()):
            return str(path)

        # Download based on ID prefix
        if dataset_id.upper().startswith("GSE"):
            await download_geo_dataset(dataset_id, path)
        elif dataset_id.upper().startswith("TCGA-"):
            await download_tcga_dataset(dataset_id, path)
        else:
            raise ValueError(
                f"Unknown dataset format: {dataset_id}. "
                "Expected GEO (GSE...) or TCGA (TCGA-...) ID."
            )

        return str(path)

    async def mount_datasets(self, dataset_ids: list[str]) -> dict[str, str]:
        """Get mount mappings for multiple datasets.

        Returns dict of {host_path: container_path}.
        """
        mounts = {}
        for dataset_id in dataset_ids:
            host_path = await self.get_dataset_path(dataset_id)
            container_path = f"/data/{dataset_id}"
            mounts[host_path] = container_path
        return mounts

    def get_upload_path(self, session_id: str) -> Path:
        """Get path for user-uploaded files."""
        upload_dir = self.cache_dir / "uploads" / session_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir

    def list_cached_datasets(self) -> list[dict]:
        """List all locally cached datasets."""
        datasets = []
        for path in self.cache_dir.iterdir():
            if path.is_dir() and path.name != "uploads":
                size_mb = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / (1024 * 1024)
                datasets.append({
                    "id": path.name,
                    "path": str(path),
                    "size_mb": round(size_mb, 1),
                })
        return datasets
