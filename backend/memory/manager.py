"""Memory manager — stores lessons as markdown files, searches with qmd."""

import asyncio
import json
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

import anthropic

from config import settings
from memory.models import Lesson, LessonCreate

EXTRACT_SYSTEM = """You are a bioinformatics analysis reviewer. Given a completed analysis (plan, code, output, evaluation), extract 1-3 key lessons that would help someone doing a similar analysis in the future.

Focus on:
- Non-obvious insights (not just "the code worked")
- Pitfalls or gotchas encountered and how they were resolved
- Useful parameter choices or thresholds that produced good results
- Package/tool recommendations based on what worked well
- Data preprocessing steps that were critical for success

Return JSON array:
[
  {
    "title": "Short descriptive title",
    "content": "Detailed lesson content — what was learned and why it matters",
    "tags": ["relevant", "tags"]
  }
]

If there are no meaningful lessons to extract, return an empty array: []"""


def _lesson_to_markdown(lesson: Lesson) -> str:
    """Convert a lesson to markdown with YAML frontmatter for qmd indexing."""
    tags_str = ", ".join(lesson.tags) if lesson.tags else ""
    return f"""---
id: {lesson.id}
source: {lesson.source}
tags: [{tags_str}]
session_id: {lesson.session_id or ""}
created_at: {lesson.created_at.isoformat() if isinstance(lesson.created_at, datetime) else lesson.created_at}
---

# {lesson.title}

{lesson.content}
"""


def _markdown_to_lesson(path: Path) -> Lesson | None:
    """Parse a lesson markdown file back into a Lesson object."""
    try:
        text = path.read_text()
    except Exception:
        return None

    # Parse frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm_match:
        return None

    fm = fm_match.group(1)
    body = text[fm_match.end():].strip()

    def _get(key: str) -> str:
        m = re.search(rf"^{key}:\s*(.+)$", fm, re.MULTILINE)
        return m.group(1).strip() if m else ""

    # Extract title from first # heading
    title_match = re.match(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1) if title_match else path.stem

    # Extract content (everything after the title)
    content = body
    if title_match:
        content = body[title_match.end():].strip()

    # Parse tags
    tags_str = _get("tags")
    tags_match = re.search(r"\[(.+?)\]", tags_str)
    tags = [t.strip().strip('"\'') for t in tags_match.group(1).split(",") if t.strip()] if tags_match else []

    session_id = _get("session_id") or None
    created_str = _get("created_at")

    try:
        created_at = datetime.fromisoformat(created_str) if created_str else datetime.now()
    except ValueError:
        created_at = datetime.now()

    return Lesson(
        id=_get("id") or path.stem,
        title=title,
        content=content,
        tags=tags,
        source=_get("source") or "user",
        session_id=session_id,
        created_at=created_at,
    )


_TAG_TO_SUBFOLDER = {
    "scrnaseq": "scrnaseq",
    "scrna": "scrnaseq",
    "single-cell": "scrnaseq",
    "scimilarity": "scrnaseq",
    "scanpy": "scrnaseq",
    "rnaseq": "bulkrnaseq",
    "deseq2": "bulkrnaseq",
    "bulk": "bulkrnaseq",
    "edger": "bulkrnaseq",
    "chipseq": "chipseq_atacseq",
    "atacseq": "chipseq_atacseq",
    "atac-seq": "chipseq_atacseq",
    "chip-seq": "chipseq_atacseq",
    "deeptools": "chipseq_atacseq",
    "macs2": "chipseq_atacseq",
    "spatial": "spatial",
    "visium": "spatial",
    "squidpy": "spatial",
}


def _infer_subfolder(tags: list[str]) -> str:
    """Determine lesson subfolder from tags. Returns '' if no match."""
    for tag in tags:
        tag_lower = tag.lower()
        # Check tag and common variations
        for key, folder in _TAG_TO_SUBFOLDER.items():
            if key == tag_lower or key == tag_lower.replace("-", "").replace("_", ""):
                return folder
        # Also check if tag contains a known key (e.g., "tumor-scrna-seq" contains "scrna")
        for key, folder in _TAG_TO_SUBFOLDER.items():
            if key in tag_lower:
                return folder
    return ""


