"""Generate executable analysis code from an approved plan."""

import json

import anthropic

from config import settings

CODE_SYSTEM = """You are a bioinformatics code generator. Given an analysis plan, write a complete, executable script that performs the analysis.

Rules:
- Write clean, well-commented code
- Include all necessary imports at the top
- Save all outputs (plots, tables, stats) to the /workspace/output/ directory
- Use try/except for error handling on critical steps
- Print progress messages so the user can follow along
- Save plots as PNG files with descriptive names
- Save tables as CSV files
- Print a summary of results at the end
- The script must be self-contained and runnable with a single command
- Data files will be mounted at /data/ — use that path
- Working directory is /workspace/
- IMPORTANT: At the very top of the script, before any imports, include a comment block listing ALL pip/CRAN packages the script needs. Use this exact format:

For Python:
# REQUIREMENTS: numpy pandas scanpy anndata matplotlib seaborn

For R:
# REQUIREMENTS: DESeq2 ggplot2 pheatmap EnhancedVolcano

This requirements line is critical — it's parsed by the executor to install dependencies before running.

If you are given reference code templates (skills), use them as a starting point and adapt to the specific plan.
If you are given lessons from previous analyses, follow them to avoid known pitfalls.

Return ONLY the code, no markdown fencing, no explanation. Just the raw script content."""


def _strip_fencing(text: str) -> str:
    """Remove markdown code fencing if present."""
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return text


async def generate_code(
    plan: dict,
    language: str = "python",
    skills: list[dict] | None = None,
    lessons: list[dict] | None = None,
) -> str:
    """Generate analysis code from an approved plan.

    Args:
        plan: Approved analysis plan
        language: python or r
        skills: Matched skill templates (with full code_template)
        lessons: Relevant lessons from memory
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt_parts = [
        f"Analysis plan:\n{json.dumps(plan, indent=2)}",
        f"\nLanguage: {language}",
    ]

    if skills:
        for s in skills[:3]:  # Limit to top 3 to save tokens
            if s.get("code_template"):
                prompt_parts.append(
                    f"\nReference skill template — **{s['name']}** ({s['description']}):\n"
                    f"```{s.get('language', language)}\n{s['code_template']}\n```"
                )

    if lessons:
        lesson_texts = [f"- {l['title']}: {l['content']}" for l in lessons[:5]]
        prompt_parts.append(
            f"\nLessons from past analyses — follow these:\n" + "\n".join(lesson_texts)
        )

    prompt_parts.append("\nWrite the complete analysis script. Output ONLY the code.")
    prompt = "\n".join(prompt_parts)

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=8192,
        system=CODE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    return _strip_fencing(response.content[0].text)


async def fix_code(
    code: str,
    error: str,
    plan: dict,
    language: str = "python",
    lessons: list[dict] | None = None,
) -> str:
    """Fix code based on execution error output."""
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt_parts = [
        f"The following {language} script failed with an error.",
        f"\nOriginal plan:\n{json.dumps(plan, indent=2)}",
        f"\nScript:\n```{language}\n{code}\n```",
        f"\nError output:\n```\n{error}\n```",
    ]

    if lessons:
        lesson_texts = [f"- {l['title']}: {l['content']}" for l in lessons[:5]]
        prompt_parts.append(
            f"\nLessons from past analyses — avoid repeating these mistakes:\n"
            + "\n".join(lesson_texts)
        )

    prompt_parts.append("\nFix the script. Return ONLY the corrected code, no explanation.")
    prompt = "\n".join(prompt_parts)

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=8192,
        system=CODE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    return _strip_fencing(response.content[0].text)
