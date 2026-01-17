#!/usr/bin/env python3
"""
Document extraction pipeline using vision LLM for visual grounding.

Extracts pages from PDF, detects figures/tables/diagrams/equations with bounding boxes,
crops detected elements, and generates structured JSON for downstream use.

Usage:
    from doclibrary.extraction import extract_document, extract_page

    # Extract specific pages
    result = extract_document(
        pdf_path="document.pdf",
        output_dir="output/doc_name",
        pages=[1, 2, 3],
    )

    # Extract single page
    page_data = extract_page(pdf_path, page_num=1, output_dir="output")
"""

import base64
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import fitz  # PyMuPDF
from openai import OpenAI
from PIL import Image

from doclibrary.config import config
from doclibrary.core.image import create_annotated_image, crop_element, render_latex_to_image
from doclibrary.core.text import clean_line_numbers, extract_latex_from_description

# Default DPI for page rendering
DEFAULT_DPI = 150

# Maximum dimension for any side of rendered page (prevents huge posters/high-DPI issues)
MAX_PAGE_DIMENSION = 2048

# Vision model extraction prompt
EXTRACTION_PROMPT = """Analyze this document page and locate all visual elements (figures, tables, diagrams, charts, equations).

For each element found, provide:
- type: figure, table, diagram, chart, or equation
- bbox: bounding box as [x1, y1, x2, y2] in 0-1000 scale (top-left to bottom-right)
- label: identifier if visible (e.g., "Figure 1", "Table 2", "Equation 3")
- description: brief description of content (for equations, include the LaTeX representation if possible)

IMPORTANT: Make sure each bounding box FULLY contains the element with a small margin around it (about 2-3% padding on each side). Nothing should be cut off.

Return JSON format:
{
  "figure": [{"bbox": [x1,y1,x2,y2], "label": "Figure 1", "description": "..."}],
  "table": [{"bbox": [x1,y1,x2,y2], "label": "Table 1", "description": "..."}],
  "diagram": [],
  "chart": [],
  "equation": [{"bbox": [x1,y1,x2,y2], "label": "Equation 1", "description": "LaTeX: ..."}]
}

Use empty arrays [] for categories with no elements."""


def _get_vision_client() -> OpenAI:
    """Get OpenAI client for vision LLM server.

    Uses extended timeout (30 min) because vision model processing
    can take 500-600+ seconds for complex pages with many elements.
    """
    import httpx

    return OpenAI(
        base_url=config.vision_llm_url,
        api_key="not-needed",
        timeout=httpx.Timeout(connect=30.0, read=1800.0, write=120.0, pool=60.0),
    )


def pdf_page_to_image(
    pdf_path: Union[str, Path],
    page_num: int,
    output_path: Union[str, Path],
    dpi: int = DEFAULT_DPI,
    max_dimension: int = MAX_PAGE_DIMENSION,
) -> Tuple[int, int, str]:
    """Convert single PDF page to image.

    Args:
        pdf_path: Path to PDF file
        page_num: Page number (1-indexed)
        output_path: Path to save the image
        dpi: Resolution for rendering
        max_dimension: Maximum pixels for longest side (rescales if exceeded)

    Returns:
        Tuple of (width, height, text) where text is the extracted OCR text
    """
    doc = fitz.open(str(pdf_path))
    page = doc[page_num - 1]  # 0-indexed

    # Render to image at requested DPI
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)

    # Check if we need to rescale (for large posters/high-DPI pages)
    width, height = pix.width, pix.height
    if max(width, height) > max_dimension:
        scale = max_dimension / max(width, height)
        new_width = int(width * scale)
        new_height = int(height * scale)
        # Re-render at reduced scale
        adjusted_dpi = dpi * scale
        mat = fitz.Matrix(adjusted_dpi / 72, adjusted_dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        width, height = pix.width, pix.height

    pix.save(str(output_path))

    # Extract and clean text
    text = page.get_text("text")
    if isinstance(text, str):
        text = clean_line_numbers(text)
    else:
        text = ""

    doc.close()

    return width, height, text


def _detect_elements(image_path: Path, client: OpenAI) -> str:
    """Use vision LLM to detect visual elements with bounding boxes.

    Args:
        image_path: Path to page image
        client: OpenAI client for vision LLM

    Returns:
        Raw JSON response from model
    """
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    response = client.chat.completions.create(
        model=config.vision_llm_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_data}"},
                    },
                    {"type": "text", "text": EXTRACTION_PROMPT},
                ],
            }
        ],
        max_tokens=2048,
        temperature=0.1,
    )

    content = response.choices[0].message.content
    return content if content is not None else ""


