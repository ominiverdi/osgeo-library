#!/usr/bin/env python3
"""
Multimodal PDF extraction using vision LLMs via OpenRouter.

Converts PDF pages to images and sends them to vision models
for detailed content extraction including figure descriptions.
"""

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from datetime import datetime

import fitz  # PyMuPDF
import requests


# OpenRouter API configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Vision models available on OpenRouter free tier
VISION_MODELS = {
    "nemotron-vl": "nvidia/nemotron-nano-12b-v2-vl:free",  # Vision-Language specialist
    "gemini": "google/gemini-2.0-flash-exp:free",
    "nova": "amazon/nova-2-lite-v1:free",
}

# Default model - Nemotron VL is document-specialized
DEFAULT_MODEL = "nemotron-vl"

EXTRACTION_PROMPT = """You are analyzing a page from a scientific research paper about Earth Observation, Remote Sensing, or AI/ML for geospatial applications.

Please extract and describe ALL content on this page in detail:

1. **Text Content**: Extract all readable text, preserving structure (headings, paragraphs, lists).

2. **Figures and Diagrams**: For each figure:
   - Figure number and caption
   - Detailed description of what the figure shows
   - If it's an architecture diagram: describe the components and data flow
   - If it's a results visualization: describe what is being compared and key findings
   - If it's a map or satellite image: describe the geographic content and features shown

3. **Tables**: Extract table data in a structured format, including:
   - Column headers
   - Row data
   - Any notable patterns or key values

4. **Equations**: Describe any mathematical equations and their meaning in context.

5. **Key Information**: Note any:
   - Method names or model architectures
   - Dataset names
   - Benchmark results or metrics
   - Citations to other works

Output in JSON format with these fields:
{
  "page_type": "title|content|results|references|appendix",
  "text_content": "full extracted text",
  "figures": [{"number": "1", "caption": "...", "description": "detailed description"}],
  "tables": [{"number": "1", "caption": "...", "headers": [...], "data": [...]}],
  "equations": [{"id": "1", "latex": "...", "description": "..."}],
  "key_concepts": ["concept1", "concept2"],
  "citations_mentioned": ["Author et al., 2023"]
}
"""


def load_api_key(config_path: Path | None = None) -> str:
    """Load OpenRouter API key from config file."""
    if config_path is None:
        # Try matrix-llmagent config
        config_path = Path.home() / "github" / "matrix-llmagent" / "config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Please provide API key via --api-key or config file."
        )

    with open(config_path) as f:
        config = json.load(f)

    return config["providers"]["openrouter"]["key"]


def pdf_page_to_base64(doc: fitz.Document, page_num: int, dpi: int = 150) -> str:
    """Convert a PDF page to base64-encoded PNG image."""
    page = doc[page_num]
    # Render at specified DPI
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    return base64.b64encode(img_bytes).decode("utf-8")


def call_vision_model(
    api_key: str,
    image_base64: str,
    model: str,
    prompt: str = EXTRACTION_PROMPT,
) -> dict:
    """Call OpenRouter vision model with an image."""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ominiverdi/osgeo-library",
        "X-Title": "OSGeo Library PDF Extraction",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": 4096,
    }

    response = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=120,
    )

    if response.status_code != 200:
        return {
            "error": True,
            "status_code": response.status_code,
            "message": response.text,
        }

    result = response.json()

    # Extract the response content
    if "choices" in result and len(result["choices"]) > 0:
        content = result["choices"][0]["message"]["content"]
        # Try to parse as JSON
        try:
            # Find JSON in the response (might be wrapped in markdown code blocks)
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            else:
                json_str = content
            parsed = json.loads(json_str)
            return {"success": True, "data": parsed, "raw": content}
        except json.JSONDecodeError:
            # Return raw content if not valid JSON
            return {"success": True, "data": None, "raw": content}

    return {"error": True, "message": "No response content", "raw": result}


def extract_page_multimodal(
    doc: fitz.Document,
    page_num: int,
    api_key: str,
    model: str,
    dpi: int = 150,
) -> dict:
    """Extract content from a single page using multimodal vision model."""

    # Convert page to image
    image_base64 = pdf_page_to_base64(doc, page_num, dpi)

    # Call vision model
    result = call_vision_model(api_key, image_base64, model)

    return {
        "page_number": page_num + 1,
        "extraction_result": result,
        "image_size_bytes": len(image_base64) * 3 // 4,  # Approximate decoded size
    }


def extract_pdf_multimodal(
    pdf_path: Path,
    api_key: str,
    model: str,
    pages: list[int] | None = None,
    dpi: int = 150,
    delay: float = 3.0,
) -> dict:
    """Extract content from PDF using multimodal vision model."""

    doc = fitz.open(pdf_path)

    result = {
        "source_file": str(pdf_path),
        "file_size_bytes": pdf_path.stat().st_size,
        "extraction_date": datetime.now().isoformat(),
        "extraction_tool": f"multimodal/{model}",
        "model": model,
        "dpi": dpi,
        "metadata": {
            "page_count": len(doc),
        },
        "pages": [],
        "api_calls": 0,
        "errors": [],
    }

    # Determine which pages to extract
    if pages is None:
        pages_to_extract = list(range(len(doc)))
    else:
        pages_to_extract = [
            p - 1 for p in pages if 0 < p <= len(doc)
        ]  # Convert to 0-indexed

    for i, page_num in enumerate(pages_to_extract):
        print(f"Processing page {page_num + 1}/{len(doc)}...", file=sys.stderr)

        page_result = extract_page_multimodal(doc, page_num, api_key, model, dpi)
        result["pages"].append(page_result)
        result["api_calls"] += 1

        if "error" in page_result.get("extraction_result", {}):
            result["errors"].append(
                {
                    "page": page_num + 1,
                    "error": page_result["extraction_result"],
                }
            )

        # Rate limiting - wait between requests
        if i < len(pages_to_extract) - 1:
            print(f"Waiting {delay}s before next request...", file=sys.stderr)
            time.sleep(delay)

    doc.close()
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Extract PDF content using multimodal vision LLMs"
    )
    parser.add_argument("pdf_path", type=Path, help="Path to PDF file")
    parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Pages to extract (comma-separated, e.g., '1,2,5'). Default: all pages",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=list(VISION_MODELS.keys()),
        default=DEFAULT_MODEL,
        help=f"Vision model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenRouter API key (default: read from matrix-llmagent config)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="DPI for page rendering (default: 150)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Delay between API calls in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON file (default: stdout)",
    )

    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"Error: File not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Load API key
    api_key = args.api_key or load_api_key()

    # Parse pages argument
    pages = None
    if args.pages:
        pages = [int(p.strip()) for p in args.pages.split(",")]

    # Get model ID
    model = VISION_MODELS[args.model]

    print(f"Extracting with model: {model}", file=sys.stderr)
    print(f"Pages: {pages or 'all'}", file=sys.stderr)

    result = extract_pdf_multimodal(
        args.pdf_path,
        api_key,
        model,
        pages=pages,
        dpi=args.dpi,
        delay=args.delay,
    )

    # Output JSON
    output_json = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        args.output.write_text(output_json)
        print(f"Output written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)

    # Print summary to stderr
    print(f"\nSummary:", file=sys.stderr)
    print(f"  Pages processed: {len(result['pages'])}", file=sys.stderr)
    print(f"  API calls: {result['api_calls']}", file=sys.stderr)
    print(f"  Errors: {len(result['errors'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
