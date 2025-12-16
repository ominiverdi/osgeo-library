#!/usr/bin/env python3
"""
Extract complete figures from PDFs by detecting captions and rendering regions.

This approach works for scientific papers where figures have captions like:
- "Figure 1: ..."
- "Fig. 2. ..."
- "Table 1: ..."

The script:
1. Finds figure/table captions using text search
2. Determines the figure region (area above the caption)
3. Renders that region as a high-quality image
"""

import argparse
import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass

import fitz  # PyMuPDF


@dataclass
class FigureRegion:
    """Detected figure region."""

    number: str  # e.g., "Figure 2" or "Table 1"
    caption: str  # Full caption text
    page_num: int  # 0-indexed page number
    bbox: tuple  # (x0, y0, x1, y1) bounding box
    caption_bbox: tuple  # Caption text bounding box


def find_captions(page: fitz.Page, page_num: int) -> list[FigureRegion]:
    """Find figure, table, and equation captions on a page."""

    # Patterns for figure/table captions: (regex, type_name)
    patterns = [
        (r"Figure\s+(\d+)[:\.]", "Figure"),
        (r"Fig\.\s*(\d+)[:\.]", "Figure"),
        (r"Table\s+(\d+)[:\.]", "Table"),
    ]

    captions = []
    blocks = page.get_text("dict")["blocks"]

    for block in blocks:
        if block.get("type") != 0:  # Skip non-text blocks
            continue

        for line in block.get("lines", []):
            # Combine spans to get full line text
            line_text = ""
            line_bbox = None

            for span in line.get("spans", []):
                text = span.get("text", "")
                line_text += text

                # Track the bounding box of the caption start
                for pattern, _ in patterns:
                    match = re.search(pattern, text)
                    if match:
                        line_bbox = span.get("bbox")
                        break

            # Check if this line contains a caption
            for pattern, fig_type in patterns:
                match = re.search(pattern, line_text)
                if match:
                    fig_num = match.group(1)

                    # Get full caption (may span multiple lines)
                    caption_text = line_text.strip()

                    if line_bbox:
                        captions.append(
                            FigureRegion(
                                number=f"{fig_type} {fig_num}",
                                caption=caption_text,
                                page_num=page_num,
                                bbox=None,  # Will be computed later
                                caption_bbox=line_bbox,
                            )
                        )
                    break

    return captions


def estimate_figure_region(
    page: fitz.Page,
    caption: FigureRegion,
    margin_left: float = 72,  # ~1 inch from left
    margin_right: float = 36,  # ~0.5 inch from right
    margin_top: float = 72,  # ~1 inch from page top
    padding_top: float = 35,  # Extra padding above figure content
) -> FigureRegion:
    """
    Estimate the figure region based on caption position.

    Technique: Caption-based region detection
    1. Find "Figure X:" or "Table X:" caption text
    2. Search upward for text blocks to find where figure starts
    3. The figure is the region between last text block and caption
    4. Render that region as a complete image (includes vectors)

    This works because scientific papers have consistent layouts:
    - Figures are placed between paragraphs
    - Captions are directly below figures
    - Column width is predictable
    """
    page_rect = page.rect
    caption_y = caption.caption_bbox[1]  # Top of caption

    # Get all blocks
    blocks = page.get_text("dict")["blocks"]
    text_blocks = [b for b in blocks if b.get("type") == 0]
    image_blocks = [b for b in blocks if b.get("type") == 1]

    # Strategy 1: Find image blocks that belong to this figure
    # (images above the caption but below any text that's clearly not part of figure)
    figure_images = [
        b
        for b in image_blocks
        if b["bbox"][3] < caption_y and b["bbox"][1] > 50  # Above caption, below header
    ]

    # Strategy 2: Find the text block just before the figure
    figure_top = margin_top  # Default: top margin

    # Sort text blocks by bottom position (descending) to find the one just above figure
    for block in sorted(text_blocks, key=lambda b: b["bbox"][3], reverse=True):
        block_bottom = block["bbox"][3]
        block_top = block["bbox"][1]
        block_text = ""
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                block_text += span.get("text", "")

        # Skip if this is the caption itself
        if caption.number in block_text:
            continue

        # Skip line number columns (narrow blocks on left margin)
        block_width = block["bbox"][2] - block["bbox"][0]
        if block_width < 50:  # Line numbers are narrow
            continue

        # Skip if block is below caption
        if block_bottom > caption_y:
            continue

        # Skip if block overlaps with figure images (it's a label inside figure)
        overlaps_image = False
        for img in figure_images:
            if block_top >= img["bbox"][1] and block_bottom <= img["bbox"][3]:
                overlaps_image = True
                break
        if overlaps_image:
            continue

        # If there's a text block well above the caption, figure starts after it
        if block_bottom < caption_y - 30:  # Reduced threshold for tighter detection
            figure_top = max(figure_top, block_bottom + 5)
            break

    # If we found image blocks, use their top as a hint
    if figure_images:
        min_image_top = min(b["bbox"][1] for b in figure_images)
        # Only use image hint if it's above our text-based detection
        if min_image_top < figure_top:
            figure_top = min_image_top - 5

    # Build the figure bounding box with padding
    bbox = (
        margin_left,
        max(margin_top - 20, figure_top - padding_top),  # Add top padding
        page_rect.width - margin_right,
        caption_y + 15,  # Include caption
    )

    return FigureRegion(
        number=caption.number,
        caption=caption.caption,
        page_num=caption.page_num,
        bbox=bbox,
        caption_bbox=caption.caption_bbox,
    )


