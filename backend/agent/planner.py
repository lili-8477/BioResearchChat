"""Generate an analysis plan from parsed paper information."""

import json

import anthropic

from config import settings

PLAN_SYSTEM = """You are a bioinformatics analysis planner. Given extracted paper information and a user's research question, generate a detailed analysis plan.

You have access to:
- **Established pipeline skills** — proven templates for common analyses. Reference these when applicable; they guide what tools and steps work well.
- **Lessons from past analyses** — insights and pitfalls learned from previous runs. Follow these to avoid known issues.

Your plan must include:
1. A step-by-step list of analysis steps
2. The recommended Docker base image (one of: python-spatial, r-rnaseq, python-chipseq, python-general)
3. Any extra packages needed beyond the base image
4. Required datasets
5. Expected outputs (plots, tables, files)

Base image contents:
- python-spatial: scanpy, squidpy, celltypist, anndata, matplotlib
- r-rnaseq: DESeq2, hciR, edgeR, ggplot2, EnhancedVolcano
- python-chipseq: deeptools, macs2, pybedtools, pysam
- python-general: pandas, numpy, scipy, scikit-learn, matplotlib

Return your plan as JSON:
{
  "title": "Analysis title",
  "base_image": "python-spatial|r-rnaseq|python-chipseq|python-general",
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
