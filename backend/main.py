"""FastAPI backend — REST + WebSocket endpoints for the research agent."""

import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from agent.orchestrator import Orchestrator, SessionState
from config import settings
from container_runtime.image_cache import ImageCache
from security import (
    control_token_http_middleware,
    require_dev_endpoints_enabled,
    websocket_authenticated,
)
from skills.manager import SkillManager
from skills.models import SkillCreate
from memory.manager import MemoryManager
from memory.models import LessonCreate

app = FastAPI(title="Research Agent", version="0.1.0")

# CORS for frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(control_token_http_middleware)

orchestrator = Orchestrator()
image_cache = ImageCache()
skill_manager = SkillManager()
memory_manager = MemoryManager()

# --- REST Endpoints ---


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/sessions")
async def create_session():
    """Create a new analysis session."""
    session = orchestrator.create_session()
    return {"session_id": session.id}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session state and messages."""
    session = orchestrator.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session.id,
        "state": session.state.value,
        "messages": [
            {"role": m.role, "content": m.content, "type": m.msg_type, "data": m.data}
            for m in session.messages
        ],
    }


@app.get("/api/sessions/{session_id}/files/{file_path:path}")
async def get_output_file(session_id: str, file_path: str):
    """Download an output file from a session workspace."""
    workspace = settings.WORKSPACE_DIR / session_id
    full_path = workspace / file_path

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if not str(full_path.resolve()).startswith(str(workspace.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(full_path, filename=full_path.name)


@app.get("/api/sessions/{session_id}/download")
async def download_workspace(session_id: str):
    """Download the entire workspace output as a zip file."""
    import zipfile
    import tempfile

    workspace = settings.WORKSPACE_DIR / session_id
    if not workspace.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    # Collect all files to zip: output/, analysis_log.md, analysis script
    files_to_zip = []

    output_dir = workspace / "output"
    if output_dir.exists():
        for f in output_dir.rglob("*"):
            if f.is_file():
                files_to_zip.append((f, f"output/{f.relative_to(output_dir)}"))

    log_file = workspace / "analysis_log.md"
    if log_file.exists():
        files_to_zip.append((log_file, "analysis_log.md"))

    for ext in ["py", "R"]:
        script = workspace / f"analysis.{ext}"
        if script.exists():
            files_to_zip.append((script, f"analysis.{ext}"))

    if not files_to_zip:
        raise HTTPException(status_code=404, detail="No output files found")

    # Create zip
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path, archive_name in files_to_zip:
            zf.write(file_path, archive_name)
    tmp.close()

    return FileResponse(
        tmp.name,
        filename=f"analysis_{session_id[:8]}.zip",
        media_type="application/zip",
    )


@app.get("/api/images")
async def list_images():
    """List cached Docker images."""
    return {"images": image_cache.list_cached_images()}


@app.post("/api/images/prune")
async def prune_images():
    """Prune old cached images."""
    removed = image_cache.prune_old_images()
    image_cache.prune_by_size()
    return {"removed": removed}


@app.get("/api/datasets")
async def list_datasets():
    """List cached datasets."""
    return {"datasets": orchestrator.data_api.list_cached_datasets()}


@app.get("/api/sessions/{session_id}/log")
async def get_analysis_log(session_id: str):
    """Get the analysis log for a session."""
    log_path = settings.WORKSPACE_DIR / session_id / "analysis_log.md"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="No analysis log for this session")
    return FileResponse(log_path, filename=f"analysis_log_{session_id[:8]}.md", media_type="text/markdown")


@app.get("/api/data/status")
async def data_status():
    """List all registered data with availability status."""
    from data.data_manager import DataManager
    dm = DataManager()
    return {"data": dm.list_all()}


@app.get("/api/data/check/{skill_name}")
async def check_data_requirements(skill_name: str):
    """Check data requirements for a skill."""
    from data.data_manager import DataManager
    dm = DataManager()
    return dm.check_requirements(skill_name)


# --- User Data Upload ---

# User data directory: data/user/ → mounted as /data/user/ in containers
USER_DATA_DIR = Path(settings.DATA_CACHE_DIR).parent / "user"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_SIZE = 5 * 1024 * 1024 * 1024  # 5GB


@app.post("/api/data/upload")
async def upload_data(file: UploadFile = File(...)):
    """Upload a data file (max 5GB). Saved to data/user/ and mounted as /data/user/ in containers."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Sanitize filename — keep only safe characters
    import re
    safe_name = re.sub(r'[^\w.\-]', '_', file.filename)
    dest = USER_DATA_DIR / safe_name

    # Stream to disk in chunks to handle large files
    total = 0
    chunk_size = 8 * 1024 * 1024  # 8MB chunks
    try:
        with open(dest, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File exceeds 5GB limit")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    size_mb = total / (1024 * 1024)
    return {
        "filename": safe_name,
        "size_mb": round(size_mb, 1),
        "host_path": str(dest),
        "container_path": f"/data/user/{safe_name}",
    }


@app.get("/api/data/files")
async def list_user_files():
    """List all files in the user data directory."""
    files = []
    if USER_DATA_DIR.exists():
        for f in sorted(USER_DATA_DIR.iterdir()):
            if f.is_file():
                size_mb = f.stat().st_size / (1024 * 1024)
                files.append({
                    "filename": f.name,
                    "size_mb": round(size_mb, 1),
                    "container_path": f"/data/user/{f.name}",
                })
    return {"files": files}


@app.delete("/api/data/files/{filename}")
async def delete_user_file(filename: str):
    """Delete a user-uploaded data file."""
    import re
    safe_name = re.sub(r'[^\w.\-]', '_', filename)
    path = USER_DATA_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if not str(path.resolve()).startswith(str(USER_DATA_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    path.unlink()
    return {"deleted": safe_name}


# --- Dev Endpoints ---


@app.post("/api/dev/replay/{session_id}")
async def replay_session(session_id: str):
    """Dev only: re-execute the plan from a previous session without re-parsing URL or re-planning.

    Loads the session's saved plan and jumps straight to execution.
    Useful when debugging execution failures without burning API tokens on parsing/planning.
    """
    require_dev_endpoints_enabled()
    session = orchestrator.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.plan:
        raise HTTPException(status_code=400, detail="Session has no plan to replay")

    # Reset state for re-execution
    session.state = SessionState.AWAITING_APPROVAL
    session.retry_count = 0
    orchestrator.persist_session(session)

    return {
        "session_id": session.id,
        "state": "awaiting_approval",
        "plan_title": session.plan.get("title"),
        "message": "Session reset to awaiting_approval. Send 'approve' via WebSocket to re-execute.",
    }


@app.get("/api/dev/sessions")
async def list_sessions():
    """Dev only: list all active sessions with their state and plan."""
    require_dev_endpoints_enabled()
    sessions = []
    for sid, s in orchestrator.sessions.items():
        sessions.append({
            "session_id": sid,
            "state": s.state.value,
            "has_plan": bool(s.plan),
            "plan_title": s.plan.get("title") if s.plan else None,
            "has_paper_info": bool(s.paper_info),
            "message_count": len(s.messages),
        })
    return {"sessions": sessions}


@app.delete("/api/dev/url-cache")
async def clear_url_cache():
    """Dev only: clear the URL parse cache."""
    require_dev_endpoints_enabled()
    from agent.paper_parser import _CACHE_DIR
    count = 0
    for f in _CACHE_DIR.glob("*.json"):
        f.unlink()
        count += 1
    return {"cleared": count}


# --- Skills Endpoints ---


@app.get("/api/skills")
async def list_skills(
    analysis_type: str | None = Query(None),
    tag: str | None = Query(None),
):
    """List all pipeline skills, optionally filtered."""
    skills = skill_manager.list_skills(analysis_type=analysis_type, tag=tag)
    return {"skills": [s.model_dump() for s in skills]}


@app.get("/api/skills/{name}")
async def get_skill(name: str):
    """Get a skill by name, including full code template."""
    skill = skill_manager.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill.model_dump()


@app.post("/api/skills")
async def create_skill(data: SkillCreate):
    """Create a new pipeline skill."""
    skill = skill_manager.create_skill(data)
    return skill.model_dump()


@app.put("/api/skills/{name}")
async def update_skill(name: str, data: dict):
    """Update an existing skill."""
    skill = skill_manager.update_skill(name, data)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill.model_dump()


@app.delete("/api/skills/{name}")
async def delete_skill(name: str):
    """Delete a skill."""
    if not skill_manager.delete_skill(name):
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"deleted": True}


# --- Lessons/Memory Endpoints ---


@app.get("/api/lessons")
async def list_lessons(
    tag: str | None = Query(None),
    source: str | None = Query(None),
):
    """List all lessons, optionally filtered by tag or source."""
    lessons = memory_manager.list_lessons(tag=tag, source=source)
    return {"lessons": [l.model_dump() for l in lessons]}


@app.get("/api/lessons/{lesson_id}")
async def get_lesson(lesson_id: str):
    """Get a lesson by ID."""
    lesson = memory_manager.get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson.model_dump()


@app.post("/api/lessons")
async def create_lesson(data: LessonCreate):
    """Create a new lesson (user-saved insight)."""
    lesson = memory_manager.create_lesson(data)
    return lesson.model_dump()


@app.put("/api/lessons/{lesson_id}")
async def update_lesson(lesson_id: str, data: dict):
    """Update an existing lesson."""
    lesson = memory_manager.update_lesson(lesson_id, data)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson.model_dump()


@app.delete("/api/lessons/{lesson_id}")
async def delete_lesson(lesson_id: str):
    """Delete a lesson."""
    if not memory_manager.delete_lesson(lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found")
    return {"deleted": True}


# --- WebSocket Endpoint ---

# Background task management: execution runs independently of WebSocket connection.
# Messages are buffered so reconnecting clients catch up.
import asyncio

# {session_id: asyncio.Task} — tracks running agent tasks
_running_tasks: dict[str, asyncio.Task] = {}


async def _run_agent_loop(session_id: str, content: str, paper_url: str | None):
    """Run the agent loop in the background, buffering messages on the session."""
    session = orchestrator.get_session(session_id)
    if not session:
        return
    try:
        async for msg in orchestrator.handle_message(session_id, content, paper_url):
            # Messages are already appended to session.messages by the orchestrator.
            # We just need to notify any connected WebSocket.
            pass
    except asyncio.CancelledError:
        raise
    except Exception as e:
        if session:
            session.add_message("assistant", f"Error: {e}", msg_type="error")
    finally:
        _running_tasks.pop(session_id, None)


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for real-time chat with the agent.

    Execution runs as a background task so it survives WebSocket disconnects
    (e.g., browser tab switches). The WebSocket polls for new messages and
    streams them to the client. Reconnecting clients catch up on missed messages.
    """
    await websocket.accept()
    if not websocket_authenticated(websocket):
        await websocket.send_text(json.dumps({
            "role": "assistant",
            "content": "Control token required",
            "type": "error",
            "data": {},
            "state": "failed",
        }))
        await websocket.close(code=1008)
        return

    # Ensure session exists
    session = orchestrator.get_session(session_id)
    if not session:
        session = orchestrator.create_session(session_id=session_id)

    # Track how many messages this client has already seen
    seen = 0

    async def flush_new_messages():
        """Send any new messages the client hasn't seen yet."""
        nonlocal seen
        while seen < len(session.messages):
            msg = session.messages[seen]
            seen += 1
            try:
                await websocket.send_text(json.dumps({
                    "role": msg.role,
                    "content": msg.content,
                    "type": msg.msg_type,
                    "data": msg.data,
                    "state": session.state.value,
                }))
            except Exception:
                return False
        return True

    try:
        # Send any existing messages (reconnect catch-up)
        await flush_new_messages()

        while True:
            # Wait for client message with a timeout so we can also flush agent messages
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
            except asyncio.TimeoutError:
                # No client message — just flush any new agent messages
                if not await flush_new_messages():
                    break
                continue

            payload = json.loads(data)
            content = payload.get("content", "")
            paper_url = payload.get("paper_url")

            # Check if user wants to save a lesson via chat
            if content.lower().startswith("/lesson ") or content.lower().startswith("/save "):
                lesson_text = content.split(" ", 1)[1] if " " in content else ""
                if lesson_text:
                    lesson = memory_manager.create_lesson(LessonCreate(
                        title=lesson_text[:100],
                        content=lesson_text,
                        tags=[],
                        source="user",
                        session_id=session_id,
                    ))
                    session.add_message("assistant", f"Lesson saved: **{lesson.title}**",
                                        msg_type="system", data={"lesson_id": lesson.id})
                await flush_new_messages()
                continue

            # Add user message to session (so it's visible on reconnect)
            # Note: handle_message also adds it, so we skip adding here
            # and let the orchestrator handle it.

            existing = _running_tasks.get(session_id)
            if existing and not existing.done():
                session.add_message(
                    "assistant",
                    "A run is already active for this session. Wait for it to finish or start a new session.",
                    msg_type="system",
                )
                await flush_new_messages()
                continue

            # Run agent loop as background task
            task = asyncio.create_task(_run_agent_loop(session_id, content, paper_url))
            _running_tasks[session_id] = task

            # Give the task a moment to start producing messages, then flush
            await asyncio.sleep(0.1)
            await flush_new_messages()

    except WebSocketDisconnect:
        pass  # Agent task keeps running in background
    except Exception:
        pass  # Agent task keeps running in background
