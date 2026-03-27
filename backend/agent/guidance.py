"""Dynamic guidance configuration — per-seq-type checklist options.

Drives the 4-step onboarding flow in the orchestrator:
  1. Sequencing type
  2. Analysis method (adapts to seq type)
  3. Input data format (adapts to seq type)
  4. Expected output (adapts to seq type + method)
"""

# Maps checklist value → config for downstream steps
SEQ_TYPES = {
    "scrna": {
        "label": "Single-cell RNA-seq",
        "subfolder": "scrnaseq",
        "analysis_type": "scrna_seq",
        "methods": [
            {"value": "clustering", "label": "Clustering & visualization (UMAP, Leiden)"},
            {"value": "annotation", "label": "Cell type annotation"},
            {"value": "de", "label": "Differential expression (between clusters/conditions)"},
            {"value": "trajectory", "label": "Trajectory / pseudotime analysis"},
            {"value": "integration", "label": "Batch correction & integration"},
            {"value": "cell_query", "label": "Cell similarity query (find similar cells in atlas)"},
        ],
        "inputs": [
            {"value": "h5ad", "label": ".h5ad (AnnData)"},
            {"value": "10x_mtx", "label": "10x filtered_feature_bc_matrix/"},
            {"value": "10x_h5", "label": "10x .h5 file"},
            {"value": "geo", "label": "GEO accession (GSExxxxx)"},
        ],
        "outputs": {
            "clustering": [
                {"value": "umap_plot", "label": "UMAP plot colored by cluster"},
                {"value": "marker_table", "label": "Marker gene table per cluster"},
                {"value": "report", "label": "Full report (UMAP + markers + QC)"},
                {"value": "h5ad", "label": "Processed .h5ad file"},
            ],
            "annotation": [
                {"value": "annotated_umap", "label": "UMAP colored by cell type"},
                {"value": "confidence_table", "label": "Annotation confidence scores"},
                {"value": "report", "label": "Full report"},
                {"value": "h5ad", "label": "Annotated .h5ad file"},
            ],
            "de": [
                {"value": "volcano", "label": "Volcano plot"},
                {"value": "deg_table", "label": "DEG table (log2FC, p-value)"},
                {"value": "heatmap", "label": "Top DEG heatmap"},
                {"value": "report", "label": "Full report"},
            ],
            "trajectory": [
                {"value": "trajectory_plot", "label": "Trajectory / pseudotime plot"},
                {"value": "gene_trends", "label": "Gene expression along trajectory"},
                {"value": "report", "label": "Full report"},
            ],
            "integration": [
                {"value": "umap_plot", "label": "Integrated UMAP (before/after)"},
                {"value": "report", "label": "Full report"},
                {"value": "h5ad", "label": "Integrated .h5ad file"},
            ],
            "cell_query": [
                {"value": "similarity_table", "label": "Top matching cells/datasets"},
                {"value": "umap_plot", "label": "Query cells on reference UMAP"},
                {"value": "report", "label": "Full report"},
            ],
        },
    },
    "bulk_rna": {
        "label": "Bulk RNA-seq",
        "subfolder": "bulkrnaseq",
        "analysis_type": "bulk_rnaseq",
        "methods": [
            {"value": "de", "label": "Differential expression (DESeq2)"},
            {"value": "enrichment", "label": "Pathway / gene set enrichment (GSEA, GO)"},
            {"value": "survival", "label": "Survival analysis (Kaplan-Meier, Cox)"},
            {"value": "pca_qc", "label": "PCA / sample QC & visualization"},
        ],
        "inputs": [
            {"value": "counts_matrix", "label": "Raw counts matrix (CSV/TSV)"},
            {"value": "geo", "label": "GEO accession (GSExxxxx)"},
            {"value": "tcga", "label": "TCGA project ID"},
        ],
        "outputs": {
            "de": [
                {"value": "volcano", "label": "Volcano plot"},
                {"value": "deg_table", "label": "DEG table"},
                {"value": "heatmap", "label": "Top DEG heatmap"},
                {"value": "report", "label": "Full report (volcano + heatmap + PCA + table)"},
            ],
            "enrichment": [
                {"value": "enrichment_plot", "label": "Enrichment dot/bar plot"},
                {"value": "pathway_table", "label": "Enriched pathways table"},
                {"value": "report", "label": "Full report"},
            ],
            "survival": [
                {"value": "km_plot", "label": "Kaplan-Meier plot"},
                {"value": "cox_table", "label": "Cox regression results"},
                {"value": "report", "label": "Full report"},
            ],
            "pca_qc": [
                {"value": "pca_plot", "label": "PCA plot"},
                {"value": "report", "label": "Full report"},
            ],
        },
    },
    "chipseq": {
        "label": "ChIP-seq / ATAC-seq",
        "subfolder": "chipseq_atacseq",
        "analysis_type": "chipseq",
        "methods": [
            {"value": "peak_calling", "label": "Peak calling (MACS2)"},
            {"value": "heatmap", "label": "Signal heatmap (deeptools)"},
            {"value": "motif", "label": "Motif enrichment (HOMER / MEME)"},
            {"value": "diff_binding", "label": "Differential binding analysis"},
        ],
        "inputs": [
            {"value": "bam", "label": "BAM files (aligned reads)"},
            {"value": "bigwig", "label": "BigWig signal files"},
            {"value": "bed", "label": "BED peak files"},
            {"value": "geo", "label": "GEO accession (GSExxxxx)"},
        ],
        "outputs": {
            "peak_calling": [
                {"value": "peak_bed", "label": "Peak BED file"},
                {"value": "bigwig", "label": "Normalized signal BigWig"},
                {"value": "report", "label": "Full report (peaks + signal + QC)"},
            ],
            "heatmap": [
                {"value": "heatmap", "label": "Signal heatmap (PNG)"},
                {"value": "profile_plot", "label": "Average profile plot"},
                {"value": "report", "label": "Full report"},
            ],
            "motif": [
                {"value": "motif_table", "label": "Enriched motifs table"},
                {"value": "report", "label": "Full report"},
            ],
            "diff_binding": [
                {"value": "db_table", "label": "Differential binding table"},
                {"value": "volcano", "label": "Volcano plot"},
                {"value": "report", "label": "Full report"},
            ],
        },
    },
    "spatial": {
        "label": "Spatial transcriptomics",
        "subfolder": "spatial",
        "analysis_type": "spatial",
        "methods": [
            {"value": "clustering", "label": "Spatial clustering & domain detection"},
            {"value": "neighborhood", "label": "Neighborhood enrichment analysis"},
            {"value": "lr_interaction", "label": "Ligand-receptor interaction"},
            {"value": "deconvolution", "label": "Cell type deconvolution"},
        ],
        "inputs": [
            {"value": "h5ad", "label": ".h5ad (AnnData with spatial coords)"},
            {"value": "visium", "label": "10x Visium Space Ranger output"},
            {"value": "geo", "label": "GEO accession (GSExxxxx)"},
        ],
        "outputs": {
            "clustering": [
                {"value": "spatial_plot", "label": "Spatial cluster plot"},
                {"value": "umap_plot", "label": "UMAP colored by cluster"},
                {"value": "report", "label": "Full report"},
                {"value": "h5ad", "label": "Processed .h5ad file"},
            ],
            "neighborhood": [
                {"value": "nhood_plot", "label": "Neighborhood enrichment heatmap"},
                {"value": "report", "label": "Full report"},
            ],
            "lr_interaction": [
                {"value": "lr_plot", "label": "Ligand-receptor interaction plot"},
                {"value": "lr_table", "label": "Significant interactions table"},
                {"value": "report", "label": "Full report"},
            ],
            "deconvolution": [
                {"value": "spatial_composition", "label": "Spatial cell type composition map"},
                {"value": "report", "label": "Full report"},
            ],
        },
    },
}

# Default output options when method doesn't have specific ones
DEFAULT_OUTPUTS = [
    {"value": "plots", "label": "Plots"},
    {"value": "tables", "label": "Tables"},
    {"value": "report", "label": "Full report (plots + tables + summary)"},
    {"value": "files", "label": "Processed data files"},
]


def get_output_options(seq_type: str, method: str) -> list[dict]:
    """Get output options for a given seq type and method."""
    config = SEQ_TYPES.get(seq_type)
    if not config:
        return DEFAULT_OUTPUTS
    outputs = config.get("outputs", {})
    return outputs.get(method, DEFAULT_OUTPUTS)
