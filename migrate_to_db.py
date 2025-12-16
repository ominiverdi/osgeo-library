#!/usr/bin/env python3
"""
Migrate existing extractions from web/data/ to db/data/ structure.

Converts monolithic extraction.json into per-page JSON files while
preserving all original data.

Structure created:
    db/data/{document}/
        document.json           # Document-level metadata
        pages/
            page_001.json       # Per-page: text, elements, timing
            page_002.json
            ...
        images/
            page_001.png        # Original page render
            page_001_annotated.png
            ...
        elements/
            p01_figure_1_*.png  # Cropped elements
            ...

Usage:
    python migrate_to_db.py                    # Migrate all documents
    python migrate_to_db.py --doc sam3         # Migrate specific document
    python migrate_to_db.py --dry-run          # Preview without copying
"""

import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime


SOURCE_DIR = Path("web/data")
TARGET_DIR = Path("db/data")


def migrate_document(doc_name: str, dry_run: bool = False) -> dict:
    """Migrate a single document from web/data to db/data structure.

    Returns summary dict with counts.
    """
    source_path = SOURCE_DIR / doc_name
    target_path = TARGET_DIR / doc_name

    extraction_file = source_path / "extraction.json"
    if not extraction_file.exists():
        print(f"  [ERROR] No extraction.json found in {source_path}")
        return {"error": True}

    # Load original extraction
    with open(extraction_file) as f:
        extraction = json.load(f)

    print(f"  Source: {source_path}")
    print(f"  Target: {target_path}")
    print(f"  Pages in extraction: {len(extraction.get('pages', []))}")

    if dry_run:
        print("  [DRY RUN] Would create directories and copy files")
        return {
            "pages": len(extraction.get("pages", [])),
            "elements": sum(
                len(p.get("elements", [])) for p in extraction.get("pages", [])
            ),
            "dry_run": True,
        }

    # Create target directories
    (target_path / "pages").mkdir(parents=True, exist_ok=True)
    (target_path / "images").mkdir(parents=True, exist_ok=True)
    (target_path / "elements").mkdir(parents=True, exist_ok=True)

    # Write document.json with all document-level metadata
    doc_metadata = {
        "document": extraction.get("document"),
        "source_file": extraction.get("source_file"),
        "extraction_date": extraction.get("extraction_date"),
        "model": extraction.get("model"),
        "timing": extraction.get("timing", {}),
        "migrated_date": datetime.now().isoformat(),
        "original_extraction_path": str(extraction_file),
    }

    doc_json_path = target_path / "document.json"
    with open(doc_json_path, "w") as f:
        json.dump(doc_metadata, f, indent=2, ensure_ascii=False)
    print(f"  Created: {doc_json_path}")

    # Process each page
    pages_migrated = 0
    elements_migrated = 0
    images_copied = 0

    for page in extraction.get("pages", []):
        page_num = page["page_number"]

        # Copy page image
        src_image = page.get("image")
        if src_image:
            src_image_path = source_path / src_image
            # Normalize to 3-digit naming
            dst_image_name = f"page_{page_num:03d}.png"
            dst_image_path = target_path / "images" / dst_image_name
            if src_image_path.exists():
                shutil.copy2(src_image_path, dst_image_path)
                images_copied += 1
            page["image"] = f"images/{dst_image_name}"

        # Copy annotated image
        src_annotated = page.get("annotated_image")
        if src_annotated:
            src_annotated_path = source_path / src_annotated
            dst_annotated_name = f"page_{page_num:03d}_annotated.png"
            dst_annotated_path = target_path / "images" / dst_annotated_name
            if src_annotated_path.exists():
                shutil.copy2(src_annotated_path, dst_annotated_path)
                images_copied += 1
            page["annotated_image"] = f"images/{dst_annotated_name}"

        # Process elements
        for elem in page.get("elements", []):
            # Copy element crop
            crop_path = elem.get("crop_path")
            if crop_path:
                src_crop = source_path / crop_path
                dst_crop = target_path / crop_path  # Keep same relative path
                if src_crop.exists():
                    shutil.copy2(src_crop, dst_crop)
                    elements_migrated += 1

            # Copy rendered LaTeX if exists
            rendered_path = elem.get("rendered_path")
            if rendered_path:
                src_rendered = source_path / rendered_path
                dst_rendered = target_path / rendered_path
                if src_rendered.exists():
                    shutil.copy2(src_rendered, dst_rendered)

        # Write page JSON (contains all original fields)
        page_json_path = target_path / "pages" / f"page_{page_num:03d}.json"
        with open(page_json_path, "w") as f:
            json.dump(page, f, indent=2, ensure_ascii=False)

        pages_migrated += 1

    print(
        f"  Migrated: {pages_migrated} pages, {elements_migrated} elements, {images_copied} images"
    )

    return {
        "pages": pages_migrated,
        "elements": elements_migrated,
        "images": images_copied,
    }


def list_documents() -> list:
    """List all documents in web/data/."""
    if not SOURCE_DIR.exists():
        return []
    return [
        d.name
        for d in SOURCE_DIR.iterdir()
        if d.is_dir() and (d / "extraction.json").exists()
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Migrate extractions to db/data structure"
    )
    parser.add_argument("--doc", type=str, help="Migrate specific document only")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without making changes"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Migration: web/data/ -> db/data/")
    print("=" * 60)

    if args.doc:
        docs = [args.doc]
    else:
        docs = list_documents()

    if not docs:
        print("No documents found in web/data/")
        return

    print(f"Documents to migrate: {docs}")
    if args.dry_run:
        print("[DRY RUN MODE]")
    print()

    total_pages = 0
    total_elements = 0

    for doc in docs:
        print(f"\nMigrating: {doc}")
        print("-" * 40)
        result = migrate_document(doc, dry_run=args.dry_run)
        if not result.get("error"):
            total_pages += result.get("pages", 0)
            total_elements += result.get("elements", 0)

    print()
    print("=" * 60)
    print(f"Total: {total_pages} pages, {total_elements} elements")
    print("=" * 60)

    # Show what's in db/data now
    if not args.dry_run and TARGET_DIR.exists():
        print("\nCreated structure:")
        for doc_dir in sorted(TARGET_DIR.iterdir()):
            if doc_dir.is_dir():
                pages_count = (
                    len(list((doc_dir / "pages").glob("*.json")))
                    if (doc_dir / "pages").exists()
                    else 0
                )
                images_count = (
                    len(list((doc_dir / "images").glob("*.png")))
                    if (doc_dir / "images").exists()
                    else 0
                )
                elements_count = (
                    len(list((doc_dir / "elements").glob("*.png")))
                    if (doc_dir / "elements").exists()
                    else 0
                )
                print(f"  {doc_dir.name}/")
                print(f"    pages/    {pages_count} JSON files")
                print(f"    images/   {images_count} PNG files")
                print(f"    elements/ {elements_count} PNG files")


if __name__ == "__main__":
    main()
