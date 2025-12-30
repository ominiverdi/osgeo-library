"""Display utilities for chat CLI (terminal preview and GUI viewers)."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Union

from doclibrary.config import config


def has_display() -> bool:
    """Check if graphical display (X11 or Wayland) is available."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def show_image(
    path: Union[str, Path],
    size: Optional[str] = None,
    base_dir: Optional[Union[str, Path]] = None,
) -> bool:
    """Display image using chafa terminal preview.

    Args:
        path: Path to image file (can be relative)
        size: Display size (e.g., "80x35"). If None, uses config default.
        base_dir: Base directory for relative paths

    Returns:
        True if displayed successfully
    """
    path = str(path)

    if not path:
        print("No image path available.")
        return False

    # Resolve relative path
    if not os.path.isabs(path):
        if base_dir:
            path = os.path.join(str(base_dir), path)
        else:
            path = os.path.join(os.getcwd(), path)

    if not os.path.exists(path):
        print(f"Image not found: {path}")
        return False

    # Use provided size or default from config
    display_size = size or config.chafa_size

    # Check for chafa
    if shutil.which("chafa"):
        try:
            subprocess.run(["chafa", path, "--size", display_size], check=True)
            print(f"\nPath: {path}")
            if has_display():
                print("(Use 'open N' to view in GUI)")
            return True
        except subprocess.CalledProcessError:
            pass

    # Fallback: no chafa available
    print(f"Image: {path}")
    print("(Install chafa for terminal preview: sudo apt install chafa)")
    if has_display():
        print("(Use 'open N' to view in GUI)")
    return True


def open_in_viewer(path: Union[str, Path], base_dir: Optional[Union[str, Path]] = None) -> bool:
    """Open image in system GUI viewer.

    Args:
        path: Path to image file
        base_dir: Base directory for relative paths

    Returns:
        True if opened successfully
    """
    path = str(path)

    if not path:
        print("No image path available.")
        return False

    # Resolve relative path
    if not os.path.isabs(path):
        if base_dir:
            path = os.path.join(str(base_dir), path)
        else:
            path = os.path.join(os.getcwd(), path)

    if not os.path.exists(path):
        print(f"Image not found: {path}")
        return False

    if not has_display():
        print("No display available (X11/Wayland not detected)")
        print("Use 'show N' for terminal preview instead")
        return False

    # Try xdg-open first (works on most Linux systems)
    if shutil.which("xdg-open"):
        subprocess.Popen(
            ["xdg-open", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"Opened: {path}")
        return True

    # Fallback to common image viewers
    viewers = ["feh", "eog", "gwenview", "sxiv", "imv"]
    for viewer in viewers:
        if shutil.which(viewer):
            subprocess.Popen(
                [viewer, path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"Opened with {viewer}: {path}")
            return True

    print("No image viewer found")
    print("Install one of: xdg-utils, feh, eog, gwenview, sxiv, imv")
    return False


def get_element_image_path(
    result,
    element_data: Optional[dict] = None,
    data_dir: Optional[str] = None,
) -> str:
    """Get the full path to an element's image.

    For equations, prefers rendered LaTeX image over crop.

    Args:
        result: SearchResult object
        element_data: Full element data from database (optional)
        data_dir: Data directory path

    Returns:
        Full path to the image file
    """
    if data_dir is None:
        data_dir = config.data_dir

    doc_slug = result.document_slug

    # For equations, prefer rendered image (cleaner LaTeX rendering)
    if result.element_type == "equation":
        if element_data and element_data.get("rendered_path"):
            image_path = element_data["rendered_path"]
        else:
            image_path = result.crop_path
    else:
        image_path = result.crop_path

    return os.path.join(data_dir, doc_slug, image_path) if image_path else ""


def get_display_size_for_element(element_type: Optional[str]) -> str:
    """Get the appropriate display size for an element type.

    Args:
        element_type: Type of element (equation, table, figure, etc.)

    Returns:
        Chafa size string
    """
    if element_type == "equation":
        return config.chafa_size_equation
    elif element_type == "table":
        return config.chafa_size_table
    else:
        return config.chafa_size
