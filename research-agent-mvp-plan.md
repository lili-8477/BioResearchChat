# Research Agent MVP — Plan

A self-hosted, Docker-based research agent with a chat UI. User uploads a paper (PDF or URL) and asks a research question. The agent reads the paper, plans the analysis, sets up a containerized environment, writes code, executes it, and returns results — like Claude Code, but purpose-built for bioinformatics research.

---

## Architecture

```
User (browser)
    │  paper PDF/URL + research question
    ▼
┌──────────────────────────────────────────┐
│  Web UI (Next.js / React)                │
│  Chat interface, file upload, results    │
└──────────────┬───────────────────────────┘
               │ REST / WebSocket
               ▼
┌──────────────────────────────────────────┐
│  Backend Orchestrator (Python / FastAPI)  │
│                                          │
│  1. Parse paper → extract methods        │
│  2. Plan analysis → pick image + steps   │
│  3. Write code → execute in container    │
│  4. Evaluate output → retry if failed    │
│                                          │
│  Talks to Claude API for all LLM calls   │
└──────┬───────────────┬───────────────────┘
       │               │
       ▼               ▼
┌─────────────┐  ┌──────────────────────────┐
│ Claude API  │  │ Docker Execution Layer    │
│ (remote)    │  │                           │
│             │  │ Base images (you maintain) │
│ - parse     │  │ ├── python-spatial        │
│ - plan      │  │ ├── r-rnaseq             │
│ - code gen  │  │ ├── python-chipseq       │
│ - evaluate  │  │ └── ...                  │
│             │  │                           │
│             │  │ Cached images (agent)     │
│             │  │ ├── python-spatial+scvi   │
│             │  │ ├── r-rnaseq+slingshot   │
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
  ├─ 1. Receive paper + question from user
  │
  ├─ 2. PARSE PAPER (Claude API)
  │     - Extract: methods, tools, packages, data types
  │     - Identify: analysis type (scRNA-seq, spatial, bulk RNA, ChIP-seq, etc.)
  │
  ├─ 3. PLAN ANALYSIS (Claude API)
  │     - Generate step-by-step analysis plan
  │     - Determine required packages
  │     - Select base image (python-spatial, r-rnaseq, etc.)
  │     - Stream plan to user for review/edit
  │
  ├─ 4. RESOLVE ENVIRONMENT
  │     - Check: cached image with all required packages?
  │       ├── YES → use cached image
  │       └── NO  → start from base image
  │                  → install missing packages
  │                  → docker commit → cache as new tagged image
  │
  ├─ 5. MOUNT DATA
  │     - Query database API for required datasets
  │     - Mount into container via -v /data:/data
  │
  ├─ 6. WRITE CODE (Claude API)
  │     - Generate analysis script based on plan
  │     - Write to mounted workspace directory
  │
  ├─ 7. EXECUTE
  │     - docker exec → run script in container
  │     - Stream stdout/stderr back to UI in real-time
  │
  ├─ 8. EVALUATE (Claude API)
  │     - Read stdout/stderr + output files
  │     - Success? → return results to user
  │     - Error?   → diagnose, rewrite code, go to step 7
  │     - Max 3 retries before asking user for help
  │
  └─ 9. RETURN RESULTS
        - Plots, tables, stats → display in chat UI
        - Generated files → download links
END
```

---

## Image Management

### Tier 1: Base images (you maintain)

Pre-built with common packages. Rebuild periodically or when major versions change.

| Image name         | Base            | Pre-installed packages                         |
|--------------------|-----------------|------------------------------------------------|
| `python-spatial`   | python:3.11-slim| scanpy, squidpy, celltypist, anndata, matplotlib|
| `r-rnaseq`         | r-base:4.3      | DESeq2, hciR, edgeR, ggplot2, EnhancedVolcano |
| `python-chipseq`   | python:3.11-slim| deeptools, macs2, pybedtools, pysam            |
| `python-general`   | python:3.11-slim| pandas, numpy, scipy, scikit-learn, matplotlib |

Each has a Dockerfile in the repo. Built with:

```bash
docker build -t research-agent/python-spatial:base -f images/python-spatial.Dockerfile .
```

