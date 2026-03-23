"""Skill manager — loads, searches, and manages pipeline templates."""

from datetime import datetime
from pathlib import Path

import yaml

from config import settings
from skills.models import Skill, SkillCreate


class SkillManager:
    """Manages bioinformatics pipeline skill templates."""

    def __init__(self, skills_dir: Path | None = None):
        self.skills_dir = skills_dir or settings.SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def _load_skill(self, path: Path) -> Skill:
        """Load a single skill from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return Skill(**data)

    def list_skills(
        self,
        analysis_type: str | None = None,
        tag: str | None = None,
    ) -> list[Skill]:
        """List all skills, optionally filtered by analysis_type or tag."""
        skills = []
        for path in sorted(self.skills_dir.glob("*.yaml")):
            try:
                skill = self._load_skill(path)
                if analysis_type and skill.analysis_type != analysis_type:
                    continue
                if tag and tag not in skill.tags:
                    continue
                skills.append(skill)
            except Exception:
                continue
        return skills

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""
        path = self.skills_dir / f"{name}.yaml"
        if path.exists():
            return self._load_skill(path)
        # Try case-insensitive match
        for p in self.skills_dir.glob("*.yaml"):
            if p.stem.lower() == name.lower():
                return self._load_skill(p)
        return None

    def create_skill(self, data: SkillCreate) -> Skill:
        """Create a new skill from user input."""
        skill = Skill(
            **data.model_dump(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._save_skill(skill)
        return skill

    def update_skill(self, name: str, data: dict) -> Skill | None:
        """Update an existing skill."""
        skill = self.get_skill(name)
        if not skill:
            return None
        for key, value in data.items():
            if hasattr(skill, key):
                setattr(skill, key, value)
        skill.updated_at = datetime.now()
        self._save_skill(skill)
        return skill

    def delete_skill(self, name: str) -> bool:
        """Delete a skill by name."""
        path = self.skills_dir / f"{name}.yaml"
        if path.exists():
            path.unlink()
            return True
        return False

    def _save_skill(self, skill: Skill):
        """Save a skill to YAML."""
        path = self.skills_dir / f"{skill.name}.yaml"
        data = skill.model_dump()
        data["created_at"] = data["created_at"].isoformat()
        data["updated_at"] = data["updated_at"].isoformat()
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def search_skills(
        self,
        query: str = "",
        analysis_type: str | None = None,
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[Skill]:
        """Search skills by query text, analysis type, or tags.

        Scores skills by keyword overlap with query, type match, and tag match.
        """
        all_skills = self.list_skills()
        if not all_skills:
            return []

        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for skill in all_skills:
            score = 0

            # Analysis type match (strong signal)
            if analysis_type and skill.analysis_type.lower() == analysis_type.lower():
                score += 10
            # Partial type match
            if analysis_type and analysis_type.lower() in skill.analysis_type.lower():
                score += 5

            # Tag match
            if tags:
                for tag in tags:
                    if tag.lower() in [t.lower() for t in skill.tags]:
                        score += 3

            # Query keyword overlap with name, description, tags
            skill_text = f"{skill.name} {skill.description} {' '.join(skill.tags)}".lower()
            for word in query_words:
                if len(word) > 2 and word in skill_text:
                    score += 2

            # Package name overlap
            for pkg in skill.packages:
                if pkg.lower() in query_lower:
                    score += 4

            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:limit]]
