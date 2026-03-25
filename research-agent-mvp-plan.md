# Research Agent MVP — Plan

A self-hosted, Docker-based research agent with a chat UI. User pastes a URL (GitHub repo or science paper) and asks a research question. The agent parses the URL, guides the user to clarify their request, searches skills and memory, plans the analysis, executes code in a container, reviews results, and generates a report — like Claude Code, but purpose-built for bioinformatics research.

---

## Architecture

```
User (browser)
    │  paper/repo URL + research question
    ▼
┌──────────────────────────────────────────┐
│  Web UI (Next.js / React)                │
│  Chat interface, URL input, results      │
└──────────────┬───────────────────────────┘
               │ REST / WebSocket
               ▼
┌──────────────────────────────────────────┐
│  Backend Orchestrator (Python / FastAPI)  │
│                                          │
│  1. Parse URL → extract context          │
│  2. Guide user → clarify request         │
│  3. Search skills + memory               │
│  4. Plan analysis → user reviews         │
│  5. Execute code in container            │
│  6. Review results → generate report     │
│                                          │
│  Talks to Claude API for all LLM calls   │
└──────┬───────────────┬───────────────────┘
       │               │
       ▼               ▼
┌─────────────┐  ┌──────────────────────────┐
│ Claude API  │  │ Docker Execution Layer    │
│ (remote)    │  │                           │
│             │  │ Base images (you maintain) │
│ - parse URL │  │ ├── python-spatial        │
│ - converse  │  │ ├── r-rnaseq             │
│ - plan      │  │ ├── python-chipseq       │
│ - code gen  │  │ └── ...                  │
│ - evaluate  │  │                           │
│             │  │ Cached images (agent)     │
│             │  │ ├── python-spatial+scvi   │
│             │  │ └── ...                  │
└─────────────┘  └──────────┬───────────────┘
                            │ -v mount
                            ▼
                 ┌──────────────────────────┐
                 │ Database API             │
                 │ Mounts datasets into     │
                 │ containers on demand     │
                 │                          │
                 │ Sources: GEO, TCGA,      │
                 │ local datasets           │
                 └──────────────────────────┘
```

---

## Agent Loop (core logic)

```
START
  │
  ├─ 1. RECEIVE URL + QUESTION
  │     - User pastes a URL (optional) and/or asks a research question
  │     - URL auto-detected from message text if not explicitly attached
  │
  ├─ 2. PARSE URL (route by type)
  │     - GitHub URL → GitHub API (repo metadata, README, file tree, config files)
  │     - Paper/docs URL → crawl4ai (clean markdown extraction)
  │     - Direct PDF URL → download + Claude Vision (page images)
  │     - No URL → skip to step 3
  │     - Extract structured context:
  │       ├── purpose  — what the project/paper aims to achieve
  │       ├── input    — required data (GEO IDs, BAM files, counts)
  │       ├── method   — analytical methods and tools
  │       └── output   — what results are produced
  │
  ├─ 3. GUIDE USER (conversational triage)
  │     - If request is underspecified → ask clarifying questions
  │     - Multi-turn conversation to refine:
  │       ├── What analysis do you want to run?
  │       ├── What data do you have?
  │       └── Any specific parameters or comparisons?
  │     - Once enough context → proceed to planning
  │
  ├─ 4. SEARCH SKILLS + MEMORY (progressive loading)
  │     a. Skill registry search (lightweight, ~50 tokens/skill)
  │        - Match by analysis_type, tags, keyword overlap
  │        - Returns: name, description, packages — NO code templates
  │     b. Memory/lesson search (QMD hybrid: BM25 + vector + reranking)
  │        - Search past lessons by tags and query text
  │        - Returns relevant insights and pitfalls from prior analyses
  │     → Planner sees only metadata, not full skill code
  │
  ├─ 5. GENERATE PLAN (Claude API)
  │     - Input: parsed URL context + user question + skill registry + lessons
  │     - Output: step-by-step plan with:
  │       ├── base image selection
  │       ├── extra packages needed
  │       ├── datasets to mount
  │       ├── skill_reference (which skill to use as template)
  │       └── expected outputs
  │     - Stream plan to user for review
  │     - User can approve, reject, or request modifications
  │     - Multi-round modification supported
  │
  ├─ 6. EXECUTE PLAN
  │     a. Resolve environment
  │        - Check cached images → extend base if needed → docker commit
  │     b. Mount data
  │        - Query database API for required datasets
  │     c. Load skill content (on demand, single skill only)
  │        - Load full markdown body of the planner's chosen skill (~800 tokens)
  │        - Includes: "When to use", "Key decisions", code template
  │     d. Write code (Claude API)
  │        - Input: plan + single skill content + lessons
  │        - Output: complete executable script
  │     e. Execute in container
  │        - docker exec → stream stdout/stderr to UI
  │        - Auto-detect missing packages → install + retry (no retry burn)
  │     f. Self-correction loop
  │        - On failure: evaluate error → fix code → retry (max 3)
  │        - Lessons context included in fix prompt to avoid repeating mistakes
  │
  ├─ 7. REVIEW RESULTS (Claude API)
  │     - Read stdout/stderr + output files
  │     - Evaluate: did the analysis succeed? Are outputs valid?
  │     - Generate summary of findings
  │
  ├─ 8. GENERATE OUTPUT + LOG
  │     a. Results to user
  │        - Plots (PNG), tables (CSV), stats → display in chat UI
  │        - Download links for all output files
  │        - Workspace zip download (all outputs in one file)
  │     b. Analysis log (markdown)
  │        - Session ID, question, paper info, plan, code, output, evaluation
  │        - Saved to workspace directory
  │     c. Extract lessons (auto)
  │        - Claude extracts reusable insights from successful analyses
  │        - Saved as markdown files with YAML frontmatter
  │        - Indexed by QMD for future hybrid search
  │
  └─ 9. DONE
        - Session state → completed
        - User can ask follow-up questions or start new analysis
END
```