### Tier 2: Agent-extended images (cached dynamically)

When the agent needs extra packages not in the base:

```python
# Pseudocode for the image resolver
def resolve_image(base_image: str, extra_packages: list[str]) -> str:
    tag = base_image + "+" + "+".join(sorted(extra_packages))
    
    # Check if cached image exists
    if docker_client.images.get(tag):
        return tag  # <1 second startup
    
    # Extend base image
    container = docker_client.containers.run(base_image, detach=True)
    container.exec_run(f"pip install {' '.join(extra_packages)}")
    container.commit(repository=tag)
    container.remove()
    
    return tag  # first run: 2-5 min, subsequent: <1 second
```

Naming convention:
```
research-agent/python-spatial:base              ← you maintain
research-agent/python-spatial:base+scvi         ← agent created
research-agent/python-spatial:base+scvi+cellpose ← agent created
```

Cleanup policy: prune cached images older than 30 days or exceeding a disk limit.

---

## Database API

A lightweight service that manages dataset access. Containers don't fetch data themselves — the API mounts it.

```python
# Pseudocode
class DataAPI:
    def mount_dataset(self, dataset_id: str) -> str:
        """Returns host path ready for docker -v mount."""
        
        path = self.local_cache / dataset_id
        if path.exists():
            return str(path)
        
        # Download if not cached
        if dataset_id.startswith("GSE"):
            self._download_geo(dataset_id, path)
        elif dataset_id.startswith("TCGA-"):
            self._download_tcga(dataset_id, path)
        else:
            raise ValueError(f"Unknown dataset: {dataset_id}")
        
        return str(path)
```

Supported sources (MVP):
- GEO (GEOquery / direct FTP)
- TCGA (TCGAbiolinks / GDC API)
- Local files (user uploads via UI)

---

## Tech Stack

| Component          | Technology                  | Why                                        |
|--------------------|-----------------------------|--------------------------------------------|
| Frontend           | Next.js + React + Tailwind  | Chat UI, file upload, streaming responses  |
| Backend            | Python + FastAPI            | Async, easy Docker SDK integration         |
| LLM                | Claude API (Sonnet/Opus)    | Best code generation, long context for papers |
| Container runtime  | Docker + docker-py SDK      | Local, fast, image caching                 |
| Database API       | FastAPI (same backend or separate) | Dataset mounting and caching          |
| Paper parsing      | Claude API (PDF vision) or PyMuPDF | Extract text + figures from papers   |
| Real-time comms    | WebSocket                   | Stream execution output to chat UI         |

---

## File Structure

```
research-agent/
├── frontend/                    # Next.js chat UI
│   ├── app/
│   │   ├── page.tsx             # Chat interface
│   │   ├── api/                 # API routes (proxy to backend)
│   │   └── components/
│   │       ├── ChatWindow.tsx
│   │       ├── PaperUpload.tsx
│   │       ├── PlanReview.tsx   # User reviews/edits analysis plan
│   │       └── ResultsView.tsx  # Plots, tables, downloads
│   └── package.json
│
├── backend/
│   ├── main.py                  # FastAPI app entry
│   ├── agent/
│   │   ├── orchestrator.py      # Main agent loop (steps 1-9)
│   │   ├── paper_parser.py      # PDF/URL → extracted methods
│   │   ├── planner.py           # Methods → analysis plan
│   │   ├── code_writer.py       # Plan → executable script
│   │   ├── evaluator.py         # Output → success/retry decision
│   │   └── image_resolver.py    # Pick or build Docker image
│   ├── docker/
│   │   ├── executor.py          # docker-py wrapper (run, exec, commit)
│   │   └── image_cache.py       # Cached image lookup + cleanup
│   ├── data/
│   │   ├── api.py               # Database API (mount datasets)
│   │   ├── geo.py               # GEO downloader
│   │   └── tcga.py              # TCGA downloader
│   └── requirements.txt
│
├── images/                      # Dockerfiles for base images
│   ├── python-spatial.Dockerfile
│   ├── r-rnaseq.Dockerfile
│   ├── python-chipseq.Dockerfile
│   └── python-general.Dockerfile
│
├── docker-compose.yml           # Frontend + backend + (optional) postgres
├── .env.example                 # ANTHROPIC_API_KEY, etc.
└── README.md
```

