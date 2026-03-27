#!/bin/bash
# Start both backend and frontend for local development

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# Check for .env
if [ ! -f "$DIR/.env" ]; then
  echo "Creating .env from .env.example..."
  cp "$DIR/.env.example" "$DIR/.env"
  echo "⚠  Edit .env and add your ANTHROPIC_API_KEY before running analyses."
fi

# Install backend deps if needed
if ! python -c "import fastapi" 2>/dev/null; then
  echo "Installing backend dependencies..."
  pip install -r "$DIR/backend/requirements.txt"
fi

# Install frontend deps if needed
if [ ! -d "$DIR/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$DIR/frontend" && npm install)
fi

# Start backend
echo "Starting backend on :8000..."
(cd "$DIR/backend" && uvicorn main:app --reload --port 8000) &
BACKEND_PID=$!

# Wait for backend to be ready
for i in $(seq 1 15); do
  if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "Backend ready."
    break
  fi
  sleep 1
done

# Start frontend
echo "Starting frontend on :3000..."
(cd "$DIR/frontend" && NEXT_PUBLIC_CONTROL_API_TOKEN="${CONTROL_API_TOKEN:-}" npm run dev) &
FRONTEND_PID=$!

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM EXIT

echo ""
echo "App running:"
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8000"
echo "  API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

wait
