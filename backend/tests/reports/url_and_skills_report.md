# URL Parsing & Skill Loading Test Report

**Date**: 2026-03-24 19:43:16
**Test count**: 1 URLs

---

## URL: https://github.com/Genentech/scimilarity

- **Description**: SCimilarity — cell similarity foundation model
- **Expected type**: github
- **Expected analysis**: scrna_seq
- **is_github_url**: `True`
- **Parse time**: 10.1s
- **Status**: PASS

### Parsed result

```json
{
  "url_type": "github",
  "purpose": "To create a unifying representation of single-cell expression profiles that quantifies similarity between expression states and enables searching through millions of cell profiles to find cells similar to a query state, without requiring additional training for new studies",
  "input": "Single-cell RNA-seq expression profiles from new studies; pretrained model weights, embeddings, kNN graphs, and single-cell metadata available from Zenodo; human tissue atlas scRNA-seq data with metadata",
  "method": "Foundation model approach using pretrained neural network embeddings to represent cell states in a unified latent space; cell similarity search using kNN graphs; model generalizes to new data without retraining",
  "output": "Cell embeddings in unified representation space; similar cells to query states from large atlases; kNN graphs for cell similarity relationships; searchable cell state representations",
  "analysis_type": "scrna_seq",
  "packages": [
    "scimilarity",
    "setuptools",
    "setuptools_scm",
    "wheel"
  ],
  "language": "python",
  "datasets": [
    "zenodo.10685499",
    "zenodo.10895214"
  ],
  "summary": "SCimilarity is a foundation model for single-cell RNA-seq analysis that creates a universal representation space for cell expression profiles, enabling researchers to search through millions of cells to find states similar to their query cells of interest. The model generalizes to new datasets without additional training, making it a scalable tool for leveraging large public scRNA-seq atlases. It provides pretrained embeddings, metadata, and kNN graphs for human tissue atlas data, with the core methodology published in Nature (2024). The tool is available as a Python package via PyPI and as a Docker container, with comprehensive tutorials and API documentation."
}
```

### Checks

- [x] url_type: PASS
- [x] analysis_type: PASS
- [x] purpose: PASS (273 chars)
- [x] input: PASS (203 chars)
- [x] method: PASS (210 chars)
- [x] output: PASS (182 chars)

## Progressive Skill Loading

### Phase 1: Registry Search (planner input)

- **Query analysis_type**: `scrna_seq`
- **Query tags**: `['scimilarity', 'setuptools', 'setuptools_scm', 'wheel', 'Foundation model approach using pretrained neural network embeddings to represent cell states in a unified latent space; cell similarity search using kNN graphs; model generalizes to new data without retraining']`
- **Results**: 5 skills matched

- `scimilarity_cell_query` — Cell similarity search with SCimilarity CellQuery: find similar cells across ref...
  - packages: ['scimilarity', 'scanpy', 'anndata', 'matplotlib', 'numpy', 'pandas']
  - code_template leaked: **No (correct)**
- `scimilarity_cell_annotation` — Cell type annotation with SCimilarity: embed cells, KNN annotation, UMAP, Leiden...
  - packages: ['scimilarity', 'scanpy', 'anndata', 'matplotlib', 'numpy', 'pandas']
  - code_template leaked: **No (correct)**
- `scanpy_scrna_clustering` — Single-cell RNA-seq: QC, normalize, HVG, PCA, UMAP, Leiden clustering, markers...
  - packages: ['scanpy', 'anndata', 'matplotlib', 'leidenalg', 'numpy', 'pandas']
  - code_template leaked: **No (correct)**
- `deeptools_heatmap` — Signal heatmaps and profiles from bigWig over BED regions using deeptools...
  - packages: ['deeptools', 'matplotlib', 'numpy']
  - code_template leaked: **No (correct)**
- `deseq2_bulk_rnaseq` — Bulk RNA-seq differential expression with DESeq2: counts, normalization, DE test...
  - packages: ['DESeq2', 'ggplot2', 'pheatmap', 'EnhancedVolcano', 'RColorBrewer']
  - code_template leaked: **No (correct)**

- **Estimated registry tokens**: ~519

### Phase 2: Skill Content Load (code_writer input)

- **Loaded skill**: `scimilarity_cell_query`
- **Content length**: 6749 chars (~1687 tokens)

<details><summary>Skill content preview (first 500 chars)</summary>

```markdown
# Cell Similarity Search with SCimilarity CellQuery

## When to use
- Search a large reference atlas for cells similar to a query cell/state
- Disease association analysis, tissue origin mapping, study source identification
- Requires pretrained model at /data/models/model_v1.1

## Key decisions
- k=10000 nearest neighbors by default (adjust for specificity vs coverage)
- Filter proportions at >0.1% to remove noise
- Query can be single cell (by index) or centroid of a cluster
- Results include 
```
</details>

---