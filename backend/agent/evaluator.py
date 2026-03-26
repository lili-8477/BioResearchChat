"""Evaluate execution output and decide if the analysis succeeded."""

import json

import anthropic

from config import settings
from agent.api_retry import api_call_with_retry

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

    try:
        response = await api_call_with_retry(
            client,
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
            return _heuristic_eval(exit_code, stdout, stderr, output_files)
    except Exception:
        # API completely unavailable — fall back to heuristic evaluation
        return _heuristic_eval(exit_code, stdout, stderr, output_files)


def _heuristic_eval(exit_code: int, stdout: str, stderr: str, output_files: list[str]) -> dict:
    """Evaluate results without calling the API — based on exit code and outputs."""
    has_outputs = len(output_files) > 0
    # Only count real Python/R tracebacks as errors, not warnings containing "Error"
    has_fatal = bool(stderr and ("Traceback (most recent call last)" in stderr
                                or "Error in " in stderr  # R-style errors
                                or "ModuleNotFoundError" in stderr))
    success = exit_code == 0 and has_outputs and not has_fatal

    if success:
        summary = f"Analysis completed. Produced {len(output_files)} output file(s)."
    elif exit_code == 0 and not has_outputs:
        summary = "Script ran without errors but produced no output files."
    else:
        # Extract the last error line for the summary
        error_lines = [l for l in (stderr or stdout).splitlines() if l.strip()]
        last_error = error_lines[-1] if error_lines else "Unknown error"
        summary = f"Script failed: {last_error}"

    return {
        "success": success,
        "summary": summary,
        "outputs": output_files,
        "errors": [stderr[-1000:]] if stderr else [],
        "suggestion": None if success else "Check the error output above.",
    }
