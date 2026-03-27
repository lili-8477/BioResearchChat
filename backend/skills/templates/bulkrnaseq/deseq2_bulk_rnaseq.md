---
name: deseq2_bulk_rnaseq
description: "Bulk RNA-seq differential expression with DESeq2: counts, normalization, DE testing, PCA, volcano, heatmap"
analysis_type: bulk_rnaseq
base_image: r-rnaseq
language: r
packages: [DESeq2, ggplot2, pheatmap, EnhancedVolcano, RColorBrewer]
tags: [rnaseq, differential-expression, deseq2, bulk, volcano, pca]
---

# Bulk RNA-seq DE with DESeq2

## When to use
- Bulk RNA-seq with counts matrix + sample metadata
- Comparing conditions (treatment vs control, disease vs normal)

## Key decisions
- Pre-filter genes with <10 total counts
- Design formula: ~ condition
- Significance: padj < 0.05, |log2FC| > 1
- VST for visualization (PCA, heatmap)
- Top 50 genes for heatmap

## Template

```r
# REQUIREMENTS: DESeq2 ggplot2 pheatmap EnhancedVolcano RColorBrewer
library(DESeq2)
library(ggplot2)
library(pheatmap)
library(EnhancedVolcano)
library(RColorBrewer)

dir.create("/workspace/output", showWarnings = FALSE, recursive = TRUE)

# --- 1. Load data ---
cat("Loading count matrix and sample metadata...\n")
counts <- read.csv("/data/counts.csv", row.names = 1)
metadata <- read.csv("/data/metadata.csv", row.names = 1)
# Ensure sample order matches
counts <- counts[, rownames(metadata)]

# --- 2. Create DESeq2 dataset ---
cat("Creating DESeqDataSet...\n")
dds <- DESeqDataSetFromMatrix(
  countData = counts,
  colData = metadata,
  design = ~ condition
)
# Pre-filter low-count genes
keep <- rowSums(counts(dds)) >= 10
dds <- dds[keep, ]

# --- 3. Run DESeq2 ---
cat("Running DESeq2...\n")
dds <- DESeq(dds)
res <- results(dds, alpha = 0.05)
res_ordered <- res[order(res$padj), ]

# --- 4. Save results ---
cat("Saving results table...\n")
write.csv(as.data.frame(res_ordered), "/workspace/output/deseq2_results.csv")

sig <- subset(res_ordered, padj < 0.05 & abs(log2FoldChange) > 1)
write.csv(as.data.frame(sig), "/workspace/output/significant_genes.csv")
cat(sprintf("Found %d significant genes (padj<0.05, |LFC|>1)\n", nrow(sig)))

# --- 5. PCA plot ---
cat("Generating PCA plot...\n")
vsd <- vst(dds, blind = FALSE)
pca_data <- plotPCA(vsd, intgroup = "condition", returnData = TRUE)
pct_var <- round(100 * attr(pca_data, "percentVar"))
p_pca <- ggplot(pca_data, aes(PC1, PC2, color = condition)) +
  geom_point(size = 3) +
  xlab(paste0("PC1: ", pct_var[1], "% variance")) +
  ylab(paste0("PC2: ", pct_var[2], "% variance")) +
  theme_minimal()
ggsave("/workspace/output/pca_plot.png", p_pca, width = 8, height = 6)

# --- 6. Volcano plot ---
cat("Generating volcano plot...\n")
png("/workspace/output/volcano_plot.png", width = 800, height = 600)
EnhancedVolcano(res,
  lab = rownames(res),
  x = "log2FoldChange",
  y = "pvalue",
  pCutoff = 0.05,
  FCcutoff = 1,
  title = "Differential Expression"
)
dev.off()

# --- 7. Heatmap of top genes ---
cat("Generating heatmap...\n")
top_genes <- head(rownames(res_ordered), 50)
mat <- assay(vsd)[top_genes, ]
mat <- mat - rowMeans(mat)
png("/workspace/output/heatmap_top50.png", width = 800, height = 1000)
pheatmap(mat,
  annotation_col = as.data.frame(colData(dds)[, "condition", drop = FALSE]),
  cluster_rows = TRUE, cluster_cols = TRUE,
  show_rownames = TRUE, fontsize_row = 7
)
dev.off()

cat("Analysis complete.\n")
```
