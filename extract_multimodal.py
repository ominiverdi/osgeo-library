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

# Vision models available on OpenRouter free tier (text+image->text)
# Tested and confirmed working as of 2025-12-16
VISION_MODELS = {
    # Google models
    "gemini": "google/gemini-2.0-flash-exp:free",  # 1M context, best quality but aggressive rate limits
    "gemma-27b": "google/gemma-3-27b-it:free",  # 131K context, often rate limited
    "gemma-12b": "google/gemma-3-12b-it:free",  # 32K context, good balance
    "gemma-4b": "google/gemma-3-4b-it:free",  # 32K context, fastest
    # Other providers
    "nemotron": "nvidia/nemotron-nano-12b-v2-vl:free",  # 128K context, document specialist
    "nova": "amazon/nova-2-lite-v1:free",  # 1M context, reliable
}
# Note: mistral-small-3.1 claims multimodal but returns 404 for image input

# Short names for display
MODEL_DISPLAY_NAMES = {
    "google/gemini-2.0-flash-exp:free": "Gemini 2.0 Flash",
    "google/gemma-3-27b-it:free": "Gemma 3 27B",
    "google/gemma-3-12b-it:free": "Gemma 3 12B",
    "google/gemma-3-4b-it:free": "Gemma 3 4B",
    "nvidia/nemotron-nano-12b-v2-vl:free": "Nemotron VL",
    "amazon/nova-2-lite-v1:free": "Amazon Nova 2",
}

# Default model - Nova is reliable with good quality
DEFAULT_MODEL = "nova"

