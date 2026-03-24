#!/bin/bash
# Push Docker images to GitHub Container Registry (GHCR)
#
# Usage:
#   ./scripts/push-images.sh              # push all built images
#   ./scripts/push-images.sh scimilarity  # push one image
#
# First time setup:
#   echo $GITHUB_TOKEN | docker login ghcr.io -u <username> --password-stdin
#
# Users can then pull images instead of building:
#   docker pull ghcr.io/lili-8477/bioresearchchat/python-scimilarity:base

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

push_image() {
    local name="$1"
    local local_tag="${LOCAL_PREFIX}/${name}:base"
    local remote_tag="${GHCR_PREFIX}/${name}:base"

    if ! docker image inspect "$local_tag" > /dev/null 2>&1; then
        echo "SKIP: $local_tag not built locally"
        return
    fi

    echo "Pushing $local_tag → $remote_tag"
    docker tag "$local_tag" "$remote_tag"
    docker push "$remote_tag"
    echo "Done: $remote_tag"
    echo ""
}

# Check login
if ! docker pull ghcr.io/lili-8477/bioresearchchat/python-general:base > /dev/null 2>&1; then
    if ! grep -q "ghcr.io" ~/.docker/config.json 2>/dev/null; then
        echo "Not logged into GHCR. Run:"
        echo "  echo \$GITHUB_TOKEN | docker login ghcr.io -u lili-8477 --password-stdin"
        echo ""
        echo "Create a token at: https://github.com/settings/tokens"
        echo "  → Scopes: write:packages, read:packages"
        exit 1
    fi
fi

if [ -n "$1" ]; then
    push_image "$1"
else
    echo "=== Pushing all images to $GHCR_PREFIX ==="
    echo ""
    for img in "${IMAGES[@]}"; do
        push_image "$img"
    done
fi
