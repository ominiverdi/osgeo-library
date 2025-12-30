#!/usr/bin/env python3
"""
Traditional PDF extraction using PyMuPDF.

Extracts metadata, text, and identifies images/figures from PDF files.
Outputs structured JSON for analysis.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import fitz  # PyMuPDF


def extract_metadata(doc: fitz.Document) -> dict:
    """Extract PDF metadata."""
    meta = doc.metadata
    return {
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "subject": meta.get("subject", ""),
        "keywords": meta.get("keywords", ""),
        "creator": meta.get("creator", ""),
        "producer": meta.get("producer", ""),
        "creation_date": meta.get("creationDate", ""),
        "modification_date": meta.get("modDate", ""),
        "page_count": len(doc),
    }


def extract_page(page: fitz.Page, page_num: int) -> dict:
    """Extract content from a single page."""
    # Get text
    text = page.get_text("text")

    # Get text blocks with positions (for structure analysis)
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

    # Count images
    images = page.get_images(full=True)

    # Get links
    links = page.get_links()

    return {
        "page_number": page_num + 1,  # 1-indexed
        "width": page.rect.width,
        "height": page.rect.height,
        "text": text,
        "text_length": len(text),
        "block_count": len(blocks.get("blocks", [])),
        "image_count": len(images),
        "images": [
            {
                "xref": img[0],
                "width": img[2],
                "height": img[3],
            }
            for img in images
        ],
        "link_count": len(links),
    }


def extract_pdf(pdf_path: Path, max_pages: int | None = None) -> dict:
    """Extract all content from a PDF file."""
    doc = fitz.open(pdf_path)

    result = {
        "source_file": str(pdf_path),
        "file_size_bytes": pdf_path.stat().st_size,
        "extraction_date": datetime.now().isoformat(),
        "extraction_tool": f"PyMuPDF {fitz.version[0]}",
        "metadata": extract_metadata(doc),
        "pages": [],
        "summary": {
            "total_pages": len(doc),
            "pages_extracted": 0,
            "total_text_length": 0,
            "total_images": 0,
        },
    }

    pages_to_extract = len(doc) if max_pages is None else min(max_pages, len(doc))

    for page_num in range(pages_to_extract):
        page = doc[page_num]
        page_data = extract_page(page, page_num)
        result["pages"].append(page_data)
        result["summary"]["total_text_length"] += page_data["text_length"]
        result["summary"]["total_images"] += page_data["image_count"]

    result["summary"]["pages_extracted"] = pages_to_extract

    doc.close()
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Extract content from PDF using PyMuPDF"
    )
    parser.add_argument("pdf_path", type=Path, help="Path to PDF file")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum pages to extract (default: all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON file (default: stdout)",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="Output only extracted text (no JSON structure)",
    )

    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"Error: File not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    result = extract_pdf(args.pdf_path, args.max_pages)

    if args.text_only:
        # Output just the text
        for page in result["pages"]:
            print(f"\n{'=' * 60}")
            print(f"PAGE {page['page_number']}")
            print("=" * 60)
            print(page["text"])
    else:
        # Output JSON
        output_json = json.dumps(result, indent=2, ensure_ascii=False)

        if args.output:
            args.output.write_text(output_json)
            print(f"Output written to: {args.output}", file=sys.stderr)
        else:
            print(output_json)

    # Print summary to stderr
    print(f"\nSummary:", file=sys.stderr)
    print(
        f"  Pages: {result['summary']['pages_extracted']}/{result['summary']['total_pages']}",
        file=sys.stderr,
    )
    print(
        f"  Text: {result['summary']['total_text_length']} characters", file=sys.stderr
    )
    print(f"  Images: {result['summary']['total_images']}", file=sys.stderr)


if __name__ == "__main__":
    main()
