#!/bin/bash
# Launch BioResearchChat with Claude Code (uses your Max plan)
#
# Usage:
#   ./run-agent.sh                          # interactive mode
#   ./run-agent.sh "analyze my scRNA-seq"   # with a prompt
#
# Put your data files in data/user/ before running.

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Show what data is available
echo "=== Data files ==="
ls -lh data/user/ 2>/dev/null || echo "(empty — put your files in data/user/)"
echo ""

if [ -n "$1" ]; then
  # Run with a prompt
  claude -p "Read program.md, then: $*"
else
  # Interactive mode
  claude "Read program.md and help me with my bioinformatics analysis. Start by checking what data I have in data/user/"
fi
