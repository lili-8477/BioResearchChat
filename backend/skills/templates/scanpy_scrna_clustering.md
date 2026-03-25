---
name: scanpy_scrna_clustering
description: "Single-cell RNA-seq: QC, normalize, HVG, PCA, UMAP, Leiden clustering, markers"
analysis_type: scrna_seq
base_image: python-spatial
language: python
packages: [scanpy, anndata, matplotlib, leidenalg, numpy, pandas]
tags: [scrnaseq, single-cell, clustering, umap, scanpy, leiden, marker-genes]
---

# scRNA-seq Clustering with Scanpy

## When to use
- Standard single-cell RNA-seq from 10x Chromium (filtered_feature_bc_matrix)
- Tasks: QC → normalize → cluster → find marker genes

## Key decisions
- QC filters: >200 genes, <5000 genes, <20% mito
- Normalize to 10k counts, log1p transform
- HVG selection: min_mean=0.0125, max_mean=3, min_disp=0.5
- Regress out total_counts and pct_counts_mt before scaling
- 30 PCs, 15 neighbors, Leiden resolution=0.8
- Wilcoxon test for marker genes

## Template

```python
# REQUIREMENTS: scanpy anndata matplotlib leidenalg numpy pandas
import scanpy as sc
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import os

os.makedirs("/workspace/output", exist_ok=True)
sc.settings.figdir = "/workspace/output"
sc.settings.verbosity = 2

# --- 1. Load data ---
print("Loading data...")
adata = sc.read_10x_mtx("/data/filtered_feature_bc_matrix/", var_names="gene_symbols", cache=False)
print(f"Loaded {adata.n_obs} cells x {adata.n_vars} genes")

# --- 2. QC ---
print("Running QC...")
adata.var["mt"] = adata.var_names.str.startswith("MT-")
sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True)

sc.pl.violin(adata, ["n_genes_by_counts", "total_counts", "pct_counts_mt"], jitter=0.4, multi_panel=True, save="_qc.png")

# Filter
adata = adata[adata.obs.n_genes_by_counts > 200, :]
adata = adata[adata.obs.n_genes_by_counts < 5000, :]
adata = adata[adata.obs.pct_counts_mt < 20, :]
print(f"After QC: {adata.n_obs} cells")

# --- 3. Normalize ---
print("Normalizing...")
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)

# --- 4. HVG selection ---
print("Selecting highly variable genes...")
sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
adata.raw = adata
adata = adata[:, adata.var.highly_variable]

# --- 5. Scale + PCA ---
print("Scaling and running PCA...")
sc.pp.regress_out(adata, ["total_counts", "pct_counts_mt"])
sc.pp.scale(adata, max_value=10)
sc.tl.pca(adata, svd_solver="arpack")
sc.pl.pca_variance_ratio(adata, n_pcs=50, save="_variance.png")

# --- 6. Neighbors + UMAP ---
print("Computing neighbors and UMAP...")
sc.pp.neighbors(adata, n_neighbors=15, n_pcs=30)
sc.tl.umap(adata)

# --- 7. Clustering ---
print("Clustering with Leiden...")
sc.tl.leiden(adata, resolution=0.8)
sc.pl.umap(adata, color=["leiden"], save="_clusters.png")
print(f"Found {adata.obs['leiden'].nunique()} clusters")

# --- 8. Marker genes ---
print("Finding marker genes...")
sc.tl.rank_genes_groups(adata, "leiden", method="wilcoxon")
sc.pl.rank_genes_groups(adata, n_genes=20, save="_markers.png")

# Save marker gene table
markers = sc.get.rank_genes_groups_df(adata, None)
markers.to_csv("/workspace/output/marker_genes.csv", index=False)

# --- 9. Save ---
adata.write("/workspace/output/adata_processed.h5ad")
print("Analysis complete.")
```
