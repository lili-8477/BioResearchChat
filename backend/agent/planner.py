"""Generate an analysis plan from parsed paper information."""

import json

import anthropic

from config import settings

PLAN_SYSTEM = """You are a bioinformatics analysis planner. Given extracted paper information and a user's research question, generate a detailed analysis plan.

You have access to:
- **Established pipeline skills** — proven templates for common analyses. When a skill matches, use its `base_image` — do NOT substitute a different image.
- **Lessons from past analyses** — insights and pitfalls learned from previous runs. Follow these to avoid known issues.

Your plan must include:
1. A step-by-step list of analysis steps
2. The recommended Docker base image
3. Any extra packages needed beyond the base image
4. Required datasets
5. Expected outputs (plots, tables, files)

Available base images:
- python-spatial: scanpy, squidpy, celltypist, anndata, matplotlib
- python-scimilarity: scanpy, anndata, scimilarity, matplotlib, leidenalg (use for SCimilarity cell annotation/query)
- r-rnaseq: DESeq2, hciR, edgeR, ggplot2, EnhancedVolcano
- python-chipseq: deeptools, macs2, pybedtools, pysam
- python-general: pandas, numpy, scipy, scikit-learn, matplotlib

IMPORTANT:
- When you reference a skill, you MUST use that skill's base_image. For example, if a skill specifies base_image "python-scimilarity", use "python-scimilarity" — not "python-spatial".
- The "datasets" field is ONLY for datasets that need to be downloaded (GEO GSE IDs or TCGA project IDs). Do NOT put zenodo IDs, URLs, or local paths here.
- Data that is already available locally (listed under "Already available on this server") does NOT need to be in the datasets field — it is auto-mounted into containers at the paths shown.

Return your plan as JSON:
{
  "title": "Analysis title",
  "base_image": "python-spatial|python-scimilarity|r-rnaseq|python-chipseq|python-general",
  "extra_packages": ["packages not in base image"],
  "datasets": [{"id": "GSE...", "description": "what it contains"}],
  "steps": [
    {"step": 1, "title": "Step title", "description": "What to do", "expected_output": "What this produces"}
  ],
  "expected_results": ["list of expected output files/plots"],
  "language": "python|r",
  "estimated_runtime_minutes": 5,
  "skill_reference": "name of matching skill template if applicable, or null"
}"""


def _get_local_data_context() -> str:
    """Scan the data/ directory and return a description of what's available locally.

    This tells the planner what data is already cached so it doesn't request downloads.
    """
    from pathlib import Path
    data_root = settings.DATA_CACHE_DIR.parent
    lines = []

    for subdir in ["models", "references", "atlases", "user"]:
        host_dir = data_root / subdir
        if not host_dir.exists():
            continue
        items = []
        for p in sorted(host_dir.iterdir()):
            if p.name.startswith("."):
                continue
            if p.is_dir():
                items.append(f"`/data/{subdir}/{p.name}/` (directory)")
            elif p.is_file() and not p.name.endswith(".tar.gz"):
                size_mb = p.stat().st_size / (1024 * 1024)
                items.append(f"`/data/{subdir}/{p.name}` ({size_mb:.0f} MB)")
        if items:
            lines.append(f"**{subdir}/**:")
            for item in items:
                lines.append(f"  - {item}")

    if not lines:
        return ""
    return "Already available on this server (no download needed):\n" + "\n".join(lines)


async def generate_plan(
    paper_info: dict,
    question: str,
    skills: list[dict] | None = None,
    lessons: list[dict] | None = None,
) -> dict:
    """Generate an analysis plan from parsed paper info and user question.

    Args:
        paper_info: Parsed paper metadata
        question: User's research question
        skills: Matched skill templates (metadata only, no code)
        lessons: Relevant lessons from memory
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt_parts = [
        f"Paper analysis:\n{json.dumps(paper_info, indent=2)}",
        f"\nUser's research question:\n{question}",
    ]

    # Tell the planner what data is already available locally
    local_data = _get_local_data_context()
    if local_data:
        prompt_parts.append(f"\n{local_data}")

    if skills:
        skill_summaries = []
        for s in skills:
            skill_summaries.append(
                f"- **{s['name']}**: {s['description']} "
                f"(image: {s['base_image']}, lang: {s['language']}, "
                f"packages: {', '.join(s.get('packages', []))})"
            )
        prompt_parts.append(
            f"\nAvailable pipeline skills (use as reference for your plan):\n"
            + "\n".join(skill_summaries)
        )

    if lessons:
        lesson_texts = []
        for l in lessons:
            lesson_texts.append(f"- **{l['title']}**: {l['content']}")
        prompt_parts.append(
            f"\nLessons from past analyses (follow these):\n"
            + "\n".join(lesson_texts)
        )

    prompt_parts.append("\nGenerate a detailed analysis plan.")
    prompt = "\n".join(prompt_parts)

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=4096,
        system=PLAN_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0].strip()
            return json.loads(json_str)
        return {"error": "Failed to parse plan", "raw": text}
