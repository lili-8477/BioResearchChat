"""FastAPI backend — REST + WebSocket endpoints for the research agent."""

import json
import os
import uuid
from pathlib import Path

import aiofiles
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from agent.orchestrator import Orchestrator, SessionState
from config import settings
from container_runtime.image_cache import ImageCache
from skills.manager import SkillManager
from skills.models import SkillCreate
from memory.manager import MemoryManager
from memory.models import LessonCreate

app = FastAPI(title="Research Agent", version="0.1.0")

# CORS for frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = Orchestrator()
image_cache = ImageCache()
skill_manager = SkillManager()
memory_manager = MemoryManager()

# Ensure upload directory exists
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


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


@app.post("/api/sessions/{session_id}/upload")
async def upload_paper(session_id: str, file: UploadFile = File(...)):
    """Upload a PDF paper for analysis."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.pdf"
    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    return {"file_id": file_id, "path": str(file_path), "filename": file.filename}


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


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for real-time chat with the agent."""
    await websocket.accept()

    # Ensure session exists
    session = orchestrator.get_session(session_id)
    if not session:
        session = orchestrator.create_session()
        orchestrator.sessions.pop(session.id)
        session.id = session_id
        orchestrator.sessions[session_id] = session

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            content = payload.get("content", "")
            pdf_path = payload.get("pdf_path")
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
                    await websocket.send_text(json.dumps({
                        "role": "assistant",
                        "content": f"Lesson saved: **{lesson.title}**",
                        "type": "system",
                        "data": {"lesson_id": lesson.id},
                        "state": session.state.value,
                    }))
                continue

            async for msg in orchestrator.handle_message(session_id, content, pdf_path, paper_url):
                await websocket.send_text(json.dumps({
                    "role": msg.role,
                    "content": msg.content,
                    "type": msg.msg_type,
                    "data": msg.data,
                    "state": session.state.value,
                }))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({
                "role": "assistant",
                "content": f"Error: {str(e)}",
                "type": "error",
                "data": {},
                "state": "failed",
            }))
        except Exception:
            pass
