---
name: spatial_transcriptomics
description: "Spatial transcriptomics with Scanpy+Squidpy: QC, clustering, spatial plots, neighborhood enrichment, Moran's I"
analysis_type: spatial
base_image: python-spatial
language: python
packages: [scanpy, squidpy, anndata, matplotlib, numpy, pandas]
tags: [spatial, visium, squidpy, transcriptomics, neighborhood, ligand-receptor]
---

# Spatial Transcriptomics with Squidpy

## When to use
- 10x Visium or MERFISH spatial data
- Spatial clustering, neighborhood analysis, spatially variable genes

## Key decisions
- Mito filter: <20%
- Seurat-flavored HVG selection, top 3000 genes
- 20 PCs, Leiden resolution=0.6
- Moran's I for spatial autocorrelation (100 permutations)
- coord_type="generic" for spatial neighbors

## Template

```python
# REQUIREMENTS: scanpy squidpy anndata matplotlib numpy pandas
import scanpy as sc
import squidpy as sq
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

os.makedirs("/workspace/output", exist_ok=True)
sc.settings.figdir = "/workspace/output"

# --- 1. Load spatial data ---
print("Loading spatial data...")
adata = sc.read_visium("/data/spatial/")
adata.var_names_make_unique()
print(f"Loaded {adata.n_obs} spots x {adata.n_vars} genes")

# --- 2. QC ---
print("QC filtering...")
adata.var["mt"] = adata.var_names.str.startswith("MT-")
sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], inplace=True)
sc.pl.spatial(adata, color=["total_counts", "n_genes_by_counts", "pct_counts_mt"], save="_qc.png")
adata = adata[adata.obs.pct_counts_mt < 20, :]

# --- 3. Normalize + cluster ---
print("Normalizing and clustering...")
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
sc.pp.highly_variable_genes(adata, flavor="seurat", n_top_genes=3000)
adata.raw = adata
adata = adata[:, adata.var.highly_variable]
sc.pp.scale(adata)
sc.tl.pca(adata)
sc.pp.neighbors(adata, n_pcs=20)
sc.tl.umap(adata)
sc.tl.leiden(adata, resolution=0.6)

# --- 4. Spatial plots ---
print("Generating spatial plots...")
sc.pl.spatial(adata, color="leiden", save="_clusters.png")
sc.pl.umap(adata, color="leiden", save="_umap.png")

# --- 5. Spatial statistics ---
print("Computing spatial statistics...")
sq.gr.spatial_neighbors(adata, coord_type="generic")
sq.gr.nhood_enrichment(adata, cluster_key="leiden")
sq.pl.nhood_enrichment(adata, cluster_key="leiden", save="/workspace/output/nhood_enrichment.png")

# --- 6. Spatially variable genes ---
print("Finding spatially variable genes...")
sq.gr.spatial_autocorr(adata, mode="moran", n_perms=100, n_jobs=4)
sv_genes = adata.uns["moranI"].sort_values("I", ascending=False)
sv_genes.head(50).to_csv("/workspace/output/spatially_variable_genes.csv")

top_sv = sv_genes.head(6).index.tolist()
sc.pl.spatial(adata.raw.to_adata(), color=top_sv, save="_top_sv_genes.png")

# --- 7. Save ---
adata.write("/workspace/output/adata_spatial.h5ad")
print("Analysis complete.")
```
