"""Image processing utilities for doclibrary."""

from pathlib import Path
from typing import List, Optional, Tuple, Union

from PIL import Image, ImageDraw

from .constants import ANNOTATION_COLORS


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color string to RGB tuple.

    Args:
        hex_color: Color like "#FF6B6B"

    Returns:
        RGB tuple like (255, 107, 107)
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b)


def get_element_color(element_type: str) -> str:
    """Get annotation color for element type.

    Args:
        element_type: Type like "figure", "table", "equation"

    Returns:
        Hex color string
    """
    return ANNOTATION_COLORS.get(element_type, ANNOTATION_COLORS["default"])


def create_annotated_image(
    image: Image.Image,
    elements: List[dict],
    line_width: int = 3,
) -> Image.Image:
    """Draw bounding boxes on page image.

    Args:
        image: PIL Image of the page
        elements: List of element dicts with 'type' and 'bbox' keys
                  bbox can be in 0-1000 scale or pixel coordinates
        line_width: Width of bounding box lines

    Returns:
        New PIL Image with annotations drawn
    """
    # Work on a copy
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)

    width, height = image.size

    for element in elements:
        element_type = element.get("type", "default")
        bbox = element.get("bbox")

        if not bbox or len(bbox) != 4:
            continue

        # Check if bbox is in 0-1000 scale (Qwen-VL format) or pixels
        if all(0 <= coord <= 1000 for coord in bbox):
            # Convert from 0-1000 scale to pixels
            x1 = int(bbox[0] * width / 1000)
            y1 = int(bbox[1] * height / 1000)
            x2 = int(bbox[2] * width / 1000)
            y2 = int(bbox[3] * height / 1000)
        else:
            x1, y1, x2, y2 = [int(c) for c in bbox]

        # Get color for element type
        color = get_element_color(element_type)

        # Draw rectangle
        draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)

        # Optionally draw label
        label = element.get("label", "")
        if label:
            # Draw label background
            text_bbox = draw.textbbox((x1, y1 - 20), label)
            draw.rectangle(text_bbox, fill=color)
            draw.text((x1, y1 - 20), label, fill="white")

    return annotated


def crop_element(
    image: Image.Image,
    bbox: Tuple[float, float, float, float],
    padding: int = 5,
    scale: int = 1000,
) -> Optional[Image.Image]:
    """Crop element from page image using bounding box.

    Args:
        image: PIL Image of the page
        bbox: Bounding box as (x1, y1, x2, y2)
        padding: Extra pixels to add around the crop
        scale: Coordinate scale (1000 for Qwen-VL, or image dimensions for pixels)

    Returns:
        Cropped PIL Image, or None if invalid bbox
    """
    if not bbox or len(bbox) != 4:
        return None

    width, height = image.size

    # Convert bbox coordinates
    if scale == 1000:
        x1 = int(bbox[0] * width / 1000)
        y1 = int(bbox[1] * height / 1000)
        x2 = int(bbox[2] * width / 1000)
        y2 = int(bbox[3] * height / 1000)
    else:
        x1, y1, x2, y2 = [int(c) for c in bbox]

    # Validate coordinates
    if x2 <= x1 or y2 <= y1:
        return None

    # Add padding
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(width, x2 + padding)
    y2 = min(height, y2 + padding)

    return image.crop((x1, y1, x2, y2))


def render_latex_to_image(
    latex: str,
    output_path: Union[str, Path],
    dpi: int = 200,
) -> bool:
    """Render LaTeX string to PNG image using pdflatex + ImageMagick.

    Requires system packages: texlive-latex-base, imagemagick

    Args:
        latex: LaTeX string to render
        output_path: Path to save the PNG image
        dpi: Resolution for rendering

    Returns:
        True if successful, False otherwise
    """
    import shutil
    import subprocess
    import tempfile

    if not latex:
        return False

    # Clean up the LaTeX
    latex = latex.strip()
    latex = latex.replace(r"\(", "").replace(r"\)", "")
    latex = latex.strip("$")

    # Determine if we need align environment
    needs_align = r"\begin{align" in latex or "&" in latex
    needs_cases = r"\begin{cases}" in latex

    # Build LaTeX document
    if needs_align or needs_cases:
        if not latex.startswith(r"\begin{"):
            math_content = f"\\begin{{align*}}\n{latex}\n\\end{{align*}}"
        else:
            math_content = latex
        doc = f"""\\documentclass[preview,border=2pt]{{standalone}}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\begin{{document}}
{math_content}
\\end{{document}}
"""
    else:
        doc = f"""\\documentclass[preview,border=2pt]{{standalone}}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\begin{{document}}
$\\displaystyle {latex}$
\\end{{document}}
"""

    # Create temp directory for LaTeX compilation
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "equation.tex"
        pdf_path = Path(tmpdir) / "equation.pdf"

        # Write LaTeX file
        tex_path.write_text(doc)

        # Compile to PDF
        try:
            subprocess.run(
                [
                    "pdflatex",
                    "-interaction=nonstopmode",
                    "-output-directory",
                    tmpdir,
                    str(tex_path),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return False

        if not pdf_path.exists():
            return False

        # Convert PDF to PNG
        try:
            subprocess.run(
                [
                    "convert",
                    "-density",
                    str(dpi),
                    str(pdf_path),
                    "-quality",
                    "100",
                    "-background",
                    "white",
                    "-alpha",
                    "remove",
                    str(output_path),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return False

        return Path(output_path).exists()
