FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libhdf5-dev pkg-config && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    scanpy squidpy celltypist anndata matplotlib leidenalg

WORKDIR /workspace
