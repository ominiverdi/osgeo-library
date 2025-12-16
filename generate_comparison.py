#!/usr/bin/env python3
"""
Generate comparison data for the web viewer.

Creates page images and combines traditional + multimodal extraction
results into a single JSON file for the comparison website.
"""

import argparse
import base64
import json
import sys
from pathlib import Path
from datetime import datetime

import fitz  # PyMuPDF


def generate_page_image(
    doc: fitz.Document, page_num: int, output_dir: Path, dpi: int = 150
) -> str:
    """Generate PNG image for a PDF page and return filename."""
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)

    filename = f"page_{page_num + 1:03d}.png"
    output_path = output_dir / filename
    pix.save(str(output_path))

    return filename


def load_traditional_extraction(json_path: Path, page_num: int) -> dict | None:
    """Load traditional extraction data for a specific page."""
    if not json_path.exists():
        return None

    with open(json_path) as f:
        data = json.load(f)

    for page in data.get("pages", []):
        if page.get("page_number") == page_num:
            return {
                "text": page.get("text", ""),
                "text_length": page.get("text_length", 0),
                "image_count": page.get("image_count", 0),
                "block_count": page.get("block_count", 0),
                "link_count": page.get("link_count", 0),
            }

    return None


def load_multimodal_extraction(json_path: Path, page_num: int) -> dict | None:
    """Load multimodal extraction data for a specific page."""
    if not json_path.exists():
        return None

    with open(json_path) as f:
        data = json.load(f)

    for page in data.get("pages", []):
        if page.get("page_number") == page_num:
            result = page.get("extraction_result", {})

            # Start with model info
            extracted = {
                "model": page.get("model", data.get("model", "unknown")),
                "model_display": page.get("model_display", "Unknown Model"),
            }

            if result.get("error"):
                extracted["error"] = True
                extracted["message"] = result.get("message", "Unknown error")
                return extracted

            # Merge in the extracted data
            if result.get("data"):
                extracted.update(result.get("data"))

            # Include extracted images info if present
            if page.get("extracted_images"):
                extracted["extracted_images"] = page["extracted_images"]

            if len(extracted) > 2:  # More than just model info
                return extracted

            # If no structured data, return raw with model info
            if result.get("raw"):
                extracted["text_content"] = result.get("raw")
                return extracted

    return None


def generate_comparison(
    pdf_path: Path,
    traditional_json: Path | None,
    multimodal_json: Path | None,
    output_dir: Path,
    pages: list[int] | None = None,
    dpi: int = 150,
) -> dict:
    """Generate comparison data for a PDF."""

    doc = fitz.open(pdf_path)
    pdf_name = pdf_path.name

    # Create output directory for images
    images_dir = output_dir / "data"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Determine pages to process
    if pages is None:
        pages_to_process = list(range(1, len(doc) + 1))
    else:
        pages_to_process = [p for p in pages if 0 < p <= len(doc)]

    result = {
        "pdf_name": pdf_name,
        "pdf_path": str(pdf_path),
        "total_pages": len(doc),
        "generated_date": datetime.now().isoformat(),
        "pages": {},
    }

    for page_num in pages_to_process:
        print(f"Processing page {page_num}/{len(doc)}...", file=sys.stderr)

        # Generate page image
        image_filename = generate_page_image(doc, page_num - 1, images_dir, dpi)

        # Load extraction data
        traditional_data = None
        multimodal_data = None

        if traditional_json:
            traditional_data = load_traditional_extraction(traditional_json, page_num)

        if multimodal_json:
            multimodal_data = load_multimodal_extraction(multimodal_json, page_num)

        result["pages"][page_num] = {
            "image": image_filename,
            "traditional": traditional_data,
            "multimodal": multimodal_data,
        }

    doc.close()
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate comparison data for web viewer"
    )
    parser.add_argument("pdf_path", type=Path, help="Path to PDF file")
    parser.add_argument(
        "--traditional",
        type=Path,
        default=None,
        help="Path to traditional extraction JSON",
    )
    parser.add_argument(
        "--multimodal",
        type=Path,
        default=None,
        help="Path to multimodal extraction JSON",
    )
    parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Pages to process (comma-separated, e.g., '1,2,5'). Default: all",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("web"),
        help="Output directory for web files (default: web/)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="DPI for page images (default: 150)",
    )

    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"Error: PDF not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Parse pages
    pages = None
    if args.pages:
        pages = [int(p.strip()) for p in args.pages.split(",")]

    # Generate comparison data
    comparison = generate_comparison(
        args.pdf_path,
        args.traditional,
        args.multimodal,
        args.output_dir,
        pages=pages,
        dpi=args.dpi,
    )

    # Load existing comparisons.json or create new
    comparisons_path = args.output_dir / "data" / "comparisons.json"
    if comparisons_path.exists():
        with open(comparisons_path) as f:
            all_comparisons = json.load(f)
    else:
        all_comparisons = {
            "generated_date": datetime.now().isoformat(),
            "pdfs": {},
        }

    # Add/update this PDF's data
    all_comparisons["pdfs"][comparison["pdf_name"]] = {
        "pdf_path": comparison["pdf_path"],
        "total_pages": comparison["total_pages"],
        "pages": comparison["pages"],
    }
    all_comparisons["generated_date"] = datetime.now().isoformat()

    # Save
    comparisons_path.parent.mkdir(parents=True, exist_ok=True)
    with open(comparisons_path, "w") as f:
        json.dump(all_comparisons, f, indent=2)

    print(f"Comparison data saved to: {comparisons_path}", file=sys.stderr)
    print(f"Pages processed: {len(comparison['pages'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
