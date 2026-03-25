---
name: env_setup
description: "Environment setup checklist: check data, download models, build images, verify mounts"
analysis_type: setup
base_image: python-general
language: python
packages: []
tags: [setup, environment, docker, models, data, prerequisites]
---

# Environment Setup Checklist

## When to use
- Before running any analysis for the first time
- When a skill requires models, references, or atlases not yet downloaded
- This is an agent-side checklist, NOT a container script

## Steps

1. **Check data registry** — read `backend/data/registry.yaml` for available datasets
   ```bash
   python -c "
     import sys; sys.path.insert(0, 'backend')
     from data.data_manager import DataManager
     dm = DataManager()
     print(dm.status_report())
   "
   ```

2. **Check skill requirements** — verify data for the target analysis
   ```bash
   python -c "
     import sys; sys.path.insert(0, 'backend')
     from data.data_manager import DataManager
     dm = DataManager()
     req = dm.check_requirements('scimilarity_cell_annotation')
     for m in req['missing']:
         print(f'MISSING: {m[\"name\"]} ({m[\"size_gb\"]}GB)')
     if req['ready']:
         print('All data available!')
   "
   ```

3. **Download missing data**
   ```bash
   ./scripts/download-model.sh <name>
   ```

4. **Check Docker images**
   ```bash
   docker images | grep research-agent
   # If missing:
   docker build -t research-agent/python-spatial:base -f images/python-spatial.Dockerfile .
   ```

5. **Verify mounts**
   ```bash
   python -c "
     import sys; sys.path.insert(0, 'backend')
     from data.data_manager import DataManager
     dm = DataManager()
     for host, container in dm.get_all_mounts().items():
         print(f'{host} -> {container}')
   "
   ```

6. **Test run**
   ```bash
   docker run --rm \
     -v ./data/user:/data/user:ro \
     -v ./data/models:/data/models:ro \
     research-agent/python-spatial:base \
     python -c "import scanpy; print('OK')"
   ```
