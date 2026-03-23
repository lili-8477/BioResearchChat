#!/bin/bash
# Start Research Agent for production behind Nginx at /tools
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Build frontend with /tools base path
echo "Building frontend..."
cd "$DIR/frontend"
NEXT_PUBLIC_BACKEND_URL=https://selfai.cc/tools/api \
NEXT_PUBLIC_BASE_PATH=/tools \
npm run build

# Start backend
echo "Starting backend on :8001..."
cd "$DIR/backend"
uvicorn main:app --host 127.0.0.1 --port 8001 &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on :3000..."
cd "$DIR/frontend"
NEXT_PUBLIC_BACKEND_URL=https://selfai.cc/tools/api \
NEXT_PUBLIC_BASE_PATH=/tools \
npm start &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM EXIT

echo ""
echo "Research Agent running at https://selfai.cc/tools"
echo "  Backend:  127.0.0.1:8001"
echo "  Frontend: 127.0.0.1:3000"
echo ""

wait
