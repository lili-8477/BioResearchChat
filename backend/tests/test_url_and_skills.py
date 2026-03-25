"""Test URL parsing (GitHub + paper) and progressive skill loading.

Run: python -m tests.test_url_and_skills
Output: tests/reports/url_and_skills_report.md
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.paper_parser import parse_url, is_github_url, fetch_github_content
from skills.manager import SkillManager

REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TEST_URLS = [
    {
        "url": "https://github.com/Genentech/scimilarity",
        "expected_type": "github",
        "expected_analysis": "scrna_seq",
        "description": "SCimilarity — cell similarity foundation model",
    },
]


def section(title: str) -> str:
    return f"\n## {title}\n"


async def test_url_parsing(url_info: dict) -> tuple[dict, str]:
    """Test URL parsing and return (result, report_section)."""
    url = url_info["url"]
    lines = [section(f"URL: {url}")]
    lines.append(f"- **Description**: {url_info['description']}")
    lines.append(f"- **Expected type**: {url_info['expected_type']}")
    lines.append(f"- **Expected analysis**: {url_info['expected_analysis']}")
    lines.append(f"- **is_github_url**: `{is_github_url(url)}`")

    start = time.time()
    try:
        result = await parse_url(url)
        elapsed = time.time() - start
        lines.append(f"- **Parse time**: {elapsed:.1f}s")
        lines.append(f"- **Status**: PASS")
        lines.append(f"\n### Parsed result\n")
        lines.append(f"```json\n{json.dumps(result, indent=2)}\n```")

        # Assertions
        checks = []
        if result.get("url_type") == url_info["expected_type"]:
            checks.append("url_type: PASS")
        else:
            checks.append(f"url_type: FAIL (got {result.get('url_type')})")

        if result.get("analysis_type") == url_info["expected_analysis"]:
            checks.append("analysis_type: PASS")
        else:
            checks.append(f"analysis_type: FAIL (got {result.get('analysis_type')})")

        for field in ["purpose", "input", "method", "output"]:
            val = result.get(field, "")
            if val and len(val) > 10:
                checks.append(f"{field}: PASS ({len(val)} chars)")
            else:
                checks.append(f"{field}: FAIL (empty or too short)")

        lines.append("\n### Checks\n")
        for c in checks:
            status = "PASS" if "PASS" in c else "FAIL"
            lines.append(f"- {'[x]' if status == 'PASS' else '[ ]'} {c}")

        return result, "\n".join(lines)

    except Exception as e:
        elapsed = time.time() - start
        lines.append(f"- **Parse time**: {elapsed:.1f}s")
        lines.append(f"- **Status**: FAIL")
        lines.append(f"- **Error**: `{e}`")
        return {}, "\n".join(lines)


def test_skill_loading(paper_info: dict) -> str:
    """Test progressive skill loading and return report section."""
    lines = [section("Progressive Skill Loading")]
    sm = SkillManager()

    # Phase 1: Registry
    lines.append("### Phase 1: Registry Search (planner input)\n")
    analysis_type = paper_info.get("analysis_type", "")
    packages = paper_info.get("packages", [])
    methods = paper_info.get("method", "").split(",") if paper_info.get("method") else []
    query = f"{paper_info.get('purpose', '')} {paper_info.get('method', '')}"

    registry_results = sm.search_registry(
        query=query[:200],
        analysis_type=analysis_type,
        tags=packages + [m.strip() for m in methods],
        limit=5,
    )

    lines.append(f"- **Query analysis_type**: `{analysis_type}`")
    lines.append(f"- **Query tags**: `{packages + [m.strip() for m in methods]}`")
    lines.append(f"- **Results**: {len(registry_results)} skills matched\n")

    for r in registry_results:
        has_code = "code_template" in r
        lines.append(f"- `{r['name']}` — {r['description'][:80]}...")
        lines.append(f"  - packages: {r.get('packages', [])}")
        lines.append(f"  - code_template leaked: **{'YES (BUG!)' if has_code else 'No (correct)'}**")

    # Token estimate
    registry_tokens = sum(len(json.dumps(r)) // 4 for r in registry_results)
    lines.append(f"\n- **Estimated registry tokens**: ~{registry_tokens}")

    # Phase 2: Load single skill
    lines.append("\n### Phase 2: Skill Content Load (code_writer input)\n")
    if registry_results:
        top_name = registry_results[0]["name"]
        content = sm.load_skill_content(top_name)
        if content:
            lines.append(f"- **Loaded skill**: `{top_name}`")
            lines.append(f"- **Content length**: {len(content)} chars (~{len(content) // 4} tokens)")
            lines.append(f"\n<details><summary>Skill content preview (first 500 chars)</summary>\n")
            lines.append(f"```markdown\n{content[:500]}\n```\n</details>")
        else:
            lines.append(f"- **FAIL**: Could not load content for `{top_name}`")
    else:
        lines.append("- **SKIP**: No skills matched")

    return "\n".join(lines)


async def main():
    report_lines = [
        f"# URL Parsing & Skill Loading Test Report",
        f"\n**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Test count**: {len(TEST_URLS)} URLs\n",
        "---",
    ]

    for url_info in TEST_URLS:
        print(f"Testing: {url_info['url']}...")
        result, url_report = await test_url_parsing(url_info)
        report_lines.append(url_report)

        if result:
            skill_report = test_skill_loading(result)
            report_lines.append(skill_report)

        report_lines.append("\n---")

    report = "\n".join(report_lines)
    report_path = REPORT_DIR / "url_and_skills_report.md"
    report_path.write_text(report)
    print(f"\nReport saved: {report_path}")
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
