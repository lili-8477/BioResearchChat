#!/bin/bash
# Download large models to data/models/ (mounted into containers at /data/models/)
#
# Usage:
#   ./scripts/download-model.sh scimilarity    # SCimilarity model (~30GB)
#   ./scripts/download-model.sh celltypist     # CellTypist models (~50MB)
#
# Models are downloaded ONCE and shared across all container runs.
# To use a faster source, set MODEL_MIRROR env var.

set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODELS_DIR="$DIR/data/models"
mkdir -p "$MODELS_DIR"

download_scimilarity() {
    local dest="$MODELS_DIR/model_v1.1.tar.gz"
    local extracted="$MODELS_DIR/model_v1.1"

    if [ -d "$extracted" ]; then
        echo "SCimilarity model already exists at $extracted"
        echo "Size: $(du -sh "$extracted" | cut -f1)"
        return 0
    fi

    echo "=== Downloading SCimilarity model v1.1 (~30GB) ==="
    echo "Source: https://zenodo.org/records/10685499"
    echo "Destination: $dest"
    echo ""
    echo "This is a large download. Options to speed it up:"
    echo "  1. Use aria2c:  aria2c -x 16 -s 16 <url> -o $dest"
    echo "  2. Use axel:    axel -n 16 <url> -o $dest"
    echo "  3. Download on a fast server and scp it here"
    echo ""

    # Use aria2c if available (multi-connection, much faster)
    if command -v aria2c &>/dev/null; then
        echo "Using aria2c (16 connections)..."
        aria2c -x 16 -s 16 -k 1M \
            "https://zenodo.org/records/10685499/files/model_v1.1.tar.gz?download=1" \
            -d "$MODELS_DIR" -o "model_v1.1.tar.gz"
    elif command -v axel &>/dev/null; then
        echo "Using axel (16 connections)..."
        axel -n 16 \
            "https://zenodo.org/records/10685499/files/model_v1.1.tar.gz?download=1" \
            -o "$dest"
    else
        echo "Using curl (single connection — install aria2c for faster downloads)..."
        curl -L --progress-bar \
            -o "$dest" \
            "https://zenodo.org/records/10685499/files/model_v1.1.tar.gz?download=1"
    fi

    echo ""
    echo "Extracting..."
    tar -xzf "$dest" -C "$MODELS_DIR/"
    echo "Done. Model at: $extracted"
    echo "Size: $(du -sh "$extracted" | cut -f1)"

    # Keep the tarball or remove it
    read -p "Remove tarball to save space? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -f "$dest"
        echo "Tarball removed."
    fi
}

download_celltypist() {
    local dest="$MODELS_DIR/celltypist"
    mkdir -p "$dest"

    if [ "$(ls -A $dest 2>/dev/null)" ]; then
        echo "CellTypist models already exist at $dest"
        return 0
    fi

    echo "=== Downloading CellTypist models (~50MB) ==="
    pip install celltypist 2>/dev/null || true
    python -c "
import celltypist
celltypist.models.download_models(force_update=False)
import shutil, os
src = os.path.expanduser('~/.celltypist/data/models/')
if os.path.exists(src):
    for f in os.listdir(src):
        shutil.copy2(os.path.join(src, f), '$dest/')
    print(f'Downloaded {len(os.listdir(src))} models to $dest')
"
    echo "Done."
}

case "${1:-}" in
    scimilarity)
        download_scimilarity
        ;;
    celltypist)
        download_celltypist
        ;;
    *)
        echo "Usage: $0 <model>"
        echo ""
        echo "Available models:"
        echo "  scimilarity   — SCimilarity v1.1 cell annotation + query (~30GB)"
        echo "  celltypist    — CellTypist automated cell type annotation (~50MB)"
        echo ""
        echo "Models are saved to data/models/ and mounted into containers at /data/models/"
        ;;
esac
