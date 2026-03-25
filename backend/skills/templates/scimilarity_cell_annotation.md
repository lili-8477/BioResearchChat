---
name: scimilarity_cell_annotation
description: "Cell type annotation with SCimilarity: embed cells, KNN annotation, UMAP, Leiden consensus"
analysis_type: scrna_seq
base_image: python-scimilarity
language: python
packages: [scimilarity, scanpy, anndata, matplotlib, numpy, pandas]
tags: [scrnaseq, single-cell, cell-annotation, cell-similarity, scimilarity, embedding, knn, umap, reference-atlas]
---

# Cell Annotation with SCimilarity

## When to use
- Annotate cell types in scRNA-seq data using a pretrained reference model
- Requires pretrained SCimilarity model at /data/models/model_v1.1
- Download first: `./scripts/download-model.sh scimilarity`

## Key decisions
- Model aligns query genes to its gene order automatically
- Log-normalize counts before embedding
- UMAP computed from SCimilarity embeddings (not PCA)
- Leiden resolution=1 for cluster-level annotation consensus
- min_dist field indicates annotation confidence (lower = more confident)

## Template

```python
# REQUIREMENTS: scimilarity scanpy anndata matplotlib numpy pandas
import scanpy as sc
from matplotlib import pyplot as plt
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")

sc.set_figure_params(dpi=100)
sc.settings.verbosity = 0
plt.rcParams["figure.figsize"] = [6, 4]
plt.rcParams["pdf.fonttype"] = 42

os.makedirs("/workspace/output", exist_ok=True)

# --- 1. Locate pretrained model ---
MODEL_DIR = "/data/models/model_v1.1"
if not os.path.exists(MODEL_DIR):
    MODEL_DIR = "/workspace/models/model_v1.1"
if not os.path.exists(MODEL_DIR):
    raise FileNotFoundError(
        "SCimilarity model not found. Download it first:\n"
        "  ./scripts/download-model.sh scimilarity\n"
        "This downloads to data/models/ which is mounted into containers."
    )
print(f"Using model at {MODEL_DIR}")

from scimilarity import CellAnnotation
from scimilarity.utils import align_dataset, lognorm_counts

# --- 2. Load model ---
print("Loading SCimilarity model...")
ca = CellAnnotation(model_path=MODEL_DIR)

# --- 3. Load data ---
print("Loading data...")
adata = sc.read("/data/input.h5ad")
print(f"Loaded {adata.n_obs} cells x {adata.n_vars} genes")

# --- 4. Preprocess ---
print("Aligning dataset to model gene order...")
adata = align_dataset(adata, ca.gene_order)
adata = lognorm_counts(adata)

# --- 5. Get embeddings ---
print("Computing SCimilarity embeddings...")
adata.obsm["X_scimilarity"] = ca.get_embeddings(adata.X)

# --- 6. UMAP from embeddings ---
print("Computing UMAP...")
sc.pp.neighbors(adata, use_rep="X_scimilarity")
sc.tl.umap(adata)

# --- 7. Annotate cells ---
print("Running cell type annotation...")
adata = ca.annotate_dataset(adata)

# --- 8. Visualize ---
print("Generating plots...")
sc.pl.umap(adata, color="celltype_hint", legend_fontsize=7, save="_scimilarity_celltypes.png")
os.rename("figures/umap_scimilarity_celltypes.png", "/workspace/output/umap_celltypes.png")

sc.pl.umap(adata, color="min_dist", vmax=0.1, save="_scimilarity_confidence.png")
os.rename("figures/umap_scimilarity_confidence.png", "/workspace/output/umap_confidence.png")

# --- 9. Leiden clustering + annotation consensus ---
print("Clustering...")
sc.tl.leiden(adata, resolution=1)

leiden_annotation = {}
for cluster in adata.obs["leiden"].unique():
    mask = adata.obs["leiden"] == cluster
    most_common = adata.obs.loc[mask, "celltype_hint"].value_counts().index[0]
    leiden_annotation[cluster] = most_common
adata.obs["leiden_celltype"] = adata.obs["leiden"].map(leiden_annotation)

sc.pl.umap(adata, color="leiden_celltype", legend_fontsize=7, save="_leiden_celltypes.png")
os.rename("figures/umap_leiden_celltypes.png", "/workspace/output/umap_leiden_celltypes.png")

# --- 10. Save results ---
print("Saving results...")
adata.obs[["celltype_hint", "min_dist", "leiden", "leiden_celltype"]].to_csv(
    "/workspace/output/cell_annotations.csv"
)
adata.write("/workspace/output/adata_annotated.h5ad")

# Print summary
print("\n=== Annotation Summary ===")
print(adata.obs["celltype_hint"].value_counts().to_string())
print(f"\nTotal cells: {adata.n_obs}")
print("Analysis complete.")
```