def _parse_elements(raw_response: str, width: int, height: int) -> List[Dict[str, Any]]:
    """Parse model response and convert 0-1000 coordinates to pixels.

    Args:
        raw_response: JSON string from model
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        List of element dictionaries with bbox_pixels and other metadata
    """
    content = raw_response

    # Extract JSON from markdown code blocks
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    # Fix invalid JSON escapes (common in LaTeX output)
    content = content.replace("\\\\", "\x00DBL\x00")
    content = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", content)
    content = content.replace("\x00DBL\x00", "\\\\")

    try:
        data = json.loads(content.strip())
    except json.JSONDecodeError:
        return []

    elements = []

    if isinstance(data, dict):
        for elem_type, items in data.items():
            if not isinstance(items, list):
                continue
            for item in items:
                bbox = item.get("bbox") or item.get("bbox_2d")
                if not bbox or len(bbox) != 4:
                    continue

                # Convert 0-1000 scale to pixels
                # Note: Vision model has systematic upward shift, add vertical offset
                # to correct (approx 1.06% of height)
                y_offset = int(0.0106 * height)
                px_bbox = [
                    int(bbox[0] / 1000 * width),
                    int(bbox[1] / 1000 * height) + y_offset,
                    int(bbox[2] / 1000 * width),
                    int(bbox[3] / 1000 * height) + y_offset,
                ]

                elem_data = {
                    "type": elem_type.rstrip("s"),  # "figures" -> "figure"
                    "bbox": bbox,  # Original 0-1000 scale
                    "bbox_pixels": px_bbox,
                    "label": item.get("label", elem_type),
                    "description": item.get("description", ""),
                }

                # For equations, extract LaTeX from description
                if elem_data["type"] == "equation":
                    latex = extract_latex_from_description(elem_data["description"])
                    if latex:
                        elem_data["latex"] = latex

                elements.append(elem_data)

    return elements


def _crop_and_save_element(
    image: Image.Image,
    element: Dict[str, Any],
    output_dir: Path,
    page_num: int,
    idx: int,
) -> Tuple[Optional[str], Optional[str]]:
    """Crop element from page and save.

    For equations with LaTeX, also renders the LaTeX to a separate image.

    Args:
        image: PIL Image of the page
        element: Element dictionary with bbox_pixels
        output_dir: Output directory
        page_num: Page number
        idx: Element index on page

    Returns:
        Tuple of (crop_path, rendered_path) where rendered_path may be None
    """
    bbox = element.get("bbox_pixels", [])
    if len(bbox) != 4:
        return None, None

    # Use core crop_element function
    # Use 7% padding around elements for safety margin
    padding = int(0.07 * min(image.width, image.height))
    cropped = crop_element(image, bbox, padding=padding, scale=image.width)
    if cropped is None:
        return None, None

    # Generate filename - sanitize label for filesystem
    elem_type = element.get("type", "element")
    label = element.get("label", "")
    label = re.sub(r"[^\w\s-]", "", label)  # Remove special chars
    label = re.sub(r"\s+", "_", label)  # Replace spaces
    label = label[:30]  # Limit length
    filename = f"p{page_num:02d}_{elem_type}_{idx}_{label}.png"

    elements_dir = output_dir / "elements"
    elements_dir.mkdir(parents=True, exist_ok=True)

    crop_path = elements_dir / filename
    cropped.save(str(crop_path))

    # For equations with LaTeX, render to separate image
    rendered_path = None
    if elem_type == "equation" and element.get("latex"):
        rendered_filename = filename.replace(".png", "_rendered.png")
        rendered_full_path = elements_dir / rendered_filename
        if render_latex_to_image(element["latex"], rendered_full_path):
            rendered_path = f"elements/{rendered_filename}"

    return f"elements/{filename}", rendered_path