---

## URL Parsing

### Route by URL type

| URL pattern | Fetcher | What it gets |
|-------------|---------|--------------|
| `github.com/*` | GitHub API | Repo metadata, README (8k cap), file tree, config files (setup.py, requirements.txt, etc.) |
| `*.pdf` or PDF content-type | httpx download + Claude Vision | PDF pages as images, full document understanding |
| Everything else (papers, docs) | crawl4ai | Clean markdown via `fit_markdown` (main content, no nav/ads/boilerplate) |

### Structured output

All URL types are parsed by Claude into:

```json
{
  "url_type": "github | paper",
  "purpose": "What this project/paper aims to achieve",
  "input": "Required data or inputs",
  "method": "Analytical methods, algorithms, tools",
  "output": "What results are produced",
  "analysis_type": "scrna_seq | bulk_rnaseq | chipseq | spatial | general",
  "packages": ["referenced software packages"],
  "language": "python | r",
  "datasets": ["GSE...", "TCGA-..."],
  "summary": "One-paragraph summary"
}
```

### Environment variables

```bash
GITHUB_TOKEN=ghp_...   # Optional. Without: 60 req/hr. With: 5,000 req/hr.
```

---

## Progressive Skill Loading

Skills are stored as **Markdown files with YAML frontmatter** in `backend/skills/templates/`. Two-tier loading minimizes token usage:

### Tier 1: Registry (planning phase)

Lightweight metadata only — name, description, tags, packages. No code.

```
skills/templates/
├── scanpy_scrna_clustering.md
├── deseq2_bulk_rnaseq.md
├── deeptools_heatmap.md
├── macs2_chipseq_peaks.md
├── spatial_transcriptomics.md
├── scimilarity_cell_annotation.md
├── scimilarity_cell_query.md
└── env_setup.md
```

**Skill file format:**

```markdown
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
- Standard single-cell RNA-seq from 10x Chromium

## Key decisions
- QC filters: >200 genes, <5000 genes, <20% mito
- 30 PCs, 15 neighbors, Leiden resolution=0.8

## Template

```python
# REQUIREMENTS: scanpy anndata matplotlib leidenalg numpy pandas
import scanpy as sc
...
```
```

**Registry search** scores by: analysis_type match (10pts), tag match (3pts each), keyword overlap (2pts), package name match (4pts).

### Tier 2: Full content (code generation phase)

Only the single skill chosen by the planner is loaded. The full markdown body (prose + code blocks) is passed to the code writer.

### Token savings

| Phase | Before (YAML) | After (progressive MD) |
|-------|---------------|----------------------|
| Planning | 3 skills × ~200 tokens metadata | Registry: 8 skills × ~50 tokens = ~400 |
| Code gen | 3 skills × ~800 tokens (with code) = ~2400 | 1 skill × ~800 tokens = ~800 |
| **Total skill tokens/session** | **~4-5K** | **~1.2K (~70% reduction)** |

