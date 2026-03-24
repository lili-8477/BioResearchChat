# Web UI Architecture — BioResearchChat

```
┌─────────────────────────────────────────────────────────────────────────┐
│  BROWSER (Next.js)                                                      │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐              │
│  │  Chat     │  │  Paper   │  │  Plan    │  │  Results  │              │
│  │  Window   │  │  Upload  │  │  Review  │  │  View     │              │
│  └─────┬────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘              │
│        │             │             │               │                    │
│  ┌─────┴─────────────┴─────────────┴───────────────┴──────┐            │
│  │              WebSocket + REST Client                     │            │
│  └──────────────────────┬──────────────────────────────────┘            │
│         /skills         │          /lessons                             │
│         ┌───────────────┼───────────────────┐                           │
│         │               │                   │                           │
│  ┌──────┴──┐     ┌──────┴──────┐     ┌──────┴───┐                     │
│  │ Skills  │     │    Chat     │     │ Lessons  │                      │
│  │ Browser │     │   page.tsx  │     │ Browser  │                      │
│  └─────────┘     └─────────────┘     └──────────┘                      │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │
              WebSocket /ws/{session_id}
              REST /api/*
                          │
┌─────────────────────────┴───────────────────────────────────────────────┐
│  FASTAPI BACKEND (main.py)                                              │
│                                                                         │
│  REST Endpoints              WebSocket Handler                          │
│  ├─ POST /api/sessions       ├─ Receive message                        │
│  ├─ POST /api/sessions/upload│ ├─ /lesson → save lesson directly       │
│  ├─ GET  /api/skills         │ └─ else → orchestrator.handle_message() │
│  ├─ GET  /api/lessons        │                                          │
│  ├─ GET  /api/data/status    │     Stream responses back via WS         │
│  └─ GET  /api/sessions/files │                                          │
│                              │                                          │
│  Instantiated at startup:                                               │
│  ├─ orchestrator = Orchestrator()                                       │
│  ├─ skill_manager = SkillManager()                                      │
│  ├─ memory_manager = MemoryManager()                                    │
│  └─ image_cache = ImageCache()                                          │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR (agent/orchestrator.py)                                   │
│                                                                         │
│  Session State Machine:                                                 │
│  IDLE → PARSING → PLANNING → AWAITING_APPROVAL → RESOLVING_ENV         │
│       → WRITING_CODE → EXECUTING → EVALUATING → COMPLETED / FAILED     │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                    AGENT LOOP                                  │     │
│  │                                                                │     │
│  │  ┌─────────────┐    ┌──────────────────────────────────────┐  │     │
│  │  │ 1. PARSE    │    │  Skills + Lessons Discovery          │  │     │
│  │  │   PAPER     │    │                                      │  │     │
│  │  │             │    │  skill_manager.search_skills()       │  │     │
│  │  │ PDF → Vision│    │    → scores by type, tags, keywords  │  │     │
│  │  │ URL → fetch │    │    → returns top 3 matches           │  │     │
│  │  │ text → pass │    │                                      │  │     │
│  │  └──────┬──────┘    │  memory_manager.search_lessons()     │  │     │
│  │         │           │    → qmd BM25 search                 │  │     │
│  │         ▼           │    → fallback: keyword matching      │  │     │
│  │  ┌──────────────┐   │    → returns top 5 matches           │  │     │
│  │  │ 2. PLAN      │◄──┘                                      │  │     │
│  │  │              │         Claude API Call #1                │  │     │
│  │  │ paper_info + │         (skills metadata + lessons)       │  │     │
│  │  │ question +   │───────────────────────────┐              │  │     │
│  │  │ skills +     │                           │              │  │     │
│  │  │ lessons      │                           ▼              │  │     │
│  │  └──────┬───────┘                    ┌─────────────┐       │  │     │
│  │         │                            │ Claude API  │       │  │     │
│  │         │ plan JSON                  │ (Sonnet/    │       │  │     │
│  │         ▼                            │  Opus)      │       │  │     │
│  │  ┌──────────────┐                    │             │       │  │     │
│  │  │ → USER       │                    │ LLM Calls:  │       │  │     │
│  │  │   APPROVAL   │                    │ #1 Plan     │       │  │     │
│  │  │              │                    │ #2 Code     │       │  │     │
│  │  │ approve /    │                    │ #3 Evaluate │       │  │     │
│  │  │ modify /     │                    │ #4 Fix code │       │  │     │
│  │  │ reject       │                    │ #5 Lessons  │       │  │     │
│  │  └──────┬───────┘                    └──────┬──────┘       │  │     │
│  │         │ approved                          │              │  │     │
│  │         ▼                                   │              │  │     │
│  │  ┌──────────────┐                           │              │  │     │
│  │  │ 3. RESOLVE   │                           │              │  │     │
│  │  │    ENV       │                           │              │  │     │
│  │  │              │    image_resolver.py       │              │  │     │
│  │  │ base_image + │    ├─ check base exists   │              │  │     │
│  │  │ extra_pkgs   │    ├─ check cached ext    │              │  │     │
│  │  │              │    └─ build + commit if    │              │  │     │
│  │  └──────┬───────┘      new pkgs needed      │              │  │     │
│  │         │                                   │              │  │     │
│  │         ▼                                   │              │  │     │
│  │  ┌──────────────┐   Claude API Call #2      │              │  │     │
│  │  │ 4. WRITE     │◄─────────────────────────┘              │  │     │
│  │  │    CODE      │   (plan + skill templates + lessons)     │  │     │
│  │  │              │                                          │  │     │
│  │  │ → analysis.py│   Includes # REQUIREMENTS: comment      │  │     │
│  │  └──────┬───────┘                                          │  │     │
│  │         │                                                  │  │     │
│  │         ▼                                                  │  │     │
│  │  ┌──────────────┐   ┌──────────────────────────────────┐  │  │     │
│  │  │ 5. EXECUTE   │──▶│  Docker Executor                 │  │  │     │
│  │  │              │   │                                   │  │  │     │
│  │  │              │   │  a. Parse # REQUIREMENTS +imports │  │  │     │
│  │  │  ┌───────┐   │   │  b. Generate setup.sh             │  │  │     │
│  │  │  │Retry  │   │   │     (pip install → run script)    │  │  │     │
│  │  │  │Loop   │   │   │  c. docker run with ALL mounts:   │  │  │     │
│  │  │  │(max 3)│   │   │     /data/user                    │  │  │     │
│  │  │  └───┬───┘   │   │     /data/models                  │  │  │     │
│  │  │      │       │   │     /data/references               │  │  │     │
│  │  │      │       │   │     /data/atlases                  │  │  │     │
│  │  │      │       │   │     /workspace                     │  │  │     │
│  │  │      │       │   │  d. Stream stdout via callback     │  │  │     │
│  │  │      │       │   │  e. On ModuleNotFoundError:        │  │  │     │
│  │  │      │       │   │     install_and_retry() (free)     │  │  │     │
│  │  │      │       │   └───────────────┬───────────────────┘  │  │     │
│  │  └──────┼───────┘                   │                      │  │     │
│  │         │                           │ exit_code + stdout    │  │     │
│  │         ▼                           │ + stderr + files      │  │     │
│  │  ┌──────────────┐                   │                      │  │     │
│  │  │ 6. EVALUATE  │◄─────────────────┘                      │  │     │
│  │  │              │   Claude API Call #3                      │  │     │
│  │  │ success?     │   (stdout + stderr + files + plan)       │  │     │
│  │  │ ├─ YES ──────┼──▶ Return results to user               │  │     │
│  │  │ │            │   + extract_lessons() ── Call #5          │  │     │
│  │  │ └─ NO  ──────┼──▶ fix_code() ── Call #4                │  │     │
│  │  │              │   → back to step 5 (retry)               │  │     │
│  │  └──────────────┘                                          │  │     │
│  └────────────────────────────────────────────────────────────┘  │     │
└──────────────────────────────────────────────────────────────────┘     │
                                                                         │
┌────────────────────────────────────────────────────────────────────────┘
│
│  PERSISTENT STORAGE
│
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────────┐
│  │ skills/         │  │ memory/         │  │ data/                    │
│  │ templates/      │  │ lessons/        │  │                          │
│  │                 │  │                 │  │ user/        (uploads)   │
│  │ *.yaml files    │  │ *.md files      │  │ models/      (28GB+)    │
│  │ 8 pipelines     │  │ qmd indexed     │  │ references/  (genomes)  │
│  │                 │  │ BM25 search     │  │ atlases/     (50GB+)    │
│  └─────────────────┘  └─────────────────┘  └──────────────────────────┘
│
│  ┌─────────────────┐  ┌──────────────────────────────────────────────┐
│  │ Docker Images   │  │ Workspaces                                   │
│  │                 │  │                                              │
│  │ python-scimil.  │  │ workspaces/{session_id}/                    │
│  │ python-spatial  │  │ ├── analysis.py      (generated code)       │
│  │ r-rnaseq       │  │ ├── setup.sh         (install + run)        │
│  │ python-chipseq │  │ └── output/                                  │
│  │ python-general │  │     ├── *.png         (plots)                │
│  │                 │  │     ├── *.csv         (tables)               │
│  │ + cached ext.  │  │     └── *.h5ad        (processed data)       │
│  │   images       │  │                                              │
│  └─────────────────┘  └──────────────────────────────────────────────┘
```

