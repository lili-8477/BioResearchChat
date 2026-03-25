"""Parse URLs (GitHub repos or science papers) and extract structured research context.

Two URL types:
- GitHub repos → GitHub API to fetch README, key files, repo metadata
- Everything else (papers, docs) → crawl4ai for clean markdown extraction

Both are sent to Claude to extract: purpose, input, method, output.
Results are cached to avoid repeat API calls during development.
"""

import base64
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import anthropic
import fitz  # PyMuPDF
import httpx

from config import settings

# --- URL Parse Cache ---
# Caches Claude API results so repeat URLs skip the LLM call.
# Cache dir: backend/.url_cache/
_CACHE_DIR = Path(__file__).parent.parent / ".url_cache"
_CACHE_DIR.mkdir(exist_ok=True)


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _get_cached(url: str) -> dict | None:
    path = _CACHE_DIR / f"{_cache_key(url)}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None


def _set_cached(url: str, result: dict):
    path = _CACHE_DIR / f"{_cache_key(url)}.json"
    path.write_text(json.dumps(result, indent=2))

PARSE_SYSTEM = """You are a bioinformatics research context parser. Given content from a URL (either a GitHub repository or a science paper), extract a structured summary.

Return your response as JSON:
{
  "url_type": "github" | "paper",
  "purpose": "What this project/paper aims to achieve — the biological question or tool goal",
  "input": "What data or inputs are required (e.g., scRNA-seq counts, BAM files, GEO accession IDs)",
  "method": "Analytical methods, algorithms, and tools/packages used (e.g., Scanpy clustering, DESeq2 DE, MACS2 peak calling)",
  "output": "What results are produced (e.g., UMAP plots, DE gene tables, peak files, trained models)",
  "analysis_type": "e.g., scrna_seq, bulk_rnaseq, chipseq, spatial, general",
  "packages": ["list of software packages referenced"],
  "language": "python or r (primary language)",
  "datasets": ["list of dataset IDs like GSE..., TCGA-..., if mentioned"],
  "summary": "One-paragraph summary of the content"
}"""


# --- URL Classification ---


def is_github_url(url: str) -> bool:
    """Check if URL is a GitHub repository."""
    parsed = urlparse(url)
    return parsed.netloc in ("github.com", "www.github.com")


def _parse_github_path(url: str) -> tuple[str, str, str | None]:
    """Parse GitHub URL into (owner, repo, subpath).

    Handles:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/tree/main/some/path
    - https://github.com/owner/repo/blob/main/file.py
    """
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL: {url}")
    owner, repo = parts[0], parts[1]
    subpath = None
    if len(parts) > 3 and parts[2] in ("tree", "blob"):
        # Skip "tree/main/" or "blob/main/" prefix
        subpath = "/".join(parts[4:]) if len(parts) > 4 else None
    return owner, repo, subpath


# --- GitHub Fetcher ---


async def fetch_github_content(url: str) -> str:
    """Fetch GitHub repo content using the GitHub API.

    Retrieves: repo description, README, key file listing, and
    optionally specific files if the URL points to a subpath.
    """
    owner, repo, subpath = _parse_github_path(url)

    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"token {token}"

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        parts = []

        # Repo metadata
        resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
        resp.raise_for_status()
        repo_data = resp.json()
        parts.append(f"# {repo_data['full_name']}")
        if repo_data.get("description"):
            parts.append(f"\n{repo_data['description']}")
        parts.append(f"\nLanguage: {repo_data.get('language', 'Unknown')}")
        parts.append(f"Stars: {repo_data.get('stargazers_count', 0)}")
        if repo_data.get("topics"):
            parts.append(f"Topics: {', '.join(repo_data['topics'])}")

        # README
        try:
            readme_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/readme",
                headers={**headers, "Accept": "application/vnd.github.v3.raw"},
            )
            if readme_resp.status_code == 200:
                readme_text = readme_resp.text[:8000]  # Cap at 8k chars
                parts.append(f"\n## README\n\n{readme_text}")
        except Exception:
            pass

        # File tree (top-level + subpath if given)
        tree_path = f"contents/{subpath}" if subpath else "contents"
        try:
            tree_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/{tree_path}"
            )
            if tree_resp.status_code == 200:
                items = tree_resp.json()
                if isinstance(items, list):
                    file_list = [f"- {item['name']} ({item['type']})" for item in items[:50]]
                    parts.append(f"\n## File listing\n\n" + "\n".join(file_list))
        except Exception:
            pass

        # Fetch key config files for more context
        for fname in ["setup.py", "pyproject.toml", "environment.yml", "DESCRIPTION", "requirements.txt"]:
            path = f"{subpath}/{fname}" if subpath else fname
            try:
                f_resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                    headers={**headers, "Accept": "application/vnd.github.v3.raw"},
                )
                if f_resp.status_code == 200:
                    content = f_resp.text[:2000]
                    parts.append(f"\n## {fname}\n\n```\n{content}\n```")
            except Exception:
                continue

        return "\n".join(parts)


