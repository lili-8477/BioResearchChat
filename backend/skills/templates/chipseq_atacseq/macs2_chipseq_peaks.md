---
name: macs2_chipseq_peaks
description: "ChIP-seq peak calling with MACS2: BAM QC, narrow/broad peaks, FRiP, bigWig track"
analysis_type: chipseq
base_image: python-chipseq
language: python
packages: [macs2, deeptools, pysam, matplotlib, pandas, numpy]
tags: [chipseq, peak-calling, macs2, deeptools, bigwig, histone, transcription-factor]
---

# ChIP-seq Peak Calling with MACS2

## When to use
- ChIP-seq BAM files needing peak calling
- Narrow peaks for transcription factors, broad peaks for histone marks
- Optional input/control BAM

## Key decisions
- BAMPE format (paired-end); change to BAM for single-end
- Genome size: "hs" (human) or "mm" (mouse)
- q-value cutoff: 0.05
- RPKM normalization for bigWig, bin size 10bp
- Use --broad flag for H3K27me3, H3K36me3, H3K9me3

## Template

```python
# REQUIREMENTS: macs2 deeptools pysam matplotlib pandas numpy
import subprocess
import pysam
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

os.makedirs("/workspace/output", exist_ok=True)

TREATMENT_BAM = "/data/treatment.bam"
CONTROL_BAM = "/data/control.bam"  # Can be None for ATAC-seq
GENOME_SIZE = "hs"  # hs=human, mm=mouse
PEAK_TYPE = "narrow"  # "narrow" for TF, "broad" for histone marks

# --- 1. BAM stats ---
print("Checking BAM file stats...")
bam = pysam.AlignmentFile(TREATMENT_BAM, "rb")
total_reads = bam.count()
bam.close()
print(f"Treatment BAM: {total_reads:,} aligned reads")

# --- 2. Peak calling ---
print(f"Calling {PEAK_TYPE} peaks with MACS2...")
macs2_cmd = [
    "macs2", "callpeak",
    "-t", TREATMENT_BAM,
    "-f", "BAMPE",
    "-g", GENOME_SIZE,
    "-n", "analysis",
    "--outdir", "/workspace/output",
    "-q", "0.05",
]
if CONTROL_BAM and os.path.exists(CONTROL_BAM):
    macs2_cmd.extend(["-c", CONTROL_BAM])
if PEAK_TYPE == "broad":
    macs2_cmd.append("--broad")

result = subprocess.run(macs2_cmd, capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"MACS2 stderr: {result.stderr}")

# --- 3. Peak summary ---
peak_ext = "broadPeak" if PEAK_TYPE == "broad" else "narrowPeak"
peak_file = f"/workspace/output/analysis_peaks.{peak_ext}"
if os.path.exists(peak_file):
    peaks = pd.read_csv(peak_file, sep="\t", header=None,
                        names=["chr", "start", "end", "name", "score",
                               "strand", "signal", "pvalue", "qvalue"] +
                              (["peak"] if PEAK_TYPE == "narrow" else []))
    print(f"Called {len(peaks)} peaks")
    print(f"Mean peak width: {(peaks['end'] - peaks['start']).mean():.0f} bp")
    peaks.to_csv("/workspace/output/peaks_summary.csv", index=False)

    # Peak width distribution
    widths = peaks["end"] - peaks["start"]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(widths, bins=50, edgecolor="black")
    ax.set_xlabel("Peak width (bp)")
    ax.set_ylabel("Count")
    ax.set_title(f"Peak Width Distribution (n={len(peaks)})")
    fig.savefig("/workspace/output/peak_width_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()

# --- 4. Generate bigWig ---
print("Generating bigWig signal track...")
bw_cmd = [
    "bamCoverage",
    "-b", TREATMENT_BAM,
    "-o", "/workspace/output/signal.bw",
    "--normalizeUsing", "RPKM",
    "--binSize", "10",
    "-p", "4",
]
subprocess.run(bw_cmd, capture_output=True, text=True)

print("Analysis complete.")
```