---

## Memory & Lessons (QMD Hybrid Search)

Lessons are reusable insights extracted from past analyses, stored as markdown files with YAML frontmatter in `backend/memory/lessons/`.

### Storage format

```markdown
---
id: 059f7bc7
source: agent
tags: [scrnaseq, batch-correction, harmony, integration]
session_id: test-002
created_at: 2026-03-23T09:51:56
---

# Use Harmony for batch correction across samples

When integrating multiple scRNA-seq samples, Harmony batch correction
on PCA embeddings worked much better than regressing out batch in the
normalization step...
```

### Search

Uses **QMD** for hybrid search (BM25 full-text + vector + reranking):

- `_qmd_index()` — indexes lesson markdown files with `qmd collection add/update`
- `_qmd_search(query)` — hybrid search returning ranked lessons
- Falls back to keyword-based scoring if QMD is unavailable

### Lesson lifecycle

1. **Auto-extraction** — after successful analysis, Claude extracts lessons from the plan, code, output, and evaluation
2. **User-created** — user can save lessons via `/lesson <text>` or `/save <text>` in chat
3. **Search** — lessons are retrieved during planning and code-fixing phases
4. **Indexed** — QMD keeps the search index up to date

---

## Image Management

### Tier 1: Base images (you maintain)

| Image name         | Base            | Pre-installed packages                         |
|--------------------|-----------------|------------------------------------------------|
| `python-spatial`   | python:3.11-slim| scanpy, squidpy, celltypist, anndata, matplotlib|
| `r-rnaseq`         | r-base:4.3      | DESeq2, hciR, edgeR, ggplot2, EnhancedVolcano |
| `python-chipseq`   | python:3.11-slim| deeptools, macs2, pybedtools, pysam            |
| `python-general`   | python:3.11-slim| pandas, numpy, scipy, scikit-learn, matplotlib |

### Tier 2: Agent-extended images (cached dynamically)

```
research-agent/python-spatial:base              ← you maintain
research-agent/python-spatial:base+scvi         ← agent created
research-agent/python-spatial:base+scvi+cellpose ← agent created
```

Cleanup policy: prune cached images older than 30 days or exceeding disk limit.

---

## Database API

Containers don't fetch data themselves — the database API mounts it.

Supported sources:
- **GEO** (GSE ID → local cache → mount)
- **TCGA** (project ID → GDC API → local cache → mount)
- **Local datasets** (user data or pre-cached references/models)
- **Self-hosted mirror** (S3/GCS/HTTP for large models like SCimilarity)

---

## Tech Stack

| Component          | Technology                  | Why                                        |
|--------------------|-----------------------------|--------------------------------------------|
| Frontend           | Next.js + React + Tailwind  | Chat UI, URL input, streaming responses    |
| Backend            | Python + FastAPI            | Async, easy Docker SDK integration         |
| LLM                | Claude API (Sonnet/Opus)    | Best code generation, long context         |
| Container runtime  | Docker + docker-py SDK      | Local, fast, image caching                 |
| URL parsing        | GitHub API + crawl4ai + Claude Vision | Route by URL type, clean extraction |
| Skill search       | Keyword scoring on YAML frontmatter | Fast, no external dependencies      |
| Memory search      | QMD (BM25 + vector + reranking) | Hybrid search on markdown lessons     |
| Real-time comms    | WebSocket                   | Stream execution output to chat UI         |

---

## File Structure