# --- Crawl4ai Fetcher ---


async def fetch_with_crawl4ai(url: str) -> tuple[str | None, str | None]:
    """Fetch URL content using crawl4ai. Returns (pdf_path, markdown_text).

    If the URL is a direct PDF, downloads it for vision processing.
    Otherwise returns cleaned markdown text.
    """
    # Check if direct PDF first (skip crawl4ai for binary files)
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        head = await client.head(url)
        content_type = head.headers.get("content-type", "")
        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            resp = await client.get(url)
            resp.raise_for_status()
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(resp.content)
            tmp.close()
            return tmp.name, None

    # Use crawl4ai for HTML content
    from crawl4ai import AsyncWebCrawler

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        if result.success and result.markdown_v2:
            # Use fit_markdown (cleaned, main content) if available
            text = result.markdown_v2.fit_markdown or result.markdown_v2.raw_markdown
            return None, text[:15000]  # Cap to avoid huge pages
        elif result.success and result.markdown:
            return None, result.markdown[:15000]
        else:
            raise ValueError(f"crawl4ai failed to extract content from {url}")


# --- PDF Vision ---


def _pdf_pages_as_images(pdf_path: str, max_pages: int = 30) -> list[str]:
    """Extract PDF pages as base64-encoded images for Claude vision."""
    doc = fitz.open(pdf_path)
    images = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        images.append(base64.standard_b64encode(img_bytes).decode())
    doc.close()
    return images


# --- Main Parser ---


async def parse_url(url: str, use_cache: bool = True) -> dict:
    """Parse a URL (GitHub repo or paper) and extract structured research context.

    Routes to GitHub API or crawl4ai based on URL type, then sends
    extracted content to Claude for structured parsing into:
    purpose, input, method, output.

    Results are cached so repeat URLs skip the Claude API call.
    """
    # Check cache first
    if use_cache:
        cached = _get_cached(url)
        if cached:
            return cached

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    if is_github_url(url):
        text = await fetch_github_content(url)
        content = [{"type": "text", "text": f"Parse this GitHub repository:\n\n{text}"}]
    else:
        pdf_path, text = await fetch_with_crawl4ai(url)
        if pdf_path and Path(pdf_path).exists():
            images = _pdf_pages_as_images(pdf_path)
            content = []
            for img_b64 in images:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                })
            content.append({"type": "text", "text": "Parse this research paper and extract the analysis details."})
        elif text:
            content = [{"type": "text", "text": f"Parse this research paper/documentation:\n\n{text}"}]
        else:
            raise ValueError(f"Could not fetch content from {url}")

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=4096,
        system=PARSE_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )

    text = response.content[0].text
    result = None
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
            result = json.loads(json_str)
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0].strip()
            result = json.loads(json_str)

    if result is None:
        result = {
            "url_type": "unknown",
            "purpose": text[:500],
            "input": "",
            "method": "",
            "output": "",
            "analysis_type": "unknown",
            "packages": [],
            "language": "python",
            "datasets": [],
            "summary": text[:500],
        }

    # Cache the result for future calls
    _set_cached(url, result)
    return result
