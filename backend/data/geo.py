"""GEO dataset downloader."""

import asyncio
from pathlib import Path

import httpx


async def download_geo_dataset(gse_id: str, dest: Path):
    """Download a GEO dataset (supplementary files) to local cache.

    Downloads the supplementary tar/files from NCBI FTP.
    """
    dest.mkdir(parents=True, exist_ok=True)

    # GEO FTP structure: GSE1234 -> GSE1nnn/GSE1234
    gse_prefix = gse_id[:len(gse_id) - 3] + "nnn"
    base_url = f"https://ftp.ncbi.nlm.nih.gov/geo/series/{gse_prefix}/{gse_id}/suppl/"

    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        # Get directory listing
        response = await client.get(base_url)
        response.raise_for_status()

        # Parse links from the FTP listing page
        import re
        links = re.findall(r'href="([^"]+)"', response.text)
        data_files = [
            link for link in links
            if not link.startswith("?") and not link.startswith("/") and link != "../"
        ]

        if not data_files:
            raise RuntimeError(f"No supplementary files found for {gse_id}")

        # Download each file
        for filename in data_files:
            file_url = f"{base_url}{filename}"
            file_path = dest / filename

            print(f"Downloading {filename}...")
            async with client.stream("GET", file_url) as stream:
                stream.raise_for_status()
                with open(file_path, "wb") as f:
                    async for chunk in stream.aiter_bytes(chunk_size=8192):
                        f.write(chunk)

    print(f"Downloaded {len(data_files)} files to {dest}")
