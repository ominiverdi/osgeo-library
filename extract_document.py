#!/usr/bin/env python3
"""
Document Extraction Pipeline using Qwen3-VL-32B for visual grounding.

Extracts pages from PDF, detects figures/tables/diagrams with bounding boxes,
crops detected elements, and generates structured JSON for the web viewer.

Usage:
    python extract_document.py document.pdf --pages 1,2,3 --output-dir web/data/doc_name
"""

import argparse
import base64
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw
from openai import OpenAI


# Configuration
LLAMA_SERVER = "http://localhost:8090/v1"
MODEL_NAME = "qwen3-vl-235b"
DPI = 150


def get_client():
    """Get OpenAI client for local llama.cpp server."""
    return OpenAI(base_url=LLAMA_SERVER, api_key="not-needed")


def pdf_page_to_image(pdf_path: Path, page_num: int, output_path: Path) -> tuple:
    """Convert single PDF page to image. Returns (width, height, text)."""
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]  # 0-indexed

    # Render to image
    mat = fitz.Matrix(DPI / 72, DPI / 72)
    pix = page.get_pixmap(matrix=mat)
    pix.save(str(output_path))

    # Extract text
    text = page.get_text("text")

    width, height = pix.width, pix.height
    doc.close()

    return width, height, text


def detect_elements(image_path: Path, client: OpenAI) -> str:
    """Use Qwen3-VL-32B to detect visual elements with bounding boxes."""

    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    prompt = """Analyze this document page and locate all visual elements (figures, tables, diagrams, charts, equations).

For each element found, provide:
- type: figure, table, diagram, chart, or equation
- bbox: bounding box as [x1, y1, x2, y2] in 0-1000 scale (top-left to bottom-right)
- label: identifier if visible (e.g., "Figure 1", "Table 2", "Equation 3")
- description: brief description of content (for equations, include the LaTeX representation if possible)

Return JSON format:
{
  "figure": [{"bbox": [x1,y1,x2,y2], "label": "Figure 1", "description": "..."}],
  "table": [{"bbox": [x1,y1,x2,y2], "label": "Table 1", "description": "..."}],
  "diagram": [],
  "chart": [],
  "equation": [{"bbox": [x1,y1,x2,y2], "label": "Equation 1", "description": "LaTeX: ..."}]
}

Use empty arrays [] for categories with no elements."""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_data}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        max_tokens=2048,
        temperature=0.1,
    )

    return response.choices[0].message.content


def parse_elements(raw_response: str, width: int, height: int) -> list:
    """Parse model response and convert 0-1000 coordinates to pixels."""

    # Extract JSON from response
    content = raw_response
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    # Fix invalid JSON escapes (common in LaTeX output)
    # Replace single backslashes that aren't valid JSON escapes
    import re

    # Valid JSON escapes: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
    # First, normalize already-escaped backslashes to a placeholder
    content = content.replace("\\\\", "\x00DBL\x00")
    # Fix single backslashes that aren't valid JSON escapes
    content = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", content)
    # Restore double backslashes
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
                px_bbox = [
                    int(bbox[0] / 1000 * width),
                    int(bbox[1] / 1000 * height),
                    int(bbox[2] / 1000 * width),
                    int(bbox[3] / 1000 * height),
                ]

                elements.append(
                    {
                        "type": elem_type.rstrip("s"),
                        "bbox_1000": bbox,
                        "bbox_pixels": px_bbox,
                        "label": item.get("label", elem_type),
                        "description": item.get("description", ""),
                    }
                )

    return elements


def crop_element(
    image_path: Path, elem: dict, output_dir: Path, page_num: int, idx: int
) -> str:
    """Crop element from page and save. Returns relative path to crop."""
    img = Image.open(image_path)
    bbox = elem.get("bbox_pixels", [])

    if len(bbox) != 4:
        return None

    x1, y1, x2, y2 = bbox

    # Add padding
    padding = 10
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(img.width, x2 + padding)
    y2 = min(img.height, y2 + padding)

    crop = img.crop((x1, y1, x2, y2))

    # Generate filename
    elem_type = elem.get("type", "element")
    label = elem.get("label", "").replace(" ", "_").replace("/", "-")[:20]
    filename = f"p{page_num:02d}_{elem_type}_{idx}_{label}.png"

    elements_dir = output_dir / "elements"
    elements_dir.mkdir(parents=True, exist_ok=True)

    crop_path = elements_dir / filename
    crop.save(str(crop_path))

    return f"elements/{filename}"


def create_annotated_page(image_path: Path, elements: list, output_path: Path):
    """Create page image with bounding boxes drawn."""
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    colors = {
        "figure": "red",
        "table": "blue",
        "diagram": "green",
        "chart": "orange",
        "equation": "purple",
    }

    for elem in elements:
        bbox = elem.get("bbox_pixels", [])
        if len(bbox) != 4:
            continue

        x1, y1, x2, y2 = bbox
        elem_type = elem.get("type", "unknown")
        color = colors.get(elem_type, "yellow")

        draw.rectangle(((x1, y1), (x2, y2)), outline=color, width=3)
        label = elem.get("label", elem_type)[:30]
        draw.text((x1 + 5, y1 + 5), label, fill=color)

    img.save(str(output_path))


