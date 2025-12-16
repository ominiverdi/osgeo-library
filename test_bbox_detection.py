#!/usr/bin/env python3
"""
Test VL model for bounding box detection of figures, tables, and equations.
Uses the local llama.cpp server with Qwen3-VL-8B.
"""

import requests
import base64
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

LLAMA_SERVER = "http://localhost:8090"  # Qwen3-VL-8B


def encode_image(image_path: str) -> str:
    """Encode image to base64."""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def convert_coords_to_pixels(elements: list, width: int, height: int) -> list:
    """
    Convert Qwen3-VL 0-1000 relative coordinates to pixel coordinates.

    Qwen3-VL outputs bounding boxes in a normalized 0-1000 scale.
    Formula: abs_coord = int(rel_coord / 1000 * dimension)
    """
    if not isinstance(elements, list):
        return elements

    converted = []
    for elem in elements:
        if not isinstance(elem, dict):
            converted.append(elem)
            continue

        bbox = elem.get("bbox_2d") or elem.get("bbox")
        if bbox and len(bbox) == 4:
            # Check if coordinates are in 0-1000 range (relative)
            # vs already in pixel range
            max_coord = max(bbox)
            if max_coord <= 1000:
                # Convert from 0-1000 to pixels
                x1 = int(bbox[0] / 1000 * width)
                y1 = int(bbox[1] / 1000 * height)
                x2 = int(bbox[2] / 1000 * width)
                y2 = int(bbox[3] / 1000 * height)
                elem = elem.copy()
                elem["bbox_2d"] = [x1, y1, x2, y2]
                elem["bbox_2d_original"] = bbox  # Keep original for reference

        converted.append(elem)

    return converted


def detect_layout_elements(image_path: str) -> list | dict:
    """
    Ask VL model to detect figures, tables, and equations with bounding boxes.
    Returns JSON with element locations.

    Qwen3-VL uses a 0-1000 relative coordinate system for grounding.
    We convert these to pixel coordinates after receiving the response.
    """

    # Encode image
    image_data = encode_image(image_path)

    # Determine image type
    suffix = Path(image_path).suffix.lower()
    media_type = "image/png" if suffix == ".png" else "image/jpeg"

    # Get image dimensions for coordinate conversion
    img = Image.open(image_path)
    width, height = img.size

    # Simplified prompt - Qwen3-VL is trained for grounding tasks
    # It outputs coordinates in 0-1000 relative scale by default
    prompt = """Detect all figures, tables, and diagrams in this scientific paper page.

For each element found, output in this JSON format:
[
  {"bbox_2d": [x1, y1, x2, y2], "label": "Figure 1"},
  {"bbox_2d": [x1, y1, x2, y2], "label": "Table 1"}
]

Coordinates should be in 0-1000 scale where (0,0) is top-left and (1000,1000) is bottom-right.
Return only the JSON array. If no visual elements found, return: []
"""

    # Build request for llama.cpp server
    payload = {
        "model": "qwen3-vl-8b",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_data}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": 2048,
        "temperature": 0.1,  # Low temp for structured output
    }

    print(f"Sending request to {LLAMA_SERVER}/v1/chat/completions...")
    print(f"Image: {image_path}")

    try:
        response = requests.post(
            f"{LLAMA_SERVER}/v1/chat/completions",
            json=payload,
            timeout=300,  # 5 min timeout
        )
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        print("\n--- Raw Response ---")
        print(content)
        print("--- End Response ---\n")

        # Try to parse JSON from response
        # Handle potential markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        # Remove JavaScript-style comments that break JSON parsing
        import re

        content = re.sub(r"//.*?$", "", content, flags=re.MULTILINE)
        content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

        try:
            parsed = json.loads(content.strip())
            # Convert 0-1000 coordinates to pixel coordinates
            parsed = convert_coords_to_pixels(parsed, width, height)
            return parsed
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")
            return {"raw_response": content, "error": str(e)}

    except requests.exceptions.Timeout:
        return {"error": "Request timed out after 300s"}
    except Exception as e:
        return {"error": str(e)}


def main():
    # Test with SAM3 paper page 1 (has Figure 1)
    test_images = [
        "web/data/page_001.png",
        "web/data/page_002.png",
        "web/data/page_003.png",
    ]

    # Use command line arg or default
    if len(sys.argv) > 1:
        test_images = [sys.argv[1]]

    for image_path in test_images:
        if not Path(image_path).exists():
            print(f"Image not found: {image_path}")
            continue

        print(f"\n{'=' * 60}")
        print(f"Testing: {image_path}")
        print("=" * 60)

        result = detect_layout_elements(image_path)

        print("\n--- Parsed Result ---")
        print(json.dumps(result, indent=2))

        # If we got elements, show them and visualize
        # Handle both old format {"elements": [...]} and new format [...]
        elements = (
            result.get("elements", result) if isinstance(result, dict) else result
        )
        if isinstance(elements, list) and elements:
            print(f"\nFound {len(elements)} elements:")
            for elem in elements:
                label = elem.get("label", "N/A")
                bbox = elem.get("bbox_2d") or elem.get("bbox", "N/A")
                elem_type = elem.get("type", "figure")
                print(f"  - {elem_type}: {label}")
                print(f"    bbox: {bbox}")

            # Convert to old format for visualization
            viz_result = {
                "elements": [
                    {
                        "type": e.get("type", "figure"),
                        "label": e.get("label"),
                        "bbox": e.get("bbox_2d") or e.get("bbox"),
                    }
                    for e in elements
                ]
            }

            # Save visualization
            out_path = f"web/data/{Path(image_path).stem}_bbox.png"
            visualize_bboxes(image_path, viz_result, out_path)

        print()


def visualize_bboxes(image_path: str, result: dict, output_path: str = ""):
    """Draw bounding boxes on image and save."""
    if "elements" not in result or not result["elements"]:
        print("No elements to visualize")
        return ""

    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # Colors for different element types
    colors = {"figure": "red", "table": "blue", "equation": "green"}

    for elem in result["elements"]:
        bbox = elem.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        elem_type = elem.get("type", "unknown")
        label = elem.get("label", elem_type)
        color = colors.get(elem_type, "yellow")

        # Draw rectangle
        x1, y1, x2, y2 = bbox
        draw.rectangle(((x1, y1), (x2, y2)), outline=color, width=3)

        # Draw label
        draw.text((x1 + 5, y1 + 5), label, fill=color)

    # Save or show
    if not output_path:
        output_path = str(Path(image_path).stem) + "_bbox.png"

    img.save(output_path)
    print(f"Saved visualization to: {output_path}")
    return output_path


if __name__ == "__main__":
    main()
