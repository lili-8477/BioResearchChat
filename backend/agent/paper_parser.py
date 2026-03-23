"""Parse a paper (PDF or URL) and extract methods, tools, and data requirements."""

import base64
import tempfile
from pathlib import Path

import anthropic
import httpx
import fitz  # PyMuPDF

from config import settings

PARSE_SYSTEM = """You are a bioinformatics research paper parser. Given a paper's text, extract:

1. **Analysis type**: e.g., scRNA-seq, bulk RNA-seq, spatial transcriptomics, ChIP-seq, ATAC-seq, etc.
2. **Methods**: Specific analytical methods used (e.g., differential expression, clustering, trajectory analysis)
3. **Tools/packages**: Software and packages mentioned (e.g., DESeq2, Scanpy, MACS2)
4. **Data sources**: Datasets referenced (GEO accessions like GSE..., TCGA projects, etc.)
5. **Key parameters**: Important parameters or thresholds mentioned

Return your response as structured JSON:
{
  "analysis_type": "string",
  "methods": ["list of methods"],
  "packages": ["list of packages"],
  "language": "python or r",
  "datasets": ["list of dataset IDs"],
  "key_parameters": {"param": "value"},
  "summary": "Brief summary of what the paper does analytically"
}"""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file using PyMuPDF."""
    doc = fitz.open(pdf_path)
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts)


def extract_pdf_pages_as_images(pdf_path: str, max_pages: int = 30) -> list[str]:
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


async def fetch_paper_from_url(url: str) -> tuple[str | None, str | None]:
    """Fetch a paper from a URL. Returns (pdf_path, text).

    If the URL points to a PDF, downloads it and returns the path.
    Otherwise, fetches the HTML and returns extracted text.
    """
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        response = await client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")

        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            # Save PDF to temp file
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(response.content)
            tmp.close()
            return tmp.name, None

        # HTML page — extract text
        html = response.text

        # Try to find a PDF link on the page (common for journal sites)
        import re
        pdf_links = re.findall(r'href="([^"]*\.pdf[^"]*)"', html, re.IGNORECASE)
        if pdf_links:
            # Try to download the first PDF link found
            pdf_url = pdf_links[0]
            if pdf_url.startswith("/"):
                # Relative URL — construct absolute
                from urllib.parse import urlparse
                parsed = urlparse(url)
                pdf_url = f"{parsed.scheme}://{parsed.netloc}{pdf_url}"
            elif not pdf_url.startswith("http"):
                pdf_url = url.rstrip("/") + "/" + pdf_url

            try:
                pdf_response = await client.get(pdf_url)
                pdf_response.raise_for_status()
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.write(pdf_response.content)
                tmp.close()
                return tmp.name, None
            except Exception:
                pass  # Fall through to HTML text extraction

        # Strip HTML tags for plain text
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) < 200:
            raise ValueError(f"Could not extract meaningful content from {url}")

        return None, text


async def parse_paper(
    pdf_path: str | None = None,
    paper_text: str | None = None,
    paper_url: str | None = None,
) -> dict:
    """Parse a paper and extract structured information.

    Accepts a PDF file path, raw text, or a URL to a paper.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # If URL provided, fetch the paper first
    if paper_url and not pdf_path and not paper_text:
        fetched_pdf, fetched_text = await fetch_paper_from_url(paper_url)
        if fetched_pdf:
            pdf_path = fetched_pdf
        elif fetched_text:
            paper_text = fetched_text

    if pdf_path and Path(pdf_path).exists():
        # Use vision for PDFs — better at reading figures and tables
        images = extract_pdf_pages_as_images(pdf_path)
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
    elif paper_text:
        content = [{"type": "text", "text": f"Parse this research paper:\n\n{paper_text}"}]
    else:
        raise ValueError("Must provide either pdf_path or paper_text")

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=4096,
        system=PARSE_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )

    # Extract JSON from response
    import json
    text = response.content[0].text
    # Try to find JSON in the response
    try:
        # Direct parse
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON block
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0].strip()
            return json.loads(json_str)
        # Return raw text wrapped in a dict
        return {"raw_response": text, "analysis_type": "unknown", "methods": [], "packages": [], "language": "python", "datasets": [], "key_parameters": {}, "summary": text[:500]}
