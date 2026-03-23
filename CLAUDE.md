# CLAUDE.md — Research Agent MVP

## What is this project?
A self-hosted "Claude Code for bioinformatics research." Users upload a paper (PDF/URL) and ask a research question via a chat UI. The agent reads the paper, plans the analysis, picks a Docker container with the right tools, writes and executes code, self-corrects on errors, and returns results.

## Architecture
- **Frontend**: Next.js + React chat UI with WebSocket streaming
- **Backend**: Python + FastAPI orchestrator
- **LLM**: Claude API (Sonnet or Opus) — all reasoning, code gen, evaluation
- **Execution**: Docker containers via docker-py SDK
- **Data**: Database API that mounts GEO/TCGA/local datasets into containers

## Agent loop
1. Parse paper → extract methods, tools, data requirements
2. Generate analysis plan → user reviews/edits
3. Resolve environment → pick base image, install extra packages if needed, cache
4. Mount data from database API
5. Write analysis code
6. Execute in container, stream output
7. Evaluate → retry up to 3x on failure
8. Return results (plots, tables, files)

## Base images (Dockerfiles in `images/`)
- `python-spatial` — scanpy, squidpy, celltypist
- `r-rnaseq` — DESeq2, hciR, edgeR
- `python-chipseq` — deeptools, macs2
- `python-general` — pandas, numpy, scikit-learn

Agent can extend base images with extra packages via `pip install` + `docker commit`. Cached images use naming: `research-agent/python-spatial:base+scvi+cellpose`

## Key directories
- `frontend/` — Next.js app
- `backend/agent/` — orchestrator, paper parser, planner, code writer, evaluator, image resolver
- `backend/docker/` — docker-py executor + image cache
- `backend/data/` — database API, GEO/TCGA downloaders
- `images/` — base image Dockerfiles

## Tech constraints
- All containers get `-v /data:/data` mount from database API
- Container limits: 16GB RAM, 8 CPU, 1hr timeout (configurable in .env)
- Image cache: max 50GB, prune after 30 days
- WebSocket for real-time streaming of execution output
- Plan review step is mandatory — user approves before code runs

## Commands
```bash
# Start everything
docker compose up -d

# Build base images
docker build -t research-agent/python-spatial:base -f images/python-spatial.Dockerfile .
docker build -t research-agent/r-rnaseq:base -f images/r-rnaseq.Dockerfile .

# Run backend dev
cd backend && uvicorn main:app --reload --port 8000

# Run frontend dev  
cd frontend && npm run dev
```

## Environment variables
See `.env.example` — needs ANTHROPIC_API_KEY at minimum.
