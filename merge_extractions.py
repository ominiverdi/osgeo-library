#!/usr/bin/env python3
"""
Merge multiple multimodal extraction JSONs into the comparison viewer.

This allows comparing different models' extractions of the same pages.
Each page can have multiple extractions from different models.
"""

import argparse
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

    # Only generate if doesn't exist
    if not output_path.exists():
        pix.save(str(output_path))
        print(f"  Generated image: {filename}", file=sys.stderr)

    return filename


def load_extraction_data(json_path: Path) -> dict:
    """Load extraction JSON and return pages dict keyed by page number."""
    with open(json_path) as f:
        data = json.load(f)

    pages = {}
    model = data.get("model", "unknown")

    for page in data.get("pages", []):
        page_num = page.get("page_number")
        if page_num is None:
            continue

        result = page.get("extraction_result", {})

        # Build extraction data with model info
        extracted = {
            "model": page.get("model", model),
            "model_display": page.get("model_display", model),
        }

        if result.get("error"):
            extracted["error"] = True
            extracted["message"] = result.get("message", "Unknown error")
        elif result.get("data"):
            extracted.update(result.get("data"))
        elif result.get("raw"):
            extracted["text_content"] = result.get("raw")

        # Include extracted images
        if page.get("extracted_images"):
            extracted["extracted_images"] = page["extracted_images"]

        pages[page_num] = extracted

    return pages


def main():
    parser = argparse.ArgumentParser(
        description="Merge multiple extraction JSONs into comparison viewer"
    )
    parser.add_argument("pdf_path", type=Path, help="Path to PDF file")
    parser.add_argument(
        "extraction_jsons",
        type=Path,
        nargs="+",
        help="Paths to extraction JSON files to merge",
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

    # Load all extraction data
    all_extractions = {}  # page_num -> list of extractions

    for json_path in args.extraction_jsons:
        if not json_path.exists():
            print(f"Warning: Skipping missing file: {json_path}", file=sys.stderr)
            continue

        print(f"Loading: {json_path}", file=sys.stderr)
        pages = load_extraction_data(json_path)

        for page_num, data in pages.items():
            if page_num not in all_extractions:
                all_extractions[page_num] = []
            all_extractions[page_num].append(data)

    if not all_extractions:
        print("Error: No extraction data found", file=sys.stderr)
        sys.exit(1)

    # Open PDF and generate page images
    doc = fitz.open(args.pdf_path)
    pdf_name = args.pdf_path.name
    images_dir = args.output_dir / "data"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Build comparison structure
    # For model comparison, we create multiple page entries: page_num_model
    comparison_pages = {}

    for page_num in sorted(all_extractions.keys()):
        # Generate page image
        image_filename = generate_page_image(doc, page_num - 1, images_dir, args.dpi)

        for extraction in all_extractions[page_num]:
            model_display = extraction.get("model_display", "Unknown")
            # Create unique key combining page and model
            page_key = f"{page_num}_{model_display.replace(' ', '_')}"

            comparison_pages[page_key] = {
                "page_number": page_num,
                "image": image_filename,
                "traditional": None,
                "multimodal": extraction,
            }

    doc.close()

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

    # Update/add this PDF's data
    all_comparisons["pdfs"][pdf_name] = {
        "pdf_path": str(args.pdf_path),
        "total_pages": fitz.open(args.pdf_path).page_count,
        "pages": comparison_pages,
    }
    all_comparisons["generated_date"] = datetime.now().isoformat()

    # Save
    with open(comparisons_path, "w") as f:
        json.dump(all_comparisons, f, indent=2)

    print(
        f"\nMerged {len(all_extractions)} pages with {sum(len(v) for v in all_extractions.values())} total extractions",
        file=sys.stderr,
    )
    print(f"Output: {comparisons_path}", file=sys.stderr)

    # Summary by model
    models = {}
    for extractions in all_extractions.values():
        for ext in extractions:
            model = ext.get("model_display", "Unknown")
            has_error = ext.get("error", False)
            if model not in models:
                models[model] = {"success": 0, "error": 0}
            if has_error:
                models[model]["error"] += 1
            else:
                models[model]["success"] += 1

    print("\nBy model:", file=sys.stderr)
    for model, counts in sorted(models.items()):
        print(
            f"  {model}: {counts['success']} success, {counts['error']} errors",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
