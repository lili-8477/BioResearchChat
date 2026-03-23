"""Pydantic models for skills (established pipeline templates)."""

from datetime import datetime
from pydantic import BaseModel, Field


class Skill(BaseModel):
    name: str
    description: str
    analysis_type: str  # e.g., "bulk_rnaseq", "scrna_seq", "chipseq", "spatial"
    base_image: str  # e.g., "python-spatial", "r-rnaseq"
    language: str = "python"
    packages: list[str] = []
    tags: list[str] = []
    code_template: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SkillCreate(BaseModel):
    name: str
    description: str
    analysis_type: str
    base_image: str
    language: str = "python"
    packages: list[str] = []
    tags: list[str] = []
    code_template: str = ""
