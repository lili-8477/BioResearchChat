"""Evaluate execution output and decide if the analysis succeeded."""

import json

import anthropic

from config import settings

EVAL_SYSTEM = """You are a bioinformatics analysis evaluator. Given the execution output (stdout + stderr) and the list of expected output files, determine if the analysis succeeded.

Return JSON:
{
  "success": true/false,
  "summary": "Brief summary of what happened",
  "outputs": ["list of output files produced"],
  "errors": ["list of errors if any"],
  "suggestion": "If failed, what to fix. If succeeded, null."
}"""


async def evaluate_output(
    stdout: str,
    stderr: str,
    exit_code: int,
    output_files: list[str],
    plan: dict,
) -> dict:
    """Evaluate whether the analysis execution succeeded."""
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt = f"""Analysis plan:
{json.dumps(plan, indent=2)}

Exit code: {exit_code}

stdout:
```
{stdout[-5000:] if len(stdout) > 5000 else stdout}
```

stderr:
```
{stderr[-3000:] if len(stderr) > 3000 else stderr}
```

Output files found:
{json.dumps(output_files)}

Did this analysis succeed?"""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=2048,
        system=EVAL_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        # Fallback: simple heuristic
        success = exit_code == 0 and len(output_files) > 0
        return {
            "success": success,
            "summary": text[:500],
            "outputs": output_files,
            "errors": [stderr[-1000:]] if stderr else [],
            "suggestion": None if success else "Check error output and retry.",
        }
