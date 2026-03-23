"""Pydantic models for the lesson/memory store."""

from datetime import datetime
from pydantic import BaseModel, Field


class Lesson(BaseModel):
    id: str
    title: str
    content: str
    tags: list[str] = []
    source: str = "user"  # "user" or "agent"
    session_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class LessonCreate(BaseModel):
    title: str
    content: str
    tags: list[str] = []
    source: str = "user"
    session_id: str | None = None


class LessonUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None
