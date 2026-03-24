"""Analysis log — writes a structured markdown report for each completed session."""

import json
from datetime import datetime
from pathlib import Path

from config import settings


def write_analysis_log(
    session_id: str,
    question: str,
    paper_info: dict,
    plan: dict,
    code: str,
    language: str,
    result: dict,
    evaluation: dict,
    lessons: list[dict] | None = None,
    skills_used: list[str] | None = None,
    retries: int = 0,
):
    """Write a complete analysis log as a markdown file.

    Saved to workspaces/{session_id}/analysis_log.md
    """
    workspace = settings.WORKSPACE_DIR / session_id
    workspace.mkdir(parents=True, exist_ok=True)
    log_path = workspace / "analysis_log.md"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if evaluation.get("success") else "FAILED"
    output_files = result.get("output_files", [])

    sections = []

    # --- Header ---
    sections.append(f"""# Analysis Log

| | |
|---|---|
| **Session** | `{session_id}` |
| **Date** | {now} |
| **Status** | {status} |
| **Question** | {question} |
| **Retries** | {retries} |
""")

    # --- Paper Info ---
    if paper_info and paper_info.get("analysis_type") != "general":
        sections.append(f"""## Paper Analysis

| | |
|---|---|
| **Analysis type** | {paper_info.get('analysis_type', 'N/A')} |
| **Language** | {paper_info.get('language', 'N/A')} |
| **Packages** | {', '.join(paper_info.get('packages', []))} |
| **Datasets** | {', '.join(str(d) for d in paper_info.get('datasets', []))} |

{paper_info.get('summary', '')}
""")

    # --- Plan ---
    plan_title = plan.get("title", "Analysis Plan")
    base_image = plan.get("base_image", "N/A")
    extra_pkgs = ", ".join(plan.get("extra_packages", []))
    steps_md = ""
    for step in plan.get("steps", []):
        steps_md += f"{step.get('step', '?')}. **{step.get('title', '')}** — {step.get('description', '')}\n"

    sections.append(f"""## Plan: {plan_title}

| | |
|---|---|
| **Image** | `{base_image}` |
| **Language** | {plan.get('language', 'N/A')} |
| **Extra packages** | {extra_pkgs or 'none'} |
| **Est. runtime** | ~{plan.get('estimated_runtime_minutes', '?')} min |
| **Skills referenced** | {', '.join(skills_used or ['none'])} |

### Steps

{steps_md}
### Expected outputs

{chr(10).join('- ' + e for e in plan.get('expected_results', []))}
""")

    # --- Code ---
    ext = "python" if language == "python" else "r"
    sections.append(f"""## Generated Code

```{ext}
{code}
```
""")

    # --- Execution Result ---
    exit_code = result.get("exit_code", "N/A")
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")

    # Truncate long output
    stdout_display = stdout[-3000:] if len(stdout) > 3000 else stdout
    stderr_display = stderr[-2000:] if len(stderr) > 2000 else stderr

    sections.append(f"""## Execution

| | |
|---|---|
| **Exit code** | {exit_code} |
| **Output files** | {len(output_files)} |

### stdout

```
{stdout_display}
```
""")

    if stderr_display.strip():
        sections.append(f"""### stderr

```
{stderr_display}
```
""")

    # --- Output Files ---
    if output_files:
        files_md = ""
        for f in output_files:
            files_md += f"- `{f}`\n"
        sections.append(f"""## Output Files

{files_md}
""")

    # --- Evaluation ---
    sections.append(f"""## Evaluation

| | |
|---|---|
| **Success** | {evaluation.get('success', 'N/A')} |
| **Summary** | {evaluation.get('summary', 'N/A')} |

""")
    if evaluation.get("errors"):
        sections.append("### Errors\n")
        for err in evaluation["errors"]:
            sections.append(f"- {err}\n")

    if evaluation.get("suggestion"):
        sections.append(f"\n### Suggestion\n\n{evaluation['suggestion']}\n")

    # --- Lessons ---
    if lessons:
        lessons_md = ""
        for lesson in lessons:
            title = lesson.get("title", "") if isinstance(lesson, dict) else getattr(lesson, "title", "")
            content = lesson.get("content", "") if isinstance(lesson, dict) else getattr(lesson, "content", "")
            tags = lesson.get("tags", []) if isinstance(lesson, dict) else getattr(lesson, "tags", [])
            lessons_md += f"### {title}\n\n{content}\n\nTags: {', '.join(tags)}\n\n"

        sections.append(f"""## Lessons Learned

{lessons_md}
""")

    # --- Write ---
    log_content = "\n".join(sections)
    log_path.write_text(log_content)

    return str(log_path)