class MemoryManager:
    """Manages the lesson store — markdown files indexed by qmd for hybrid search.

    Lessons are organized in subfolders by sequencing type:
      lessons/scrnaseq/, lessons/bulkrnaseq/, lessons/chipseq_atacseq/, lessons/spatial/
    """

    def __init__(self, lessons_dir: Path | None = None):
        self.lessons_dir = lessons_dir or settings.LESSONS_DIR
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        self._qmd_initialized = False

    def _find_lesson_path(self, lesson_id: str) -> Path | None:
        """Find a lesson file by ID (searches subfolders)."""
        for path in self.lessons_dir.rglob(f"{lesson_id}.md"):
            return path
        return None

    def _save_lesson(self, lesson: Lesson):
        """Save lesson as a markdown file in the appropriate subfolder."""
        subfolder = _infer_subfolder(lesson.tags)
        target_dir = self.lessons_dir / subfolder if subfolder else self.lessons_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        md = _lesson_to_markdown(lesson)
        (target_dir / f"{lesson.id}.md").write_text(md)
        self._qmd_initialized = False  # needs re-index

    def _qmd_index(self):
        """Index lessons with qmd (idempotent). Adds collection and updates index."""
        if self._qmd_initialized:
            return
        try:
            # Add the lessons collection (ignore error if already exists)
            subprocess.run(
                ["qmd", "collection", "add", str(self.lessons_dir), "--name", "lessons"],
                capture_output=True, timeout=30,
            )
            # Update index to pick up new/changed files
            subprocess.run(
                ["qmd", "collection", "update", "lessons"],
                capture_output=True, timeout=30,
            )
            self._qmd_initialized = True
        except FileNotFoundError:
            # qmd not installed — fall back to keyword search
            self._qmd_initialized = True  # don't retry
        except Exception:
            pass

    def list_lessons(
        self,
        tag: str | None = None,
        source: str | None = None,
    ) -> list[Lesson]:
        """List all lessons, optionally filtered."""
        lessons = []
        for path in sorted(self.lessons_dir.rglob("*.md")):
            lesson = _markdown_to_lesson(path)
            if not lesson:
                continue
            if tag and tag not in lesson.tags:
                continue
            if source and lesson.source != source:
                continue
            lessons.append(lesson)
        return lessons

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        path = self._find_lesson_path(lesson_id)
        if path:
            return _markdown_to_lesson(path)
        return None

    def create_lesson(self, data: LessonCreate) -> Lesson:
        """Create a new lesson as a markdown file."""
        lesson = Lesson(
            id=str(uuid.uuid4())[:8],
            title=data.title,
            content=data.content,
            tags=data.tags,
            source=data.source,
            session_id=data.session_id,
            created_at=datetime.now(),
        )
        self._save_lesson(lesson)
        return lesson

    def update_lesson(self, lesson_id: str, updates: dict) -> Lesson | None:
        lesson = self.get_lesson(lesson_id)
        if not lesson:
            return None
        for key, value in updates.items():
            if value is not None and hasattr(lesson, key):
                setattr(lesson, key, value)
        self._save_lesson(lesson)
        return lesson

    def delete_lesson(self, lesson_id: str) -> bool:
        path = self._find_lesson_path(lesson_id)
        if path:
            path.unlink()
            self._qmd_initialized = False
            return True
        return False

    def search_lessons(
        self,
        query: str = "",
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[Lesson]:
        """Search lessons using qmd hybrid search (BM25 + vector + reranking).

        Falls back to simple keyword search if qmd is unavailable.
        """
        if not query and not tags:
            return self.list_lessons()[:limit]

        all_lessons = self.list_lessons()
        if not all_lessons:
            return []

        # Try qmd search first
        if query:
            results = self._qmd_search(query, limit)
            if results is not None:
                # Filter by tags if needed
                if tags:
                    results = [l for l in results if any(t.lower() in [lt.lower() for lt in l.tags] for t in tags)]
                return results[:limit]

        # Fallback: keyword search
        return self._keyword_search(query, tags, all_lessons, limit)

    def _qmd_search(self, query: str, limit: int) -> list[Lesson] | None:
        """Run qmd search (BM25) and return matching lessons, or None if unavailable."""
        self._qmd_index()

        try:
            result = subprocess.run(
                ["qmd", "search", query],
                capture_output=True, text=True, timeout=15,
            )

            if result.returncode != 0:
                return None

            # Parse qmd output — lines like:
            # qmd://lessons/0f9b1090.md:4 #a0a5e1
            lessons = []
            seen = set()
            for line in result.stdout.strip().splitlines():
                # Extract lesson ID from path pattern like /0f9b1090.md
                id_match = re.search(r"/([a-f0-9]{8})\.md", line)
                if id_match:
                    lesson_id = id_match.group(1)
                    if lesson_id not in seen:
                        lesson = self.get_lesson(lesson_id)
                        if lesson:
                            lessons.append(lesson)
                            seen.add(lesson_id)

            return lessons[:limit] if lessons else None

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _keyword_search(
        self,
        query: str,
        tags: list[str] | None,
        all_lessons: list[Lesson],
        limit: int,
    ) -> list[Lesson]:
        """Fallback keyword-based search."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for lesson in all_lessons:
            score = 0

            if tags:
                for tag in tags:
                    if tag.lower() in [t.lower() for t in lesson.tags]:
                        score += 3

            lesson_text = f"{lesson.title} {lesson.content} {' '.join(lesson.tags)}".lower()
            for word in query_words:
                if len(word) > 2 and word in lesson_text:
                    score += 2

            if score > 0:
                scored.append((score, lesson))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:limit]]

    async def extract_lessons(
        self,
        plan: dict,
        code: str,
        stdout: str,
        stderr: str,
        evaluation: dict,
        session_id: str | None = None,
    ) -> list[Lesson]:
        """Use Claude to auto-extract lessons from a completed analysis."""
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = f"""Analysis plan:
{json.dumps(plan, indent=2)}

Code executed:
```
{code[:3000]}
```

Output (last 2000 chars):
```
{stdout[-2000:] if stdout else "(empty)"}
```

Stderr:
```
{stderr[-1000:] if stderr else "(empty)"}
```

Evaluation:
{json.dumps(evaluation, indent=2)}

Extract key lessons from this analysis."""

        try:
            response = await client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=2048,
                system=EXTRACT_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text
            try:
                items = json.loads(text)
            except json.JSONDecodeError:
                if "```json" in text:
                    items = json.loads(text.split("```json")[1].split("```")[0].strip())
                elif "```" in text:
                    items = json.loads(text.split("```")[1].split("```")[0].strip())
                else:
                    return []

            lessons = []
            for item in items:
                if not item.get("title") or not item.get("content"):
                    continue
                lesson = self.create_lesson(LessonCreate(
                    title=item["title"],
                    content=item["content"],
                    tags=item.get("tags", []),
                    source="agent",
                    session_id=session_id,
                ))
                lessons.append(lesson)

            return lessons

        except Exception:
            return []
