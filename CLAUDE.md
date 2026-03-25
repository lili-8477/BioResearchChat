# CLAUDE.md — Research Agent MVP

## What is this project?
A self-hosted "Claude Code for bioinformatics research." Users paste a URL (GitHub repo or science paper) and ask a research question via a chat UI. The agent parses the URL, guides the user, searches skills and memory, plans the analysis, picks a Docker container, writes and executes code, self-corrects on errors, and returns results.

## Architecture
- **Frontend**: Next.js + React chat UI with WebSocket streaming
- **Backend**: Python + FastAPI orchestrator
- **LLM**: Claude API (Sonnet or Opus) — all reasoning, code gen, evaluation
- **Execution**: Docker containers via docker-py SDK
- **URL parsing**: GitHub API for repos, crawl4ai for papers/docs, Claude Vision for PDFs
- **Skills**: Markdown templates with progressive loading (registry for planning, full content for code gen)
- **Memory**: QMD hybrid search (BM25 + vector) on markdown lessons
- **Data**: Database API that mounts GEO/TCGA/local/user datasets into containers

## Agent loop
1. Parse URL → extract purpose, input, method, output (URL is optional)
2. Guide user → clarify underspecified requests via conversation
3. Search skills (registry metadata only) + memory (QMD hybrid search)
4. Generate analysis plan → user reviews/edits (multi-round)
5. Load selected skill content on demand (single skill only)
6. Resolve environment → pick base image, install extra packages if needed, cache
7. Mount data from database API + user uploads
8. Write analysis code
9. Execute in container, stream output
10. Evaluate → retry up to 3x on failure
11. Return results (plots, tables, files) + write analysis log + extract lessons

## Base images (Dockerfiles in `images/`)
- `python-spatial` — scanpy, squidpy, celltypist
- `python-scimilarity` — scanpy, scimilarity, hnswlib (cell annotation/query)
- `r-rnaseq` — DESeq2, hciR, edgeR
- `python-chipseq` — deeptools, macs2
- `python-general` — pandas, numpy, scikit-learn

Agent can extend base images with extra packages via `pip install` + `docker commit`. Cached images use naming: `research-agent/python-spatial:base+scvi+cellpose`

## Key directories
- `frontend/` — Next.js app
- `backend/agent/` — orchestrator, paper parser, planner, code writer, evaluator, image resolver
- `backend/skills/templates/` — Markdown skill files with YAML frontmatter
- `backend/memory/lessons/` — Markdown lesson files (auto-extracted from successful analyses)
- `backend/container_runtime/` — docker-py executor + image cache
- `backend/data/` — database API, GEO/TCGA downloaders, data registry
- `backend/tests/` — test scripts with markdown reports
- `images/` — base image Dockerfiles
- `data/` — models, references, atlases, user data (gitignored)
- `workspaces/` — per-session output + analysis logs (gitignored)

## Tech constraints
- All containers get auto-mounts: `/data/user/`, `/data/models/`, `/data/references/`, `/data/atlases/`
- Container limits: 16GB RAM, 8 CPU, 1hr timeout (configurable in .env)
- Image cache: max 50GB, prune after 30 days
- User data upload: max 5GB per file via HTTP, saved to `data/user/`
- WebSocket for real-time streaming of execution output
- Plan review step is mandatory — user approves before code runs

## Commands
```bash
# Start everything
docker compose up -d

# Build base images
docker build -t research-agent/python-spatial:base -f images/python-spatial.Dockerfile .
docker build -t research-agent/python-scimilarity:base -f images/python-scimilarity.Dockerfile .
docker build -t research-agent/r-rnaseq:base -f images/r-rnaseq.Dockerfile .

# Run backend dev
cd backend && uvicorn main:app --reload --port 8000

# Run frontend dev
cd frontend && npm run dev

# Run tests
cd backend && python -m tests.test_url_and_skills
```

## Environment variables
See `.env.example` — needs ANTHROPIC_API_KEY at minimum.

## Docker socket setup

The backend uses `docker-py` to manage containers. The `DOCKER_HOST` env var must point to the correct Docker socket.

### macOS (Docker Desktop)
```bash
DOCKER_HOST=unix:///Users/<username>/.docker/run/docker.sock
```

### Linux (standard Docker Engine)
```bash
DOCKER_HOST=unix:///var/run/docker.sock
```

Make sure the user running the backend has permission to access the socket:
```bash
# Check socket exists
ls -la /var/run/docker.sock

# If permission denied, add your user to the docker group
sudo usermod -aG docker $USER
# Then log out and back in (or run: newgrp docker)

# Verify
docker ps
```

### Linux (rootless Docker)
If using rootless Docker:
```bash
DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock
```

### Troubleshooting
If the backend shows `Error while fetching server API version: ('Connection aborted.', FileNotFoundError)`:
1. Check Docker is running: `docker ps`
2. Find the actual socket: `docker context inspect | grep Host`
3. Update `DOCKER_HOST` in `.env` to match