EXTRACTION_PROMPT = """You are analyzing a page from a scientific research paper about Earth Observation, Remote Sensing, or AI/ML for geospatial applications.

Please extract and describe ALL content on this page in detail:

1. **Text Content**: Extract all readable text, preserving structure (headings, paragraphs, lists).

2. **Visual Elements**: Identify and categorize ALL visual elements. For EACH visual element, specify:
   - **type**: One of: "architecture_diagram", "flowchart", "graph_chart", "results_figure", "map", "satellite_image", "photo", "table", "equation", "other"
   - **number**: Figure/Table number if labeled (e.g., "Figure 1", "Table 2")
   - **caption**: The caption text if present
   - **description**: Detailed description of what it shows
   
   For specific types, include additional details:
   - **architecture_diagram**: List components, connections, data flow direction
   - **graph_chart**: Chart type (bar, line, scatter, etc.), axes labels, data series, key trends
   - **results_figure**: What is being compared, metrics shown, best/worst performers
   - **table**: Headers, row labels, key values, what the data represents
   - **map/satellite_image**: Geographic region, features visible, scale if shown

3. **Tables**: For each table, extract structured data:
   - headers (column names)
   - rows (as arrays)
   - summary of what the table shows

4. **Equations**: For mathematical content:
   - LaTeX representation if possible
   - Plain text description of what it computes
   - Variable definitions

5. **Key Information**:
   - Method/model names and architectures
   - Dataset names and sizes
   - Benchmark results (metrics, scores)
   - Notable citations

Output in JSON format:
{
  "page_type": "title|abstract|methodology|results|discussion|references|appendix",
  "text_content": "full extracted text preserving structure",
  "visual_elements": [
    {
      "type": "architecture_diagram|flowchart|graph_chart|results_figure|map|satellite_image|photo|table|equation|other",
      "number": "Figure 1",
      "caption": "caption text",
      "description": "detailed description",
      "components": ["for diagrams: list of components"],
      "data_summary": "for charts/tables: summary of data shown"
    }
  ],
  "tables_structured": [
    {
      "number": "Table 1",
      "caption": "caption",
      "headers": ["col1", "col2"],
      "rows": [["val1", "val2"]],
      "key_findings": "summary of important values"
    }
  ],
  "equations": [
    {
      "number": "1",
      "latex": "LaTeX if possible",
      "description": "what it computes"
    }
  ],
  "key_concepts": ["concept1", "concept2"],
  "methods_mentioned": ["method names"],
  "datasets_mentioned": ["dataset names"],
  "metrics_reported": [{"metric": "mAP", "value": "0.85", "context": "on COCO"}],
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


def extract_images_from_page(
    doc: fitz.Document,
    page_num: int,
    output_dir: Path,
    pdf_name: str,
    min_area: int = 20000,
    min_dimension: int = 80,
) -> list[dict]:
    """
    Extract embedded images from a PDF page and save them.

    Args:
        doc: PyMuPDF document
        page_num: 0-indexed page number
        output_dir: Directory to save images
        pdf_name: Base name of PDF for naming images
        min_area: Minimum area (width * height) to include image.
                  Default 20000 = ~141x141 or 200x100, etc.
        min_dimension: Minimum for smallest dimension. Default 80px.

    Returns:
        List of dicts with image metadata
    """
    page = doc[page_num]
    images_info = []
    seen_sizes = set()  # Track (width, height, size) to deduplicate

    # Get all images on the page
    image_list = page.get_images(full=True)

    for img_idx, img_info in enumerate(image_list):
        xref = img_info[0]  # Image xref

        try:
            # Extract image
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            width = base_image["width"]
            height = base_image["height"]
            colorspace = base_image.get("colorspace", "unknown")

            # Skip small images based on area and minimum dimension
            area = width * height
            if area < min_area or min(width, height) < min_dimension:
                continue

            # Deduplicate images with same dimensions and size
            size_key = (width, height, len(image_bytes))
            if size_key in seen_sizes:
                continue
            seen_sizes.add(size_key)

            # Generate filename
            img_filename = (
                f"{pdf_name}_p{page_num + 1:03d}_img{img_idx + 1:02d}.{image_ext}"
            )
            img_path = output_dir / img_filename

            # Save image
            with open(img_path, "wb") as f:
                f.write(image_bytes)

            # Get image position on page (bounding box)
            bbox = None
            for img_rect in page.get_image_rects(xref):
                bbox = {
                    "x0": round(img_rect.x0, 2),
                    "y0": round(img_rect.y0, 2),
                    "x1": round(img_rect.x1, 2),
                    "y1": round(img_rect.y1, 2),
                }
                break  # Take first rect

            images_info.append(
                {
                    "filename": img_filename,
                    "path": str(img_path),
                    "width": width,
                    "height": height,
                    "format": image_ext,
                    "colorspace": colorspace,
                    "size_bytes": len(image_bytes),
                    "bbox": bbox,
                    "xref": xref,
                }
            )

        except Exception as e:
            # Some images may fail to extract (e.g., inline images, special formats)
            print(
                f"  Warning: Could not extract image {img_idx} from page {page_num + 1}: {e}",
                file=sys.stderr,
            )
            continue

    return images_info


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
    output_dir: Path | None = None,
    pdf_name: str = "pdf",
    extract_images: bool = True,
) -> dict:
    """Extract content from a single page using multimodal vision model."""

    # Convert page to image
    image_base64 = pdf_page_to_base64(doc, page_num, dpi)

    # Call vision model
    result = call_vision_model(api_key, image_base64, model)

    # Get display name for model
    model_display = MODEL_DISPLAY_NAMES.get(model, model)

    page_result = {
        "page_number": page_num + 1,
        "model": model,
        "model_display": model_display,
        "extraction_result": result,
        "image_size_bytes": len(image_base64) * 3 // 4,  # Approximate decoded size
    }

    # Extract embedded images if requested and output_dir provided
    if extract_images and output_dir is not None:
        images_info = extract_images_from_page(doc, page_num, output_dir, pdf_name)
        page_result["extracted_images"] = images_info
        if images_info:
            print(
                f"  Extracted {len(images_info)} images from page {page_num + 1}",
                file=sys.stderr,
            )

    return page_result


def extract_pdf_multimodal(
    pdf_path: Path,
    api_key: str,
    model: str,
    pages: list[int] | None = None,
    dpi: int = 150,
    delay: float = 3.0,
    output_dir: Path | None = None,
    extract_images: bool = True,
) -> dict:
    """Extract content from PDF using multimodal vision model."""

    doc = fitz.open(pdf_path)

    # Create output directory for images if needed
    pdf_name = pdf_path.stem  # Filename without extension
    if extract_images and output_dir is not None:
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
    else:
        images_dir = None

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
        "images_extracted": 0,
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

        page_result = extract_page_multimodal(
            doc,
            page_num,
            api_key,
            model,
            dpi,
            output_dir=images_dir,
            pdf_name=pdf_name,
            extract_images=extract_images,
        )
        result["pages"].append(page_result)
        result["api_calls"] += 1

        # Count extracted images
        if "extracted_images" in page_result:
            result["images_extracted"] += len(page_result["extracted_images"])

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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to save extracted images (default: same as --output or current dir)",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip extracting embedded images from pages",
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

    # Determine output directory for images
    output_dir = args.output_dir
    if output_dir is None and args.output:
        output_dir = args.output.parent
    if output_dir is None:
        output_dir = Path.cwd()

    extract_images = not args.no_images

    print(f"Extracting with model: {model}", file=sys.stderr)
    print(f"Pages: {pages or 'all'}", file=sys.stderr)
    print(f"Extract images: {extract_images}", file=sys.stderr)
    if extract_images:
        print(f"Images output dir: {output_dir / 'images'}", file=sys.stderr)

    result = extract_pdf_multimodal(
        args.pdf_path,
        api_key,
        model,
        pages=pages,
        dpi=args.dpi,
        delay=args.delay,
        output_dir=output_dir,
        extract_images=extract_images,
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
    print(f"  Images extracted: {result['images_extracted']}", file=sys.stderr)
    print(f"  Errors: {len(result['errors'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