## Request Flow (Sequence)

```
User          Frontend       Backend        Orchestrator     Claude API      Docker
 │               │              │               │               │              │
 │── message ──▶│              │               │               │              │
 │               │── WS ──────▶│               │               │              │
 │               │              │── handle ────▶│               │              │
 │               │              │               │               │              │
 │               │              │               │── find skills │              │
 │               │              │               │── find lessons│              │
 │               │              │               │               │              │
 │               │              │               │── parse ─────▶│ #1           │
 │               │◀── "parsing" ┤◀──────────────┤◀──── JSON ───┤              │
 │               │              │               │               │              │
 │               │              │               │── plan ──────▶│ #2           │
 │               │◀── plan ─────┤◀──────────────┤◀── plan JSON─┤              │
 │               │              │               │               │              │
 │── "approve" ─▶              │               │               │              │
 │               │── WS ──────▶│── approve ───▶│               │              │
 │               │              │               │── resolve img │              │
 │               │              │               │── code ──────▶│ #3           │
 │               │◀── code ─────┤◀──────────────┤◀─── code ────┤              │
 │               │              │               │               │              │
 │               │              │               │── execute ───────────────────▶│
 │               │◀── stdout ───┤◀──────────────┤◀─── stream ─────────────────┤
 │               │              │               │◀─── result ─────────────────┤
 │               │              │               │               │              │
 │               │              │               │── evaluate ──▶│ #4           │
 │               │              │               │◀── success ──┤              │
 │               │              │               │               │              │
 │               │◀── results ──┤◀──────────────┤               │              │
 │               │              │               │── lessons ───▶│ #5           │
 │               │◀── "saved" ──┤◀──────────────┤◀── lessons ──┤              │
 │               │              │               │               │              │
```
