FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    pandas numpy scipy scikit-learn matplotlib seaborn

WORKDIR /workspace
