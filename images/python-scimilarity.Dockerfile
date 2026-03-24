FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libhdf5-dev pkg-config curl cmake && \
    rm -rf /var/lib/apt/lists/*

# Step 1: Install all dependencies that scimilarity needs
RUN pip install --no-cache-dir \
    scanpy anndata matplotlib leidenalg numpy pandas \
    captum circlify hnswlib obonet pytorch-lightning \
    tiledb "zarr<3.0.0"

# Step 2: Install scimilarity itself without pulling deps again
# (tiledb-vector-search would fail to build, but scimilarity works without it)
RUN pip install --no-cache-dir --no-deps scimilarity

WORKDIR /workspace
