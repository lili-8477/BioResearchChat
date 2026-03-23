"""Resolve the correct Docker image for an analysis, extending if needed."""

import docker

from config import settings

BASE_IMAGES = {
    "python-spatial": f"{settings.IMAGE_PREFIX}/python-spatial:base",
    "r-rnaseq": f"{settings.IMAGE_PREFIX}/r-rnaseq:base",
    "python-chipseq": f"{settings.IMAGE_PREFIX}/python-chipseq:base",
    "python-general": f"{settings.IMAGE_PREFIX}/python-general:base",
}


def _make_tag(base_name: str, extra_packages: list[str]) -> str:
    """Build a cache tag like research-agent/python-spatial:base+scvi+cellpose."""
    if not extra_packages:
        return BASE_IMAGES[base_name]
    suffix = "+".join(sorted(extra_packages))
    return f"{settings.IMAGE_PREFIX}/{base_name}:base+{suffix}"


def _image_exists(client: docker.DockerClient, tag: str) -> bool:
    try:
        client.images.get(tag)
        return True
    except docker.errors.ImageNotFound:
        return False


async def resolve_image(base_name: str, extra_packages: list[str] | None = None) -> str:
    """Resolve or build the Docker image needed for analysis.

    Returns the image tag to use.
    """
    extra_packages = extra_packages or []
    client = docker.from_env()

    # If no extra packages, just use the base
    if not extra_packages:
        tag = BASE_IMAGES.get(base_name)
        if not tag:
            raise ValueError(f"Unknown base image: {base_name}")
        if not _image_exists(client, tag):
            raise RuntimeError(
                f"Base image {tag} not found. Build it with: "
                f"docker build -t {tag} -f images/{base_name}.Dockerfile ."
            )
        return tag

    # Check for cached extended image
    tag = _make_tag(base_name, extra_packages)
    if _image_exists(client, tag):
        return tag

    # Build extended image
    base_tag = BASE_IMAGES[base_name]
    if not _image_exists(client, base_tag):
        raise RuntimeError(f"Base image {base_tag} not found.")

    # Determine install command based on image type
    if base_name.startswith("r-"):
        install_cmd = (
            "R -e \"install.packages(c("
            + ", ".join(f"'{p}'" for p in extra_packages)
            + "), repos='https://cran.r-project.org')\""
        )
    else:
        install_cmd = f"pip install --no-cache-dir {' '.join(extra_packages)}"

    # Run base image, install packages, commit
    container = client.containers.run(
        base_tag,
        command=f"sh -c '{install_cmd}'",
        detach=True,
    )
    result = container.wait()
    if result["StatusCode"] != 0:
        logs = container.logs().decode()
        container.remove()
        raise RuntimeError(f"Failed to install packages: {logs}")

    container.commit(repository=tag.split(":")[0], tag=tag.split(":")[1])
    container.remove()

    return tag