---

## Phases

### Phase 1: Skeleton (week 1)

- [ ] FastAPI backend with WebSocket endpoint
- [ ] Paper upload endpoint (PDF → text via PyMuPDF or Claude vision)
- [ ] Claude API integration (single call: paper text → analysis plan)
- [ ] Basic chat UI (Next.js) — send message, see response
- [ ] One base Dockerfile (`python-general`)
- [ ] `docker exec` wrapper — run a hardcoded script in container

**Milestone:** Upload a paper, see an analysis plan in chat, manually run a script in container.

### Phase 2: Agent loop (week 2-3)

- [ ] Full orchestrator: parse → plan → code → execute → evaluate
- [ ] Plan review step — user can edit plan before execution
- [ ] Code generation from plan (Claude API)
- [ ] Self-correction loop (read stderr → rewrite → retry, max 3)
- [ ] Stream stdout/stderr to chat UI in real-time via WebSocket
- [ ] Results display — render plots (PNG/SVG), tables, download links

**Milestone:** Upload paper, approve plan, agent writes and runs analysis, returns results.

### Phase 3: Image management (week 3-4)

- [ ] Build 4 base images (python-spatial, r-rnaseq, python-chipseq, python-general)
- [ ] Image resolver — agent decides which base image fits the analysis
- [ ] Dynamic package install + `docker commit` for caching
- [ ] Image cache lookup (check if extended image already exists)
- [ ] Cleanup policy (prune old cached images)

**Milestone:** Agent picks correct image, installs extra packages if needed, cached for next time.

### Phase 4: Database API (week 4-5)

- [ ] Dataset mount endpoint — given dataset ID, return host path
- [ ] GEO downloader (GSE ID → local cache → mount)
- [ ] TCGA downloader (TCGA project ID → local cache → mount)
- [ ] User file upload → stored locally → mountable
- [ ] Agent can request datasets in the planning step

**Milestone:** Agent reads paper, identifies needed dataset, fetches and mounts it automatically.

### Phase 5: Polish (week 5-6)

- [ ] Conversation history (persist chats, reference previous analyses)
- [ ] Export results as report (PDF or markdown)
- [ ] Multiple concurrent sessions
- [ ] Error handling and graceful degradation
- [ ] Resource limits (container memory/CPU caps, execution timeout)
- [ ] Basic auth (single user MVP, but wired for multi-user later)

---

## Key Design Decisions

1. **Claude API over local models** — code generation quality matters more than latency for this use case; Claude Sonnet/Opus writes better analysis code than any local model
2. **Multiple base images over one fat image** — avoids package conflicts (Python vs R, version clashes), keeps images lean, agent picks the right one
3. **Agent-extended cached images** — first run installs extra packages (2-5 min), `docker commit` saves it, every subsequent run is <1 second
4. **Database API mounts data** — containers never fetch data themselves; clean separation, cacheable, reusable across sessions
5. **Plan review before execution** — user sees and can edit the analysis plan before the agent writes code; avoids wasted compute on wrong approaches
6. **WebSocket streaming** — user sees execution output in real-time, not after completion

---

## .env.example

```bash
# LLM
ANTHROPIC_API_KEY=sk-ant-api03-...
CLAUDE_MODEL=claude-sonnet-4-5-20250929

# Docker
DOCKER_HOST=unix:///var/run/docker.sock
IMAGE_CACHE_MAX_GB=50
IMAGE_CACHE_MAX_AGE_DAYS=30
CONTAINER_MEMORY_LIMIT=16g
CONTAINER_CPU_LIMIT=8
EXECUTION_TIMEOUT_SECONDS=3600

# Data
DATA_CACHE_DIR=/data/datasets
GEO_MIRROR=https://ftp.ncbi.nlm.nih.gov/geo/
GDC_API=https://api.gdc.cancer.gov

# App
FRONTEND_PORT=3000
BACKEND_PORT=8000
```
