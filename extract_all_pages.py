#!/usr/bin/env python3
"""
Extract ALL pages from PDFs to db/data/ structure.

Reuses functions from extract_document.py but outputs per-page JSON files
directly to db/data/{doc}/pages/ structure. Skips already-extracted pages
for resumability.

Usage:
    python extract_all_pages.py sam3.pdf --name sam3
    python extract_all_pages.py sam3.pdf --name sam3 --pages 1-10
    python extract_all_pages.py sam3.pdf --name sam3 --skip-existing
    python extract_all_pages.py --list  # Show status of all documents

Output structure:
    db/data/{name}/
        document.json
        pages/page_001.json, page_002.json, ...
        images/page_001.png, page_001_annotated.png, ...
        elements/p01_figure_1_*.png, ...
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF

# Import functions from extract_document.py
from extract_document import (
    get_client,
    pdf_page_to_image,
    detect_elements,
    parse_elements,
    crop_element,
    create_annotated_page,
    extract_latex_from_description,
    render_latex_to_image,
    DPI,
)


DB_DATA_DIR = Path("db/data")


def get_existing_pages(doc_dir: Path) -> set:
    """Get set of page numbers already extracted."""
    pages_dir = doc_dir / "pages"
    if not pages_dir.exists():
        return set()

    existing = set()
    for f in pages_dir.glob("page_*.json"):
        # Extract page number from filename like "page_001.json"
        try:
            num = int(f.stem.split("_")[1])
            existing.add(num)
        except (IndexError, ValueError):
            pass
    return existing


def extract_single_page(
    pdf_path: Path,
    page_num: int,
    doc_dir: Path,
    client,
    skip_detection: bool = False,
) -> dict:
    """Extract a single page and save to db/data structure.

    Returns dict with extraction results.
    """
    images_dir = doc_dir / "images"
    pages_dir = doc_dir / "pages"
    elements_dir = doc_dir / "elements"

    # Ensure directories exist
    images_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)
    elements_dir.mkdir(parents=True, exist_ok=True)

    page_start = time.time()

    # Convert PDF page to image
    page_image = images_dir / f"page_{page_num:03d}.png"
    width, height, text = pdf_page_to_image(pdf_path, page_num, page_image)

    elements = []
    detect_time = 0

    if not skip_detection:
        # Detect elements using LLM
        detect_start = time.time()
        try:
            raw_response = detect_elements(page_image, client)
            elements = parse_elements(raw_response, width, height)
            detect_time = time.time() - detect_start
        except Exception as e:
            print(f"    [ERROR] Detection failed: {e}")
            detect_time = time.time() - detect_start

    # Process elements: crop and render LaTeX
    for i, elem in enumerate(elements):
        # Crop element - need to adjust for db/data structure
        crop_path, rendered_path = crop_element_db(
            page_image, elem, doc_dir, page_num, i + 1
        )
        if crop_path:
            elem["crop_path"] = crop_path
        if rendered_path:
            elem["rendered_path"] = rendered_path

    # Create annotated page if elements found
    annotated_image = None
    if elements:
        annotated_path = images_dir / f"page_{page_num:03d}_annotated.png"
        create_annotated_page(page_image, elements, annotated_path)
        annotated_image = f"images/page_{page_num:03d}_annotated.png"

    page_time = time.time() - page_start

    # Build page data
    page_data = {
        "page_number": page_num,
        "image": f"images/page_{page_num:03d}.png",
        "annotated_image": annotated_image,
        "width": width,
        "height": height,
        "text": text,
        "text_length": len(text),
        "elements": elements,
        "extraction_time_seconds": round(detect_time, 2),
        "total_page_time_seconds": round(page_time, 2),
        "extracted_at": datetime.now().isoformat(),
    }

    # Save page JSON
    page_json = pages_dir / f"page_{page_num:03d}.json"
    with open(page_json, "w") as f:
        json.dump(page_data, f, indent=2, ensure_ascii=False)

    return {
        "page_number": page_num,
        "elements_count": len(elements),
        "text_length": len(text),
        "detect_time": detect_time,
        "total_time": page_time,
    }


def crop_element_db(
    image_path: Path, elem: dict, doc_dir: Path, page_num: int, idx: int
) -> tuple:
    """Crop element and save to db/data structure.

    Adapted from extract_document.crop_element but saves to elements/ dir.
    Returns tuple of (crop_path, rendered_path) relative to doc_dir.
    """
    import re
    from PIL import Image

    img = Image.open(image_path)
    bbox = elem.get("bbox_pixels", [])

    if len(bbox) != 4:
        return None, None

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
    label = elem.get("label", "")
    label = re.sub(r"[^\w\s-]", "", label)
    label = re.sub(r"\s+", "_", label)
    label = label[:30]
    filename = f"p{page_num:02d}_{elem_type}_{idx}_{label}.png"

    elements_dir = doc_dir / "elements"
    elements_dir.mkdir(parents=True, exist_ok=True)

    crop_path = elements_dir / filename
    crop.save(str(crop_path))

    # For equations with LaTeX, render to separate image
    rendered_path = None
    if elem_type == "equation":
        latex = extract_latex_from_description(elem.get("description", ""))
        if latex:
            elem["latex"] = latex
            rendered_filename = filename.replace(".png", "_rendered.png")
            rendered_full_path = elements_dir / rendered_filename
            if render_latex_to_image(latex, rendered_full_path):
                rendered_path = f"elements/{rendered_filename}"

    return f"elements/{filename}", rendered_path


def update_document_json(doc_dir: Path, pdf_path: Path, total_pages: int):
    """Update or create document.json with current status."""
    doc_json = doc_dir / "document.json"

    if doc_json.exists():
        with open(doc_json) as f:
            doc_data = json.load(f)
    else:
        doc_data = {}

    # Get list of extracted pages
    existing = get_existing_pages(doc_dir)

    # Set extraction_date only on first extraction (preserve if already set)
    if "extraction_date" not in doc_data:
        doc_data["extraction_date"] = datetime.now().isoformat()

    doc_data.update(
        {
            "document": doc_dir.name,
            "source_file": pdf_path.name,
            "source_path": str(pdf_path.absolute()),
            "total_pages": total_pages,
            "extracted_pages": sorted(list(existing)),
            "extracted_count": len(existing),
            "last_updated": datetime.now().isoformat(),
        }
    )

    with open(doc_json, "w") as f:
        json.dump(doc_data, f, indent=2, ensure_ascii=False)


def parse_page_range(page_spec: str, total_pages: int) -> list:
    """Parse page specification like '1-10' or '1,5,10' or 'all'."""
    if page_spec.lower() == "all":
        return list(range(1, total_pages + 1))

    pages = []
    for part in page_spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start = int(start)
            end = min(int(end), total_pages)
            pages.extend(range(start, end + 1))
        else:
            pages.append(int(part))

    return sorted(set(p for p in pages if 1 <= p <= total_pages))


def find_doc_dir_for_pdf(pdf_path: Path) -> Path:
    """Find existing db/data directory for a PDF by checking document.json."""
    pdf_name = pdf_path.name

    # First, check if folder with PDF stem exists
    stem_dir = DB_DATA_DIR / pdf_path.stem
    if stem_dir.exists():
        return stem_dir

    # Search all document.json files for matching source_file
    if DB_DATA_DIR.exists():
        for doc_dir in DB_DATA_DIR.iterdir():
            if doc_dir.is_dir():
                doc_json = doc_dir / "document.json"
                if doc_json.exists():
                    with open(doc_json) as f:
                        data = json.load(f)
                    if data.get("source_file") == pdf_name:
                        return doc_dir

    # Default to PDF stem
    return stem_dir


def list_documents():
    """List all documents and their extraction status."""
    print("\nDocument Extraction Status")
    print("=" * 70)

    # Check PDFs in current directory
    pdfs = list(Path(".").glob("*.pdf"))

    for pdf in sorted(pdfs):
        doc = fitz.open(pdf)
        total = len(doc)
        doc.close()

        # Find the corresponding db/data directory
        doc_dir = find_doc_dir_for_pdf(pdf)
        existing = get_existing_pages(doc_dir)

        status = "not started"
        folder_info = ""
        if existing:
            if len(existing) == total:
                status = "complete"
            else:
                status = f"{len(existing)}/{total} pages"
            folder_info = f" -> {doc_dir.name}"

        print(f"  {pdf.name:40} {total:4} pages  [{status}]{folder_info}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Extract all pages from PDF to db/data structure"
    )
    parser.add_argument("pdf_path", type=Path, nargs="?", help="Path to PDF file")
    parser.add_argument("--name", type=str, help="Document name (default: PDF stem)")
    parser.add_argument(
        "--pages",
        type=str,
        default="all",
        help="Pages to extract: 'all', '1-10', '1,5,10' (default: all)",
    )
    parser.add_argument(
        "--skip-existing", action="store_true", help="Skip pages already extracted"
    )
    parser.add_argument(
        "--skip-detection",
        action="store_true",
        help="Skip LLM detection (only extract text and render pages)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_docs",
        help="List all documents and their extraction status",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between pages in seconds (default: 1.0)",
    )

    args = parser.parse_args()

    if args.list_docs:
        list_documents()
        return

    if not args.pdf_path:
        parser.print_help()
        sys.exit(1)

    if not args.pdf_path.exists():
        print(f"Error: File not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Determine document name and directory
    doc_name = args.name or args.pdf_path.stem
    doc_dir = DB_DATA_DIR / doc_name

    # Get total pages
    pdf_doc = fitz.open(args.pdf_path)
    total_pages = len(pdf_doc)
    pdf_doc.close()

    # Parse page range
    pages_to_extract = parse_page_range(args.pages, total_pages)

    # Skip existing if requested
    if args.skip_existing:
        existing = get_existing_pages(doc_dir)
        pages_to_extract = [p for p in pages_to_extract if p not in existing]

    if not pages_to_extract:
        print(f"No pages to extract (all {total_pages} pages already done)")
        return

    print("=" * 60)
    print(f"Extracting: {args.pdf_path.name}")
    print(f"Output: {doc_dir}")
    print(f"Total pages in PDF: {total_pages}")
    print(f"Pages to extract: {len(pages_to_extract)}")
    if args.skip_detection:
        print("Mode: Text extraction only (no LLM detection)")
    else:
        print("Mode: Full extraction with LLM element detection")
    print("=" * 60)

    # Initialize LLM client if doing detection
    client = None
    if not args.skip_detection:
        print("\nConnecting to LLM server...", end=" ", flush=True)
        try:
            client = get_client()
            # Test connection
            print("OK")
        except Exception as e:
            print(f"FAILED: {e}")
            sys.exit(1)

    # Create directories
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Extract pages
    total_start = time.time()
    total_elements = 0

    for i, page_num in enumerate(pages_to_extract):
        print(f"\n[{i + 1}/{len(pages_to_extract)}] Page {page_num}:")

        try:
            result = extract_single_page(
                args.pdf_path,
                page_num,
                doc_dir,
                client,
                skip_detection=args.skip_detection,
            )

            elem_count = result["elements_count"]
            total_elements += elem_count
            detect_time = result["detect_time"]

            if elem_count > 0:
                print(f"  Found {elem_count} elements ({detect_time:.1f}s)")
            else:
                print(f"  No elements ({detect_time:.1f}s)")

        except Exception as e:
            print(f"  [ERROR] {e}")

        # Update document.json after each page (for progress tracking)
        update_document_json(doc_dir, args.pdf_path, total_pages)

        # Delay between pages
        if i < len(pages_to_extract) - 1:
            time.sleep(args.delay)

    total_time = time.time() - total_start

    print("\n" + "=" * 60)
    print(f"Done!")
    print(f"Pages extracted: {len(pages_to_extract)}")
    print(f"Total elements found: {total_elements}")
    print(
        f"Total time: {total_time:.1f}s ({total_time / len(pages_to_extract):.1f}s per page)"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
