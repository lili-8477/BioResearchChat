"""Data manager — handles large dataset downloads, caching, and container mounting."""

import hashlib
import subprocess
from pathlib import Path

import yaml

from config import settings

REGISTRY_PATH = Path(__file__).parent / "registry.yaml"


class DataManager:
    """Manages the data registry — knows what data exists, what's cached, what needs downloading."""

    def __init__(self):
        self.root = Path(settings.DATA_CACHE_DIR).parent  # data/
        self.root.mkdir(parents=True, exist_ok=True)
        self._registry = None

    @property
    def registry(self) -> dict:
        if self._registry is None:
            with open(REGISTRY_PATH) as f:
                self._registry = yaml.safe_load(f)
        return self._registry

    def list_all(self) -> list[dict]:
        """List all registered datasets with their availability status."""
        items = []
        for category in ["models", "references", "atlases"]:
            for name, info in self.registry.get(category, {}).items():
                local = self.root.parent / info["local_path"]
                items.append({
                    "name": name,
                    "category": category,
                    "description": info["description"],
                    "size_gb": info.get("size_gb", "?"),
                    "available": local.exists() and any(local.iterdir()) if local.exists() else False,
                    "local_path": str(local),
                    "mount_path": info["mount_path"],
                    "required_by": info.get("required_by", []),
                })
        return items

    def check_requirements(self, skill_name: str) -> dict:
        """Check which datasets a skill needs and whether they're available."""
        needed = []
        missing = []
        available = []

        for category in ["models", "references", "atlases"]:
            for name, info in self.registry.get(category, {}).items():
                if skill_name in info.get("required_by", []):
                    local = self.root.parent / info["local_path"]
                    is_available = local.exists() and any(local.iterdir()) if local.exists() else False
                    entry = {"name": name, "category": category, **info}
                    needed.append(entry)
                    if is_available:
                        available.append(entry)
                    else:
                        missing.append(entry)

        return {
            "skill": skill_name,
            "needed": needed,
            "available": available,
            "missing": missing,
            "ready": len(missing) == 0,
        }

    def get_mount_map(self, skill_name: str) -> dict[str, str]:
        """Get Docker volume mount mappings for a skill's data dependencies.

        Returns {host_path: container_path} for all available datasets.
        """
        mounts = {}
        for category in ["models", "references", "atlases"]:
            for name, info in self.registry.get(category, {}).items():
                if skill_name in info.get("required_by", []):
                    local = self.root.parent / info["local_path"]
                    if local.exists():
                        mounts[str(local.resolve())] = info["mount_path"]
        return mounts

    def get_all_mounts(self) -> dict[str, str]:
        """Get mount mappings for ALL available cached data."""
        mounts = {}
        for subdir in ["models", "references", "atlases", "user"]:
            path = self.root / subdir if subdir != "user" else self.root.parent / "data" / subdir
            # Try both locations
            for p in [self.root / subdir, self.root.parent / subdir]:
                if p.exists() and any(p.iterdir()):
                    mounts[str(p.resolve())] = f"/data/{subdir}"
                    break
        return mounts

    def download(self, name: str, force: bool = False) -> bool:
        """Download a registered dataset. Returns True on success."""
        # Find the entry
        info = None
        for category in ["models", "references", "atlases"]:
            if name in self.registry.get(category, {}):
                info = self.registry[category][name]
                break

        if not info:
            print(f"Unknown dataset: {name}")
            return False

        local = self.root.parent / info["local_path"]

        if local.exists() and any(local.iterdir()) and not force:
            print(f"{name} already cached at {local}")
            return True

        url = info.get("url", "")
        if url == "manual":
            print(f"{name} must be set up manually.")
            if info.get("note"):
                print(f"  Note: {info['note']}")
            return False

        if url.startswith("pip://"):
            # Special: install via pip
            cmd = info.get("install_cmd", "")
            if cmd:
                print(f"Installing {name}...")
                subprocess.run(cmd, shell=True, check=True)
                return True
            return False

        local.mkdir(parents=True, exist_ok=True)

        filename = url.split("/")[-1].split("?")[0]
        dest = local / filename

        print(f"Downloading {name} ({info.get('size_gb', '?')} GB)...")
        print(f"  URL: {url}")
        print(f"  Dest: {dest}")

        # Use aria2c if available for parallel downloads
        if _has_command("aria2c"):
            print("  Using aria2c (16 connections)...")
            result = subprocess.run(
                ["aria2c", "-x", "16", "-s", "16", "-k", "1M",
                 url, "-d", str(local), "-o", filename],
                capture_output=False,
            )
        elif _has_command("axel"):
            print("  Using axel...")
            result = subprocess.run(
                ["axel", "-n", "16", url, "-o", str(dest)],
                capture_output=False,
            )
        else:
            print("  Using curl (install aria2c for faster downloads)...")
            result = subprocess.run(
                ["curl", "-L", "--progress-bar", "-o", str(dest), url],
                capture_output=False,
            )

        if result.returncode != 0:
            print(f"Download failed for {name}")
            return False

        # Extract if needed
        if info.get("extract") and dest.suffix in (".gz", ".tgz"):
            print("Extracting...")
            subprocess.run(["tar", "-xzf", str(dest), "-C", str(local)], check=True)

        print(f"Done: {name} ready at {local}")
        return True

    def status_report(self) -> str:
        """Generate a human-readable status report of all data."""
        lines = ["## Data Status\n"]
        for item in self.list_all():
            icon = "OK" if item["available"] else "MISSING"
            lines.append(
                f"[{icon}] **{item['name']}** ({item['category']}, {item['size_gb']}GB) "
                f"→ `{item['mount_path']}`"
            )
            if not item["available"]:
                lines.append(f"      Download: `./scripts/download-model.sh {item['name']}`")
        return "\n".join(lines)


def _has_command(cmd: str) -> bool:
    """Check if a command is available on the system."""
    try:
        subprocess.run(["which", cmd], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
