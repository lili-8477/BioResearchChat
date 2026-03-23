FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev zlib1g-dev libbz2-dev liblzma-dev \
    libcurl4-openssl-dev bedtools tabix samtools && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    deeptools macs2 pybedtools pysam matplotlib numpy pandas

WORKDIR /workspace
