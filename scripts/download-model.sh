#!/bin/bash
# Download large datasets from the registry to data/ (mounted into containers)
#
# Usage:
#   ./scripts/download-model.sh list                    # show all datasets + status
#   ./scripts/download-model.sh check <skill>           # check what a skill needs
#   ./scripts/download-model.sh get <name>              # download a specific dataset
#   ./scripts/download-model.sh setup <skill>           # download everything a skill needs
#
# Data layout:
#   data/models/      → /data/models/      (pretrained models)
#   data/references/  → /data/references/  (genomes, annotations)
#   data/atlases/     → /data/atlases/     (cell atlases)
#   data/user/        → /data/user/        (your files)

set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

# Use Python DataManager for registry operations
run_dm() {
    python3 -c "
import sys; sys.path.insert(0, 'backend')
from data.data_manager import DataManager
dm = DataManager()
$1
"
}

case "${1:-}" in
    list)
        echo "=== Data Registry Status ==="
        echo ""
        run_dm "print(dm.status_report())"
        echo ""
        echo "Total cached: $(du -sh data/ 2>/dev/null | cut -f1)"
        ;;

    check)
        if [ -z "$2" ]; then
            echo "Usage: $0 check <skill_name>"
            echo "Example: $0 check scimilarity_cell_annotation"
            exit 1
        fi
        run_dm "
req = dm.check_requirements('$2')
if req['ready']:
    print('All data available for $2!')
else:
    print('Missing data for $2:')
    for m in req['missing']:
        print(f'  - {m[\"name\"]} ({m.get(\"size_gb\",\"?\")}GB): {m[\"description\"]}')
    print()
    print('Download with:')
    for m in req['missing']:
        print(f'  $0 get {m[\"name\"]}')
"
        ;;

    get)
        if [ -z "$2" ]; then
            echo "Usage: $0 get <dataset_name>"
            echo "Run '$0 list' to see available datasets."
            exit 1
        fi
        run_dm "dm.download('$2')"
        ;;

    setup)
        if [ -z "$2" ]; then
            echo "Usage: $0 setup <skill_name>"
            echo "Downloads all data needed for a skill."
            exit 1
        fi
        echo "Setting up data for skill: $2"
        run_dm "
req = dm.check_requirements('$2')
if req['ready']:
    print('All data already available!')
else:
    for m in req['missing']:
        print(f'Downloading {m[\"name\"]}...')
        dm.download(m['name'])
"
        # Also check Docker image
        echo ""
        echo "Checking Docker images..."
        if docker images | grep -q "research-agent"; then
            echo "Base images found."
        else
            echo "No base images found. Build with:"
            echo "  docker build -t research-agent/python-spatial:base -f images/python-spatial.Dockerfile ."
        fi
        ;;

    *)
        echo "Data Manager — download and cache large datasets for analysis"
        echo ""
        echo "Usage:"
        echo "  $0 list                  Show all datasets and their status"
        echo "  $0 check <skill>         Check data requirements for a skill"
        echo "  $0 get <name>            Download a specific dataset"
        echo "  $0 setup <skill>         Download everything a skill needs"
        echo ""
        echo "Examples:"
        echo "  $0 list"
        echo "  $0 check scimilarity_cell_annotation"
        echo "  $0 get scimilarity_v1.1"
        echo "  $0 setup scimilarity_cell_annotation"
        echo ""
        echo "For self-hosting, set DATA_MIRROR in .env to your own S3/HTTP mirror."
        ;;
esac
