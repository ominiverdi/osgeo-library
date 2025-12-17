#!/usr/bin/env python3
"""
Draw bounding boxes on images based on Claude's detections.
Uses same colors as Qwen annotations for fair comparison.
"""

import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw

# Same colors as extract_document.py
COLORS = {
    "figure": "red",
    "table": "blue",
    "diagram": "green",
    "chart": "orange",
    "equation": "purple",
}


def annotate_image(image_path: Path, elements: list, output_path: Path):
    """Draw bounding boxes on image and save."""
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    width, height = img.size

    for elem in elements:
        bbox = elem.get("bbox_1000", [])
        if len(bbox) != 4:
            continue

        # Convert 0-1000 scale to pixels
        x1 = int(bbox[0] / 1000 * width)
        y1 = int(bbox[1] / 1000 * height)
        x2 = int(bbox[2] / 1000 * width)
        y2 = int(bbox[3] / 1000 * height)

        elem_type = elem.get("type", "unknown")
        color = COLORS.get(elem_type, "yellow")

        draw.rectangle(((x1, y1), (x2, y2)), outline=color, width=3)
        label = elem.get("label", elem_type)[:30]
        draw.text((x1 + 5, y1 + 5), label, fill=color)

    img.save(str(output_path))
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: python annotate_claude.py <image_path> <output_path> '<json_elements>'"
        )
        sys.exit(1)

    image_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    elements = json.loads(sys.argv[3])

    annotate_image(image_path, elements, output_path)
    print(f"Created: {output_path}")
