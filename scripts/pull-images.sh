#!/bin/bash
# Pull pre-built Docker images from GHCR and tag them locally
#
# Usage:
#   ./scripts/pull-images.sh              # pull all available
#   ./scripts/pull-images.sh scimilarity  # pull one image
#
# This is MUCH faster than building from Dockerfiles (minutes vs hours)

set -e

GHCR_PREFIX="ghcr.io/lili-8477/bioresearchchat"
LOCAL_PREFIX="research-agent"

IMAGES=(
    "python-scimilarity"
    "python-spatial"
    "r-rnaseq"
    "python-chipseq"
    "python-general"
)

pull_image() {
    local name="$1"
    local remote_tag="${GHCR_PREFIX}/${name}:base"
    local local_tag="${LOCAL_PREFIX}/${name}:base"

    echo "Pulling $remote_tag..."
    if docker pull "$remote_tag" 2>/dev/null; then
        docker tag "$remote_tag" "$local_tag"
        echo "  → Tagged as $local_tag"
    else
        echo "  → Not available on GHCR. Build locally:"
        echo "    docker build -t $local_tag -f images/${name}.Dockerfile ."
    fi
    echo ""
}

if [ -n "$1" ]; then
    pull_image "$1"
else
    echo "=== Pulling pre-built images from GHCR ==="
    echo ""
    for img in "${IMAGES[@]}"; do
        pull_image "$img"
    done

    echo "=== Local images ==="
    docker images | grep research-agent || echo "(none)"
fi