```
research-agent/
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Chat interface
│   │   ├── lessons/page.tsx     # Lessons browser
│   │   ├── skills/page.tsx      # Skills browser
│   │   └── components/
│   │       ├── ChatWindow.tsx
│   │       ├── PaperUpload.tsx   # URL input (no file upload)
│   │       ├── PlanReview.tsx    # User reviews/edits plan
│   │       ├── ResultsView.tsx   # Plots, tables, downloads
│   │       └── Nav.tsx
│   └── package.json
│
├── backend/
│   ├── main.py                   # FastAPI app entry
│   ├── config.py                 # Settings from .env
│   ├── agent/
│   │   ├── orchestrator.py       # Main agent loop
│   │   ├── paper_parser.py       # URL → GitHub API / crawl4ai → Claude parse
│   │   ├── planner.py            # Context → analysis plan
│   │   ├── code_writer.py        # Plan + skill content → executable script
│   │   ├── evaluator.py          # Output → success/retry decision
│   │   ├── image_resolver.py     # Pick or build Docker image
│   │   └── analysis_log.py       # Write structured analysis log
│   ├── container_runtime/
│   │   ├── executor.py           # docker-py wrapper (run, install, retry)
│   │   └── image_cache.py        # Cached image lookup + cleanup
│   ├── skills/
│   │   ├── manager.py            # Progressive loading: registry + on-demand content
│   │   ├── models.py             # Skill pydantic model
│   │   └── templates/            # Markdown skills with YAML frontmatter
│   │       ├── scanpy_scrna_clustering.md
│   │       ├── deseq2_bulk_rnaseq.md
│   │       ├── deeptools_heatmap.md
│   │       ├── macs2_chipseq_peaks.md
│   │       ├── spatial_transcriptomics.md
│   │       ├── scimilarity_cell_annotation.md
│   │       ├── scimilarity_cell_query.md
│   │       └── env_setup.md
│   ├── memory/
│   │   ├── manager.py            # Lesson CRUD + QMD hybrid search
│   │   ├── models.py             # Lesson pydantic model
│   │   └── lessons/              # Markdown lessons with YAML frontmatter
│   ├── data/
│   │   ├── api.py                # Database API (mount datasets)
│   │   ├── data_manager.py       # Data registry + download management
│   │   └── registry.yaml         # Registered datasets and models
│   ├── tests/
│   │   ├── test_url_and_skills.py # URL parsing + skill loading tests
│   │   └── reports/              # Test output reports (markdown)
│   └── requirements.txt
│
├── images/                       # Dockerfiles for base images
│   ├── python-spatial.Dockerfile
│   ├── r-rnaseq.Dockerfile
│   ├── python-chipseq.Dockerfile
│   └── python-general.Dockerfile
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## .env.example

```bash
# LLM
ANTHROPIC_API_KEY=sk-ant-api03-...
CLAUDE_MODEL=claude-sonnet-4-5-20250929

# GitHub (optional — increases rate limit from 60 to 5000 req/hr)
GITHUB_TOKEN=ghp_...

# Docker
DOCKER_HOST=unix:///var/run/docker.sock
IMAGE_CACHE_MAX_GB=50
IMAGE_CACHE_MAX_AGE_DAYS=30
CONTAINER_MEMORY_LIMIT=16g
CONTAINER_CPU_LIMIT=8
EXECUTION_TIMEOUT_SECONDS=3600

# Data
DATA_CACHE_DIR=/data/datasets
DATA_MIRROR=                     # Self-hosted mirror URL (S3/GCS/HTTP)
GEO_MIRROR=https://ftp.ncbi.nlm.nih.gov/geo/
GDC_API=https://api.gdc.cancer.gov

# App
FRONTEND_PORT=3000
BACKEND_PORT=8000
```

---

## Key Design Decisions

1. **URL-only input (no file upload)** — users paste GitHub repo or paper URLs; agent routes to GitHub API or crawl4ai for clean extraction; simpler UX, no server-side file storage
2. **Conversational triage** — agent guides underspecified requests through multi-turn conversation before planning; reduces wasted compute on wrong approaches
3. **Progressive skill loading** — planner sees only lightweight registry (~50 tokens/skill); full code template loaded on demand for only the selected skill; ~70% token reduction per session
4. **Structured URL parsing** — all URLs parsed into purpose/input/method/output schema; gives planner consistent context regardless of source type
5. **QMD hybrid memory search** — lessons indexed with BM25 + vector search; past insights automatically inform planning and code-fixing
6. **Markdown skill format** — YAML frontmatter for machine search, markdown body for Claude context; includes "When to use" and "Key decisions" sections alongside code templates
7. **Multiple base images over one fat image** — avoids package conflicts, keeps images lean, agent picks the right one
8. **Agent-extended cached images** — first run installs extras (2-5 min), `docker commit` saves it, subsequent runs <1 second
9. **Database API mounts data** — containers never fetch data; clean separation, cacheable, reusable across sessions
10. **Plan review before execution** — user sees and can modify the plan through multiple rounds before code runs
11. **Auto-lesson extraction** — successful analyses automatically generate lessons for future sessions
12. **Analysis log per session** — structured markdown log with full provenance (question, plan, code, output, evaluation)
