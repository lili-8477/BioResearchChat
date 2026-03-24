# BioResearchChat

An AI-powered research agent for bioinformatics analysis. Upload a paper or ask a question — the agent reads it, plans the analysis, writes code, executes it in a Docker container, evaluates results, and iterates. Like Claude Code, but purpose-built for biology.

## How it works

```
Paper / Question
      │
      ▼
┌─ Parse paper (Claude Vision) ─┐
│  Extract methods, tools, data  │
└────────────┬───────────────────┘
             ▼
┌─ Plan analysis ───────────────┐
│  Match skills + lessons        │
│  Select Docker image           │
│  User reviews & approves       │
└────────────┬───────────────────┘
             ▼
┌─ Write code ──────────────────┐
│  Adapt from skill templates    │
│  Apply lessons from memory     │
└────────────┬───────────────────┘
             ▼
┌─ Execute in Docker ───────────┐
│  Auto-install dependencies     │
│  Mount data, models, refs      │
│  Stream output in real-time    │
└────────────┬───────────────────┘
             ▼
┌─ Evaluate + Retry ────────────┐
│  Success → return results      │
│  Failure → fix code, retry 3x  │
│  Save lessons for next time    │
└───────────────────────────────┘
```

## Two ways to use it

### Option 1: Claude Code CLI (uses your Max plan, no API key)

```bash
# Put your data in data/user/
cp your_data.h5ad data/user/

# Pull pre-built images (faster than building)
./scripts/pull-images.sh

# Run
./run-agent.sh "annotate cell types using scimilarity"
```

### Option 2: Web UI (uses Anthropic API)

```bash
# Set your API key
cp .env.example .env  # edit and add ANTHROPIC_API_KEY

# Start backend + frontend
./dev.sh

# Open http://localhost:3000
```

## Quick start

### Prerequisites

- Docker
- Python 3.11+
- Node.js 20+ (for web UI)
- Claude Code (for CLI mode) or Anthropic API key (for web UI)

### 1. Pull Docker images

Pre-built images from GHCR — no need to build from Dockerfiles:

```bash
./scripts/pull-images.sh
```

| Image | Size | What's inside |
|---|---|---|
| `python-scimilarity` | 6 GB | scimilarity, scanpy, pytorch, hnswlib, tiledb |
| `python-spatial` | 1.9 GB | scanpy, squidpy, celltypist, anndata |
| `r-rnaseq` | ~2 GB | DESeq2, edgeR, ggplot2, EnhancedVolcano |
| `python-chipseq` | ~1 GB | deeptools, macs2, pybedtools, pysam |
| `python-general` | ~500 MB | pandas, numpy, scipy, scikit-learn |

Or build from source:
```bash
docker build -t research-agent/python-scimilarity:base -f images/python-scimilarity.Dockerfile .
docker build -t research-agent/python-spatial:base -f images/python-spatial.Dockerfile .
docker build -t research-agent/r-rnaseq:base -f images/r-rnaseq.Dockerfile .
docker build -t research-agent/python-chipseq:base -f images/python-chipseq.Dockerfile .
docker build -t research-agent/python-general:base -f images/python-general.Dockerfile .
```

### 2. Download large models (if needed)

Some analyses require pre-trained models. Download once, reuse forever:

```bash
# See what's available and what's cached
./scripts/download-model.sh list

# Download what a specific skill needs
./scripts/download-model.sh setup scimilarity_cell_annotation

# Or download individually
./scripts/download-model.sh get scimilarity_v1.1    # 28 GB
./scripts/download-model.sh get celltypist_models    # 50 MB
./scripts/download-model.sh get hg38_genome          # 3.1 GB
```

Models are stored in `data/models/` and mounted into containers at `/data/models/`.

### 3. Run an analysis

```bash
# Drop your data
cp my_cells.h5ad data/user/

# Launch the agent
./run-agent.sh "cluster and annotate my single-cell data"
```

Results appear in `workspaces/current/output/`:
- Plots (PNG)
- Tables (CSV)
- Processed data (h5ad)
- Analysis log (markdown report)

## Data layout

```
data/
├── user/          Your files → /data/user/ in containers
├── models/        Pre-trained models → /data/models/
├── references/    Genomes, GTF → /data/references/
└── atlases/       Cell atlases → /data/atlases/
```

All directories are mounted read-only into every container. Large data stays on the host — containers start instantly.

## Pipeline skills

Built-in templates the agent uses as starting points:

| Skill | Analysis | Image |
|---|---|---|
| `deseq2_bulk_rnaseq` | Bulk RNA-seq differential expression | r-rnaseq |
| `scanpy_scrna_clustering` | scRNA-seq QC, clustering, markers | python-spatial |
| `scimilarity_cell_annotation` | Cell type annotation via KNN | python-scimilarity |
| `scimilarity_cell_query` | Cell similarity search across atlas | python-scimilarity |
| `macs2_chipseq_peaks` | ChIP-seq peak calling + bigWig | python-chipseq |
| `deeptools_heatmap` | Signal heatmaps at peaks/TSS | python-chipseq |
| `spatial_transcriptomics` | Visium/MERFISH spatial analysis | python-spatial |

Skills are YAML files in `backend/skills/templates/`. Add your own by creating a new YAML file.

## Lessons (memory)

The agent learns from every analysis:

- **Auto-captured**: After a successful run, Claude extracts non-obvious insights
- **User-saved**: Type `/lesson your takeaway` in chat, or use the Lessons page
- **Searchable**: Powered by [qmd](https://github.com/tobi/qmd) (BM25 full-text search)

Lessons are injected into future analyses so the agent avoids known pitfalls and applies proven approaches.

## Architecture

See [docs/architecture-webui.md](docs/architecture-webui.md) for detailed diagrams.

```
┌──────────────┐     ┌──────────────┐
│  Web UI      │     │  Claude Code  │
│  (Next.js)   │     │  (CLI)        │
└──────┬───────┘     └──────┬───────┘
       │ WebSocket          │ Bash
       ▼                    ▼
┌──────────────┐     ┌──────────────┐
│  FastAPI     │     │  program.md  │
│  Backend     │     │  (agent      │
│  + Claude API│     │   instructions)
└──────┬───────┘     └──────┬───────┘
       │                    │
       └────────┬───────────┘
                ▼
        ┌──────────────┐
        │  Docker      │
        │  Containers  │  ← same images, same mounts
        │  (execution) │
        └──────────────┘
```

Both paths produce identical results — same Docker images, same data mounts, same output format.

## Docker image hosting

Pre-built images are hosted on GitHub Container Registry:

```
ghcr.io/lili-8477/bioresearchchat/python-scimilarity:base
ghcr.io/lili-8477/bioresearchchat/python-spatial:base
```

Pull with `./scripts/pull-images.sh` or push your own with `./scripts/push-images.sh`.

## Deployment

### Local development
```bash
./dev.sh  # starts backend (port 8001) + frontend (port 3000)
```

### Docker Compose (production)
```bash
docker compose up -d --build  # backend + frontend + nginx on port 80
```

### Self-hosted data
Large models and references live on the host filesystem. For faster setup across machines, mirror them to S3/GCS and set `DATA_MIRROR` in `.env`.

## Project structure

```
├── backend/
│   ├── main.py                  FastAPI + WebSocket endpoints
│   ├── agent/
│   │   ├── orchestrator.py      Main agent loop (parse → plan → code → execute → evaluate)
│   │   ├── paper_parser.py      PDF/URL → structured methods extraction
│   │   ├── planner.py           Generate analysis plan via Claude
│   │   ├── code_writer.py       Generate + fix analysis scripts
│   │   ├── evaluator.py         Evaluate execution output
│   │   ├── image_resolver.py    Select/build Docker images
│   │   └── analysis_log.py      Write structured markdown reports
│   ├── container_runtime/
│   │   ├── executor.py          Docker execution + auto-package install
│   │   └── image_cache.py       Manage cached extended images
│   ├── data/
│   │   ├── data_manager.py      Download/cache large datasets
│   │   ├── registry.yaml        Catalog of models, genomes, atlases
│   │   ├── api.py               Dataset mounting API
│   │   ├── geo.py               GEO dataset downloader
│   │   └── tcga.py              TCGA/GDC downloader
│   ├── skills/
│   │   ├── manager.py           Skill search and management
│   │   └── templates/*.yaml     Pipeline skill templates
│   └── memory/
│       ├── manager.py           Lesson store + qmd search
│       └── lessons/*.md         Stored lessons (markdown)
├── frontend/                    Next.js chat UI
├── images/                      Dockerfiles for base images
├── scripts/
│   ├── docker-run.sh            Run scripts with all data mounted
│   ├── download-model.sh        Download/manage large datasets
│   ├── pull-images.sh           Pull pre-built images from GHCR
│   └── push-images.sh           Push images to GHCR
├── program.md                   Agent instructions for Claude Code mode
├── run-agent.sh                 Launch agent via Claude Code
├── dev.sh                       Start local dev servers
└── docker-compose.yml           Production deployment
```

## License

MIT
