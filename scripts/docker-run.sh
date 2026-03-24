#!/bin/bash
# Run analysis in Docker with all data directories mounted.
# This ensures feature parity between CLI and Web UI execution paths.
#
# Usage:
#   ./scripts/docker-run.sh <image-name> <command>
#
# Examples:
#   ./scripts/docker-run.sh python-scimilarity python /workspace/analysis.py
#   ./scripts/docker-run.sh r-rnaseq Rscript /workspace/analysis.R
#   ./scripts/docker-run.sh python-spatial "pip install -q scvi-tools && python /workspace/analysis.py"
#
# All data directories are mounted read-only:
#   data/user/        → /data/user/
#   data/models/      → /data/models/
#   data/references/  → /data/references/
#   data/atlases/     → /data/atlases/
#   workspaces/current/ → /workspace/ (read-write)

set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <image-name> <command>"
    echo ""
    echo "Images: python-scimilarity, python-spatial, r-rnaseq, python-chipseq, python-general"
    echo ""
    echo "Examples:"
    echo "  $0 python-scimilarity python /workspace/analysis.py"
    echo "  $0 r-rnaseq Rscript /workspace/analysis.R"
    echo "  $0 python-spatial \"pip install -q scvi-tools && python /workspace/analysis.py\""
    exit 1
fi

IMAGE="research-agent/$1:base"
shift
CMD="$*"

# Ensure workspace exists
mkdir -p "$DIR/workspaces/current/output"

# Build mount flags — only mount directories that exist
MOUNTS="-v $DIR/workspaces/current:/workspace"

for subdir in user models references atlases; do
    if [ -d "$DIR/data/$subdir" ]; then
        MOUNTS="$MOUNTS -v $DIR/data/$subdir:/data/$subdir:ro"
    fi
done

# Check if image exists
if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
    echo "ERROR: Image $IMAGE not found."
    echo "Build it with:"
    echo "  docker build -t $IMAGE -f images/$1.Dockerfile ."
    exit 1
fi

echo "=== Running in $IMAGE ==="
echo "Command: $CMD"
echo "Mounts:"
for subdir in user models references atlases; do
    if [ -d "$DIR/data/$subdir" ]; then
        SIZE=$(du -sh "$DIR/data/$subdir" 2>/dev/null | cut -f1)
        echo "  /data/$subdir ($SIZE)"
    fi
done
echo ""

# If command contains && or pipes, wrap in sh -c
if echo "$CMD" | grep -qE '[&|;]'; then
    docker run --rm \
        $MOUNTS \
        --memory=16g \
        --cpus=8 \
        "$IMAGE" \
        sh -c "$CMD"
else
    docker run --rm \
        $MOUNTS \
        --memory=16g \
        --cpus=8 \
        "$IMAGE" \
        $CMD
fi

echo ""
echo "=== Done ==="
echo "Output files:"
ls -lh "$DIR/workspaces/current/output/" 2>/dev/null || echo "  (none)"
