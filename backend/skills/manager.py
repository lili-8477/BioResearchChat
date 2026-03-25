"""Skill manager — loads, searches, and manages pipeline templates.

Skills are stored as Markdown files with YAML frontmatter.
Supports progressive loading: registry (metadata only) for planning,
full content loaded on demand for code generation.
"""

from datetime import datetime
from pathlib import Path

import yaml

from config import settings
from skills.models import Skill, SkillCreate


class SkillManager:
    """Manages bioinformatics pipeline skill templates with progressive loading.

    Two-tier loading:
    - get_registry(): lightweight metadata (name, description, tags) for planning (~50 tokens/skill)
    - load_skill_content(): full markdown body for code generation (loaded on demand)
    """

    def __init__(self, skills_dir: Path | None = None):
        self.skills_dir = skills_dir or settings.SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._registry: list[dict] | None = None
        self._skills_cache: dict[str, Skill] = {}

    @staticmethod
    def _parse_md(path: Path) -> tuple[dict, str]:
        """Parse a Markdown file with YAML frontmatter. Returns (metadata, body)."""
        text = path.read_text()
        if not text.startswith("---"):
            raise ValueError(f"No YAML frontmatter in {path}")
        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid frontmatter in {path}")
        meta = yaml.safe_load(parts[1])
        body = parts[2].strip()
        return meta, body

    def _load_skill(self, path: Path) -> Skill:
        """Load a single skill from a Markdown file with YAML frontmatter."""
        meta, body = self._parse_md(path)
        meta["code_template"] = body
        return Skill(**meta)

    def _ensure_cache(self):
        """Load all skills into cache if not already loaded."""
        if self._skills_cache:
            return
        for path in sorted(self.skills_dir.glob("*.md")):
            try:
                skill = self._load_skill(path)
                self._skills_cache[skill.name] = skill
            except Exception:
                continue

    def _invalidate_cache(self):
        """Clear caches so next access reloads from disk."""
        self._registry = None
        self._skills_cache.clear()

    # --- Progressive Loading API ---

    def get_registry(self) -> list[dict]:
        """Return lightweight skill metadata for planning. No code_template.

        This is what the planner sees — just enough to pick the right skill.
        ~50 tokens per skill vs ~800 tokens with full code.
        """
        if self._registry is not None:
            return self._registry
        self._registry = []
        for path in sorted(self.skills_dir.glob("*.md")):
            try:
                meta, _ = self._parse_md(path)
                self._registry.append({
                    "name": meta["name"],
                    "description": meta["description"],
                    "analysis_type": meta.get("analysis_type", ""),
                    "base_image": meta.get("base_image", ""),
                    "language": meta.get("language", "python"),
                    "packages": meta.get("packages", []),
                    "tags": meta.get("tags", []),
                })
            except Exception:
                continue
        return self._registry

    def load_skill_content(self, name: str) -> str | None:
        """Load the full markdown body for a specific skill. Called at code-gen time.

        Returns the markdown content (prose + code blocks) or None if not found.
        """
        self._ensure_cache()
        skill = self._skills_cache.get(name)
        if skill:
            return skill.code_template
        # Case-insensitive fallback
        for sname, s in self._skills_cache.items():
            if sname.lower() == name.lower():
                return s.code_template
        return None

    # --- Full Skill Access ---

    def list_skills(
        self,
        analysis_type: str | None = None,
        tag: str | None = None,
    ) -> list[Skill]:
        """List all skills, optionally filtered by analysis_type or tag."""
        self._ensure_cache()
        skills = []
        for skill in self._skills_cache.values():
            if analysis_type and skill.analysis_type != analysis_type:
                continue
            if tag and tag not in skill.tags:
                continue
            skills.append(skill)
        return skills

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""
        self._ensure_cache()
        skill = self._skills_cache.get(name)
        if skill:
            return skill
        for sname, s in self._skills_cache.items():
            if sname.lower() == name.lower():
                return s
        return None

    def create_skill(self, data: SkillCreate) -> Skill:
        """Create a new skill from user input."""
        skill = Skill(
            **data.model_dump(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._save_skill(skill)
        self._invalidate_cache()
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
        self._invalidate_cache()
        return skill

    def delete_skill(self, name: str) -> bool:
        """Delete a skill by name."""
        path = self.skills_dir / f"{name}.md"
        if path.exists():
            path.unlink()
            self._invalidate_cache()
            return True
        return False

    def _save_skill(self, skill: Skill):
        """Save a skill as Markdown with YAML frontmatter."""
        path = self.skills_dir / f"{skill.name}.md"
        meta = {
            "name": skill.name,
            "description": skill.description,
            "analysis_type": skill.analysis_type,
            "base_image": skill.base_image,
            "language": skill.language,
            "packages": skill.packages,
            "tags": skill.tags,
        }
        frontmatter = yaml.dump(meta, default_flow_style=False, sort_keys=False)
        body = skill.code_template or ""
        path.write_text(f"---\n{frontmatter}---\n\n{body}\n")

    # --- Search (uses registry for lightweight matching) ---

    def search_registry(
        self,
        query: str = "",
        analysis_type: str | None = None,
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Search skills using registry metadata only. Returns lightweight dicts.

        Used by the planner — no code_template in results.
        """
        registry = self.get_registry()
        if not registry:
            return []

        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for entry in registry:
            score = 0

            # Analysis type match (strong signal)
            entry_type = entry.get("analysis_type", "").lower()
            if analysis_type:
                if entry_type == analysis_type.lower():
                    score += 10
                elif analysis_type.lower() in entry_type:
                    score += 5

            # Tag match
            if tags:
                entry_tags_lower = [t.lower() for t in entry.get("tags", [])]
                for tag in tags:
                    if tag.lower() in entry_tags_lower:
                        score += 3

            # Query keyword overlap with name, description, tags
            entry_text = f"{entry['name']} {entry['description']} {' '.join(entry.get('tags', []))}".lower()
            for word in query_words:
                if len(word) > 2 and word in entry_text:
                    score += 2

            # Package name overlap
            for pkg in entry.get("packages", []):
                if pkg.lower() in query_lower:
                    score += 4

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:limit]]

    def search_skills(
        self,
        query: str = "",
        analysis_type: str | None = None,
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[Skill]:
        """Search skills returning full Skill objects. Used when full data is needed."""
        matched = self.search_registry(query, analysis_type, tags, limit)
        skills = []
        for entry in matched:
            skill = self.get_skill(entry["name"])
            if skill:
                skills.append(skill)
        return skills
