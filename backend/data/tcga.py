"""TCGA dataset downloader via GDC API."""

import json
from pathlib import Path

import httpx

GDC_FILES_ENDPOINT = "https://api.gdc.cancer.gov/files"
GDC_DATA_ENDPOINT = "https://api.gdc.cancer.gov/data"


async def download_tcga_dataset(project_id: str, dest: Path, data_type: str = "Gene Expression Quantification", max_files: int = 50):
    """Download TCGA data for a project via GDC API.

    Args:
        project_id: TCGA project ID (e.g., TCGA-BRCA)
        dest: Local directory to save files
        data_type: Type of data to download
        max_files: Maximum number of files to download
    """
    dest.mkdir(parents=True, exist_ok=True)

    # Query GDC for files
    filters = {
        "op": "and",
        "content": [
            {"op": "in", "content": {"field": "cases.project.project_id", "value": [project_id]}},
            {"op": "in", "content": {"field": "data_type", "value": [data_type]}},
            {"op": "in", "content": {"field": "access", "value": ["open"]}},
        ],
    }

    params = {
        "filters": json.dumps(filters),
        "fields": "file_id,file_name,file_size",
        "size": str(max_files),
        "format": "JSON",
    }

    async with httpx.AsyncClient(timeout=300) as client:
        # Get file list
        response = await client.get(GDC_FILES_ENDPOINT, params=params)
        response.raise_for_status()
        data = response.json()

        hits = data.get("data", {}).get("hits", [])
        if not hits:
            raise RuntimeError(f"No open-access {data_type} files found for {project_id}")

        print(f"Found {len(hits)} files for {project_id}")

        # Download each file
        for hit in hits:
            file_id = hit["file_id"]
            file_name = hit["file_name"]
            file_path = dest / file_name

            if file_path.exists():
                print(f"Skipping {file_name} (already exists)")
                continue

            print(f"Downloading {file_name}...")
            download_url = f"{GDC_DATA_ENDPOINT}/{file_id}"
            async with client.stream("GET", download_url) as stream:
                stream.raise_for_status()
                with open(file_path, "wb") as f:
                    async for chunk in stream.aiter_bytes(chunk_size=8192):
                        f.write(chunk)

    # Save metadata
    meta_path = dest / "metadata.json"
    meta_path.write_text(json.dumps(hits, indent=2))
    print(f"Downloaded {len(hits)} files to {dest}")