def extract_figure_image(
    doc: fitz.Document,
    figure: FigureRegion,
    output_dir: Path,
    dpi: int = 200,
) -> Path:
    """Render a figure region to an image file."""

    page = doc[figure.page_num]

    # Create clip rectangle
    clip = fitz.Rect(figure.bbox)

    # Render at specified DPI
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, clip=clip)

    # Generate filename
    safe_name = figure.number.lower().replace(" ", "_").replace(".", "")
    filename = f"p{figure.page_num + 1:03d}_{safe_name}.png"
    output_path = output_dir / filename

    pix.save(str(output_path))

    return output_path


def extract_figures_from_pdf(
    pdf_path: Path,
    output_dir: Path,
    pages: list[int] | None = None,
    dpi: int = 200,
) -> list[dict]:
    """Extract all figures from a PDF."""

    doc = fitz.open(pdf_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    # Determine which pages to process
    if pages is None:
        page_range = range(len(doc))
    else:
        page_range = [p - 1 for p in pages if 0 < p <= len(doc)]

    for page_num in page_range:
        page = doc[page_num]

        # Find captions
        captions = find_captions(page, page_num)

        for caption in captions:
            # Estimate figure region
            figure = estimate_figure_region(page, caption)

            # Extract image
            try:
                output_path = extract_figure_image(doc, figure, output_dir, dpi)

                results.append(
                    {
                        "number": figure.number,
                        "caption": figure.caption,
                        "page": page_num + 1,
                        "bbox": figure.bbox,
                        "image_path": str(output_path),
                        "success": True,
                    }
                )

                print(
                    f"Extracted {figure.number} from page {page_num + 1}",
                    file=sys.stderr,
                )

            except Exception as e:
                results.append(
                    {
                        "number": figure.number,
                        "caption": figure.caption,
                        "page": page_num + 1,
                        "error": str(e),
                        "success": False,
                    }
                )
                print(f"Error extracting {figure.number}: {e}", file=sys.stderr)

    doc.close()
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Extract complete figures from PDFs using caption detection"
    )
    parser.add_argument("pdf_path", type=Path, help="Path to PDF file")
    parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Pages to process (comma-separated, e.g., '1,2,5'). Default: all",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("figures"),
        help="Output directory for extracted figures",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="DPI for rendered images (default: 200)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Output JSON file with extraction results",
    )

    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"Error: File not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Parse pages
    pages = None
    if args.pages:
        pages = [int(p.strip()) for p in args.pages.split(",")]

    print(f"Extracting figures from: {args.pdf_path}", file=sys.stderr)
    print(f"Output directory: {args.output_dir}", file=sys.stderr)

    results = extract_figures_from_pdf(
        args.pdf_path,
        args.output_dir,
        pages=pages,
        dpi=args.dpi,
    )

    # Print summary
    success = sum(1 for r in results if r.get("success"))
    print(f"\nExtracted {success}/{len(results)} figures", file=sys.stderr)

    # Output JSON
    if args.output_json:
        args.output_json.write_text(json.dumps(results, indent=2))
        print(f"Results written to: {args.output_json}", file=sys.stderr)
    else:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