def extract_document(
    pdf_path: Path, output_dir: Path, pages: list, merge: bool = False
) -> dict:
    """Main extraction pipeline."""

    print(f"Document: {pdf_path.name}")
    print(f"Output: {output_dir}")
    print(f"Pages: {pages}")
    print(f"Merge mode: {merge}")
    print("=" * 50)

    output_dir.mkdir(parents=True, exist_ok=True)
    client = get_client()

    # Load existing extraction if merge mode enabled
    existing_pages = {}
    result_path = output_dir / "extraction.json"
    if merge and result_path.exists():
        with open(result_path) as f:
            existing_data = json.load(f)
            for p in existing_data.get("pages", []):
                existing_pages[p["page_number"]] = p
            print(f"Loaded {len(existing_pages)} existing pages")

    result = {
        "document": pdf_path.stem,
        "source_file": pdf_path.name,
        "extraction_date": datetime.now().isoformat(),
        "model": MODEL_NAME,
        "pages": [],
        "timing": {},
    }

    total_start = time.time()

    for page_num in pages:
        print(f"\nPage {page_num}:")
        page_start = time.time()

        # Convert PDF page to image
        page_image = output_dir / f"page_{page_num:02d}.png"
        print(f"  Converting to image...", end=" ", flush=True)
        width, height, text = pdf_page_to_image(pdf_path, page_num, page_image)
        print(f"{width}x{height}")

        # Detect elements
        print(f"  Detecting elements...", end=" ", flush=True)
        detect_start = time.time()
        raw_response = detect_elements(page_image, client)
        detect_time = time.time() - detect_start
        elements = parse_elements(raw_response, width, height)
        print(f"found {len(elements)} ({detect_time:.1f}s)")

        # Process elements
        for i, elem in enumerate(elements):
            elem_type = elem.get("type", "")
            label = elem.get("label", "")
            bbox = elem.get("bbox_1000", [])
            pos = f"{bbox[1] // 10}%-{bbox[3] // 10}%" if len(bbox) == 4 else "?"
            print(f"    - {elem_type}: {label} (vertical: {pos})")

            # Crop element
            crop_path = crop_element(page_image, elem, output_dir, page_num, i + 1)
            if crop_path:
                elem["crop_path"] = crop_path

        # Create annotated page
        if elements:
            annotated = output_dir / f"page_{page_num:02d}_annotated.png"
            create_annotated_page(page_image, elements, annotated)

        # Calculate page timing
        page_time = time.time() - page_start

        # Store page data
        page_data = {
            "page_number": page_num,
            "image": f"page_{page_num:02d}.png",
            "annotated_image": f"page_{page_num:02d}_annotated.png"
            if elements
            else None,
            "width": width,
            "height": height,
            "text": text,
            "text_length": len(text),
            "elements": elements,
            "extraction_time_seconds": round(detect_time, 2),
            "total_page_time_seconds": round(page_time, 2),
        }
        result["pages"].append(page_data)
        print(f"  Page completed in {page_time:.1f}s (detection: {detect_time:.1f}s)")

        # Small delay between requests
        time.sleep(1)

    # Merge with existing pages if in merge mode
    if merge and existing_pages:
        # Build set of newly extracted page numbers
        new_page_nums = {p["page_number"] for p in result["pages"]}
        # Add existing pages that weren't re-extracted
        for page_num, page_data in existing_pages.items():
            if page_num not in new_page_nums:
                result["pages"].append(page_data)
        # Sort pages by page number
        result["pages"].sort(key=lambda p: p["page_number"])

    # Save results
    result_path = output_dir / "extraction.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total_time = time.time() - total_start

    # Store timing in result
    result["timing"] = {
        "total_seconds": round(total_time, 2),
        "pages_extracted": len(pages),
        "avg_seconds_per_page": round(total_time / len(pages), 2) if pages else 0,
    }

    print("\n" + "=" * 50)
    print(f"Done! Results saved to: {result_path}")

    total_elements = sum(len(p["elements"]) for p in result["pages"])
    print(f"Total elements extracted: {total_elements}")
    print(f"Total time: {total_time:.1f}s ({total_time / len(pages):.1f}s per page)")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Extract document with visual grounding"
    )
    parser.add_argument("pdf_path", type=Path, help="Path to PDF file")
    parser.add_argument(
        "--pages",
        type=str,
        required=True,
        help="Comma-separated page numbers (e.g., 1,2,3)",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Output directory"
    )
    parser.add_argument(
        "--dpi", type=int, default=150, help="Page rendering DPI (default: 150)"
    )
    parser.add_argument(
        "--merge", action="store_true", help="Merge with existing extraction.json"
    )

    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"Error: File not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Parse page numbers
    pages = [int(p.strip()) for p in args.pages.split(",")]

    # Update DPI if specified
    global DPI
    if args.dpi != 150:
        DPI = args.dpi

    extract_document(args.pdf_path, args.output_dir, pages, merge=args.merge)


if __name__ == "__main__":
    main()