def extract_page(
    pdf_path: Union[str, Path],
    page_num: int,
    output_dir: Union[str, Path],
    dpi: int = DEFAULT_DPI,
    save_annotated: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Extract elements from a single PDF page.

    Output structure:
        {output_dir}/images/page_001.png
        {output_dir}/images/page_001_annotated.png
        {output_dir}/pages/page_001.json
        {output_dir}/elements/p01_figure_1_*.png

    Args:
        pdf_path: Path to PDF file
        page_num: Page number (1-indexed)
        output_dir: Output directory
        dpi: Resolution for rendering
        save_annotated: Whether to save annotated page image
        verbose: Print progress

    Returns:
        Dictionary with page data including elements
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    # Create subdirectories
    images_dir = output_dir / "images"
    pages_dir = output_dir / "pages"
    elements_dir = output_dir / "elements"
    images_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)
    elements_dir.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"  Page {page_num}:")

    # Convert PDF page to image (in images/ subdirectory)
    page_image_path = images_dir / f"page_{page_num:03d}.png"
    if verbose:
        print(f"    Converting to image...", end=" ", flush=True)

    width, height, text = pdf_page_to_image(pdf_path, page_num, page_image_path, dpi)
    if verbose:
        print(f"{width}x{height}")

    # Detect elements using vision LLM
    if verbose:
        print(f"    Detecting elements...", end=" ", flush=True)

    client = _get_vision_client()
    detect_start = time.time()
    raw_response = _detect_elements(page_image_path, client)
    detect_time = time.time() - detect_start

    elements = _parse_elements(raw_response, width, height)
    if verbose:
        print(f"found {len(elements)} ({detect_time:.1f}s)")

    # Load page image for cropping
    page_image = Image.open(page_image_path)

    # Process each element
    for i, elem in enumerate(elements):
        if verbose:
            elem_type = elem.get("type", "")
            label = elem.get("label", "")
            print(f"      - {elem_type}: {label}")

        crop_path, rendered_path = _crop_and_save_element(
            page_image, elem, output_dir, page_num, i + 1
        )
        if crop_path:
            elem["crop_path"] = crop_path
        if rendered_path:
            elem["rendered_path"] = rendered_path
            if verbose:
                print(f"        + LaTeX rendered")

    # Create annotated page
    annotated_rel_path = None
    if save_annotated and elements:
        annotated_path = images_dir / f"page_{page_num:03d}_annotated.png"
        annotated = create_annotated_image(page_image, elements)
        annotated.save(str(annotated_path))
        annotated_rel_path = f"images/page_{page_num:03d}_annotated.png"

    # Build page data
    page_data = {
        "page_number": page_num,
        "image": f"images/page_{page_num:03d}.png",
        "annotated_image": annotated_rel_path,
        "width": width,
        "height": height,
        "text": text,
        "text_length": len(text),
        "elements": elements,
        "extraction_time_seconds": round(detect_time, 2),
        "extracted_at": datetime.now().isoformat(),
    }

    # Save page JSON to pages/ subdirectory
    page_json_path = pages_dir / f"page_{page_num:03d}.json"
    with open(page_json_path, "w") as f:
        json.dump(page_data, f, indent=2, ensure_ascii=False)

    return page_data


def _get_existing_pages(output_dir: Path) -> set:
    """Get set of page numbers already extracted."""
    pages_dir = output_dir / "pages"
    if not pages_dir.exists():
        return set()
    existing = set()
    for f in pages_dir.glob("page_*.json"):
        try:
            num = int(f.stem.split("_")[1])
            existing.add(num)
        except (IndexError, ValueError):
            pass
    return existing


def _update_document_json(output_dir: Path, pdf_path: Path, total_pages: int, model: str) -> None:
    """Update or create document.json with current status."""
    doc_json = output_dir / "document.json"

    doc_data: Dict[str, Any] = {}
    if doc_json.exists():
        with open(doc_json) as f:
            doc_data = json.load(f)

    if "extraction_date" not in doc_data:
        doc_data["extraction_date"] = datetime.now().isoformat()

    existing = _get_existing_pages(output_dir)

    doc_data["document"] = output_dir.name
    doc_data["source_file"] = pdf_path.name
    doc_data["source_path"] = str(pdf_path.absolute())
    doc_data["total_pages"] = total_pages
    doc_data["extracted_pages"] = sorted(list(existing))
    doc_data["extracted_count"] = len(existing)
    doc_data["model"] = model
    doc_data["last_updated"] = datetime.now().isoformat()

    with open(doc_json, "w") as f:
        json.dump(doc_data, f, indent=2, ensure_ascii=False)


