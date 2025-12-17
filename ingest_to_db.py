#!/usr/bin/env python3
"""
Ingest extracted documents into PostgreSQL database.

Reads from db/data/{document}/ structure and inserts:
- Document metadata
- Pages with text
- Text chunks with embeddings
- Elements (figures, tables, equations) with embeddings

Usage:
    python ingest_to_db.py sam3                    # Ingest one document
    python ingest_to_db.py --all                   # Ingest all documents
    python ingest_to_db.py sam3 --dry-run          # Preview without changes
    python ingest_to_db.py sam3 --skip-existing    # Skip already ingested
    python ingest_to_db.py sam3 --delete-first     # Re-ingest (delete then insert)
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# Local imports
from db.connection import (
    get_document_by_slug,
    delete_document,
    insert_document,
    insert_page,
    insert_chunk,
    insert_element,
)
from db.chunking import chunk_text, clean_text_for_chunking, Chunk
from embeddings.embed import get_embeddings, check_server

DB_DATA_DIR = Path("db/data")

# Chunking settings
CHUNK_SIZE = 800  # ~200 tokens
CHUNK_OVERLAP = 200  # ~50 tokens


def clean_slug_to_title(slug: str) -> str:
    """Convert slug to human-readable title."""
    # Remove common suffixes
    title = re.sub(r"[-_]?(v\d+|\d{4}v\d+)$", "", slug)
    # Replace underscores/hyphens with spaces
    title = title.replace("_", " ").replace("-", " ")
    # Title case
    title = title.title()
    return title


def parse_latex_from_description(description: str) -> str | None:
    """Extract LaTeX from equation description."""
    if not description:
        return None

    # Pattern: "LaTeX: ..." or "LaTeX:\n..."
    match = re.search(r"LaTeX:\s*(.+)", description, re.DOTALL)
    if match:
        latex = match.group(1).strip()
        # Remove surrounding \( \) or $ $ if present
        latex = re.sub(r"^\\?\((.+)\\?\)$", r"\1", latex, flags=re.DOTALL)
        latex = re.sub(r"^\$(.+)\$$", r"\1", latex, flags=re.DOTALL)
        return latex.strip()

    return None


def load_document_data(doc_path: Path) -> Dict[str, Any]:
    """Load document.json and all page JSON files."""
    doc_file = doc_path / "document.json"
    if not doc_file.exists():
        raise FileNotFoundError(f"No document.json in {doc_path}")

    with open(doc_file) as f:
        doc_data = json.load(f)

    # Load all pages
    pages_dir = doc_path / "pages"
    pages = []

    if pages_dir.exists():
        for page_file in sorted(pages_dir.glob("page_*.json")):
            with open(page_file) as f:
                pages.append(json.load(f))

    doc_data["pages"] = pages
    return doc_data


def ingest_document(
    doc_name: str,
    dry_run: bool = False,
    skip_existing: bool = False,
    delete_first: bool = False,
    embed_content: bool = True,
) -> bool:
    """
    Ingest a single document into the database.

    Args:
        doc_name: Document name (slug)
        dry_run: Preview without making changes
        skip_existing: Skip if document already in DB
        delete_first: Delete existing document before ingesting
        embed_content: Generate embeddings (requires embedding server)

    Returns:
        True if successful, False otherwise
    """
    doc_path = DB_DATA_DIR / doc_name
    if not doc_path.exists():
        print(f"ERROR: Document not found: {doc_path}")
        return False

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Ingesting {doc_name}...")

    # Check if already exists
    existing = get_document_by_slug(doc_name)
    if existing:
        if skip_existing:
            print(f"  Skipping (already exists, id={existing['id']})")
            return True
        elif delete_first:
            if not dry_run:
                print(f"  Deleting existing document (id={existing['id']})...")
                delete_document(existing["id"])
        else:
            print(f"  ERROR: Document already exists (id={existing['id']})")
            print(f"  Use --delete-first to replace or --skip-existing to skip")
            return False

    # Load document data
    try:
        doc_data = load_document_data(doc_path)
    except Exception as e:
        print(f"  ERROR loading document: {e}")
        return False

    pages = doc_data.get("pages", [])
    title = clean_slug_to_title(doc_name)

    print(f"  Title: {title}")
    print(f"  Pages: {len(pages)}")

    if dry_run:
        # Count elements and chunks for preview
        total_elements = sum(len(p.get("elements", [])) for p in pages)
        total_chunks = 0
        for page in pages:
            text = clean_text_for_chunking(page.get("text", ""))
            chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
            total_chunks += len(chunks)

        print(f"  Elements: {total_elements}")
        print(f"  Chunks: {total_chunks}")
        print(f"  [DRY RUN] Would insert document, pages, chunks, and elements")
        return True

    # Check embedding server if needed
    if embed_content and not check_server():
        print("  WARNING: Embedding server not available - skipping embeddings")
        embed_content = False

    start_time = time.time()

    # Insert document
    doc_id = insert_document(
        slug=doc_name,
        title=title,
        source_file=doc_data.get("source_file", f"{doc_name}.pdf"),
        extraction_date=doc_data.get("extraction_date", ""),
        model=doc_data.get("model", "unknown"),
        metadata=doc_data.get("metadata", {}),
    )
    print(f"  Inserted document (id={doc_id})")

    # Process pages
    total_chunks = 0
    total_elements = 0

    for page in pages:
        page_num = page.get("page_number", 0)

        # Insert page
        page_id = insert_page(
            document_id=doc_id,
            page_number=page_num,
            image_path=page.get("image", ""),
            annotated_image_path=page.get("annotated_image", ""),
            full_text=page.get("text", ""),
            width=page.get("width", 0),
            height=page.get("height", 0),
        )

        # Chunk and insert text
        text = clean_text_for_chunking(page.get("text", ""))
        if text:
            chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)

            # Batch embed chunks
            chunk_contents = [c.content for c in chunks]
            embeddings = None
            if embed_content and chunk_contents:
                embeddings = get_embeddings(chunk_contents)

            for i, chunk in enumerate(chunks):
                emb = embeddings[i] if embeddings and i < len(embeddings) else None
                insert_chunk(
                    document_id=doc_id,
                    page_id=page_id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    start_char=chunk.start_char,
                    end_char=chunk.end_char,
                    embedding=emb,
                )
                total_chunks += 1

        # Insert elements
        for element in page.get("elements", []):
            elem_type = element.get("type", "unknown")
            description = element.get("description", "")
            search_text = element.get("search_text", description)

            # Parse LaTeX for equations
            latex = None
            if elem_type == "equation":
                latex = parse_latex_from_description(description)

            # Embed search_text
            embedding = None
            if embed_content and search_text:
                emb_result = get_embeddings([search_text])
                if emb_result:
                    embedding = emb_result[0]

            insert_element(
                document_id=doc_id,
                page_id=page_id,
                element_type=elem_type,
                label=element.get("label", ""),
                description=description,
                search_text=search_text,
                latex=latex,
                crop_path=element.get("crop_path", ""),
                rendered_path=element.get("rendered_path", ""),
                bbox_pixels=element.get("bbox_pixels"),
                embedding=embedding,
            )
            total_elements += 1

        # Progress indicator
        print(
            f"    Page {page_num}: {len(chunks) if text else 0} chunks, "
            f"{len(page.get('elements', []))} elements"
        )

    elapsed = time.time() - start_time
    print(
        f"  Completed: {total_chunks} chunks, {total_elements} elements ({elapsed:.1f}s)"
    )

    return True


def list_documents() -> List[Dict[str, Any]]:
    """List available documents and their ingestion status."""
    from db.connection import fetch_all

    # Get documents in db/data
    docs = []
    if DB_DATA_DIR.exists():
        for item in DB_DATA_DIR.iterdir():
            if item.is_dir() and (item / "document.json").exists():
                doc_name = item.name

                # Check if in database
                db_doc = get_document_by_slug(doc_name)

                # Count pages/elements in extraction
                pages_dir = item / "pages"
                page_count = (
                    len(list(pages_dir.glob("page_*.json")))
                    if pages_dir.exists()
                    else 0
                )

                docs.append(
                    {
                        "name": doc_name,
                        "pages": page_count,
                        "in_db": db_doc is not None,
                        "db_id": db_doc["id"] if db_doc else None,
                    }
                )

    return docs


def main():
    parser = argparse.ArgumentParser(
        description="Ingest extracted documents into PostgreSQL"
    )
    parser.add_argument("document", nargs="?", help="Document name to ingest")
    parser.add_argument("--all", action="store_true", help="Ingest all documents")
    parser.add_argument("--list", action="store_true", help="List available documents")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without changes"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip documents already in database",
    )
    parser.add_argument(
        "--delete-first",
        action="store_true",
        help="Delete existing document before re-ingesting",
    )
    parser.add_argument(
        "--no-embed", action="store_true", help="Skip embedding generation"
    )

    args = parser.parse_args()

    if args.list:
        docs = list_documents()
        if docs:
            print("\nDocument Ingestion Status")
            print("=" * 70)
            for doc in sorted(docs, key=lambda x: x["name"]):
                status = (
                    f"[in DB, id={doc['db_id']}]" if doc["in_db"] else "[not ingested]"
                )
                print(f"  {doc['name']:30} {doc['pages']:3} pages  {status}")
        else:
            print("No documents found in db/data/")
        return

    embed_content = not args.no_embed

    if args.all:
        docs = list_documents()
        success_count = 0
        for doc in docs:
            if ingest_document(
                doc["name"],
                dry_run=args.dry_run,
                skip_existing=args.skip_existing,
                delete_first=args.delete_first,
                embed_content=embed_content,
            ):
                success_count += 1
        print(f"\nIngested {success_count}/{len(docs)} documents")

    elif args.document:
        ingest_document(
            args.document,
            dry_run=args.dry_run,
            skip_existing=args.skip_existing,
            delete_first=args.delete_first,
            embed_content=embed_content,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