def extract_document(
    pdf_path: Union[str, Path],
    output_dir: Union[str, Path],
    pages: List[int],
    dpi: int = DEFAULT_DPI,
    skip_existing: bool = False,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Extract elements from multiple PDF pages.

    Output structure:
        {output_dir}/document.json
        {output_dir}/images/page_001.png
        {output_dir}/pages/page_001.json
        {output_dir}/elements/p01_figure_1_*.png

    Args:
        pdf_path: Path to PDF file
        output_dir: Output directory
        pages: List of page numbers to extract
        dpi: Resolution for rendering
        skip_existing: If True, skip pages that already have JSON files
        verbose: Print progress

    Returns:
        Dictionary with extraction summary
    """
    import fitz  # for getting total page count

    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get total pages in PDF
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()

    # Filter out pages beyond document length
    original_count = len(pages)
    pages = [p for p in pages if p <= total_pages]
    if len(pages) < original_count and verbose:
        print(f"Note: Capped page range to {total_pages} (document length)")

    # Check for existing pages if skip_existing
    if skip_existing:
        existing = _get_existing_pages(output_dir)
        pages = [p for p in pages if p not in existing]
        if verbose and existing:
            print(f"Skipping {len(existing)} already extracted pages")

    if verbose:
        print(f"Document: {pdf_path.name}")
        print(f"Output: {output_dir}")
        print(f"Total pages in PDF: {total_pages}")
        print(f"Pages to extract: {len(pages)}")
        print("=" * 50)

    if not pages:
        if verbose:
            print("No pages to extract.")
        return {"pages_extracted": 0}

    total_start = time.time()
    total_elements = 0

    for i, page_num in enumerate(pages):
        if verbose:
            print(f"\n[{i + 1}/{len(pages)}]")

        page_start = time.time()
        page_data = extract_page(pdf_path, page_num, output_dir, dpi, verbose=verbose)
        page_time = time.time() - page_start

        total_elements += len(page_data.get("elements", []))

        if verbose:
            detect_time = page_data.get("extraction_time_seconds", 0)
            print(f"    Page completed in {page_time:.1f}s (detection: {detect_time:.1f}s)")

        # Update document.json after each page (for progress tracking)
        _update_document_json(output_dir, pdf_path, total_pages, config.vision_llm_model)

        # Delay between pages to prevent GPU overload/thermal issues
        if i < len(pages) - 1:
            time.sleep(5.0)

    total_time = time.time() - total_start

    result = {
        "pages_extracted": len(pages),
        "total_elements": total_elements,
        "total_seconds": round(total_time, 2),
        "avg_seconds_per_page": round(total_time / len(pages), 2) if pages else 0,
    }

    if verbose:
        print("\n" + "=" * 50)
        print(f"Done! Results saved to: {output_dir}")
        print(f"Pages extracted: {len(pages)}")
        print(f"Total elements found: {total_elements}")
        print(f"Total time: {total_time:.1f}s ({result['avg_seconds_per_page']:.1f}s per page)")

    return result


# --- CLI for testing ---

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Extract document with visual grounding")
    parser.add_argument("pdf_path", type=Path, help="Path to PDF file")
    parser.add_argument(
        "--pages",
        type=str,
        required=True,
        help="Page numbers: 'all', '1-10', or '1,2,3'",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="Page rendering DPI")
    parser.add_argument("--skip-existing", action="store_true", help="Skip pages already extracted")

    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"Error: File not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Parse pages argument
    if args.pages.lower() == "all":
        import fitz

        doc = fitz.open(str(args.pdf_path))
        pages = list(range(1, len(doc) + 1))
        doc.close()
    elif "-" in args.pages and "," not in args.pages:
        start, end = args.pages.split("-", 1)
        pages = list(range(int(start), int(end) + 1))
    else:
        pages = [int(p.strip()) for p in args.pages.split(",")]

    extract_document(
        args.pdf_path, args.output_dir, pages, args.dpi, skip_existing=args.skip_existing
    )
