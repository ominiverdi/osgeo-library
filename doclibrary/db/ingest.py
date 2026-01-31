#!/usr/bin/env python3
"""
Ingest extracted documents into PostgreSQL database.

Reads from data_dir/{document}/ structure and inserts:
- Document metadata
- Pages with text
- Text chunks with embeddings
- Elements (figures, tables, equations) with embeddings

Usage:
    from doclibrary.db.ingest import ingest_document, list_available_documents

    # Ingest one document
    ingest_document("sam3")

    # List all available documents
    docs = list_available_documents()
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from doclibrary.config import config
from doclibrary.db.chunking import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    chunk_text,
    clean_text_for_chunking,
)
from doclibrary.db.connection import (
    delete_document,
    get_document_by_slug,
    get_document_by_source_file,
    insert_chunk,
    insert_document,
    insert_element,
    insert_page,
)
from doclibrary.search.embeddings import check_server as check_embed_server
from doclibrary.search.embeddings import get_embeddings

# Batch size for embedding requests to avoid timeouts on large pages
EMBED_BATCH_SIZE = 50


def get_embeddings_batched(texts: List[str], verbose: bool = False) -> List[Optional[List[float]]]:
    """Get embeddings in batches to avoid timeouts on large requests."""
    if not texts:
        return []

    total = len(texts)
    all_embeddings = []
    for i in range(0, total, EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        if verbose and total > EMBED_BATCH_SIZE:
            print(f"      Embedding {i + 1}-{min(i + len(batch), total)} of {total}...")
        batch_embeddings = get_embeddings(batch)
        if batch_embeddings:
            all_embeddings.extend(batch_embeddings)
        else:
            # Fill with None if batch failed
            all_embeddings.extend([None] * len(batch))

    return all_embeddings


def get_data_dir() -> Path:
    """Get the data directory path."""
    return Path(config.data_dir)


def clean_slug_to_title(slug: str) -> str:
    """Convert slug to human-readable title."""
    # Remove common suffixes like version numbers
    title = re.sub(r"[-_]?(v\d+|\d{4}v\d+)$", "", slug)
    # Replace underscores/hyphens with spaces
    title = title.replace("_", " ").replace("-", " ")
    # Title case
    title = title.title()
    return title


def parse_latex_from_description(description: str) -> Optional[str]:
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


def load_extraction_data(doc_path: Path) -> Dict[str, Any]:
    """
    Load document data from document.json + pages/*.json files.

    Structure:
        {doc}/document.json - document metadata
        {doc}/pages/page_001.json - per-page text, elements, summary, keywords
    """
    doc_file = doc_path / "document.json"
    if not doc_file.exists():
        raise FileNotFoundError(f"No document.json in {doc_path}")

    with open(doc_file) as f:
        doc_data = json.load(f)

    # Load pages from separate files
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
    verbose: bool = True,
) -> bool:
    """
    Ingest a single document into the database.

    Args:
        doc_name: Document name (slug)
        dry_run: Preview without making changes
        skip_existing: Skip if document already in DB
        delete_first: Delete existing document before ingesting
        embed_content: Generate embeddings (requires embedding server)
        verbose: Print progress messages

    Returns:
        True if successful, False otherwise
    """
    data_dir = get_data_dir()
    doc_path = data_dir / doc_name

    if not doc_path.exists():
        if verbose:
            print(f"ERROR: Document not found: {doc_path}")
        return False

    prefix = "[DRY RUN] " if dry_run else ""
    if verbose:
        print(f"\n{prefix}Ingesting {doc_name}...")

    # Check if already exists
    existing = get_document_by_slug(doc_name)
    if existing:
        if skip_existing:
            if verbose:
                print(f"  Skipping (already exists, id={existing['id']})")
            return True
        elif delete_first:
            if not dry_run:
                if verbose:
                    print(f"  Deleting existing document (id={existing['id']})...")
                delete_document(existing["id"])
        else:
            if verbose:
                print(f"  ERROR: Document already exists (id={existing['id']})")
                print("  Use --delete-first to replace or --skip-existing to skip")
            return False

    # Load document data
    try:
        doc_data = load_extraction_data(doc_path)
    except Exception as e:
        if verbose:
            print(f"  ERROR loading document: {e}")
        return False

    # Check for duplicate source_file (same PDF ingested under different slug)
    source_file = doc_data.get("source_file", f"{doc_name}.pdf")
    existing_by_file = get_document_by_source_file(source_file)
    if existing_by_file:
        if skip_existing:
            if verbose:
                print(
                    f"  Skipping (source_file already exists as '{existing_by_file['slug']}', id={existing_by_file['id']})"
                )
            return True
        elif delete_first:
            if not dry_run:
                if verbose:
                    print(
                        f"  Deleting existing document with same source_file (slug='{existing_by_file['slug']}', id={existing_by_file['id']})..."
                    )
                delete_document(existing_by_file["id"])
        else:
            if verbose:
                print(
                    f"  ERROR: source_file '{source_file}' already exists as slug '{existing_by_file['slug']}' (id={existing_by_file['id']})"
                )
                print("  Use --delete-first to replace or --skip-existing to skip")
            return False

    pages = doc_data.get("pages", [])
    title = clean_slug_to_title(doc_name)

    if verbose:
        print(f"  Title: {title}")
        print(f"  Pages: {len(pages)}")

    if dry_run:
        # Count elements and chunks for preview
        total_elements = sum(len(p.get("elements", [])) for p in pages)
        total_chunks = 0
        for page in pages:
            text = clean_text_for_chunking(page.get("text", ""))
            chunks = chunk_text(text, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP)
            total_chunks += len(chunks)

        if verbose:
            print(f"  Elements: {total_elements}")
            print(f"  Chunks: {total_chunks}")
            print(f"  {prefix}Would insert document, pages, chunks, and elements")
        return True

    # Check embedding server if needed
    if embed_content and not check_embed_server():
        if verbose:
            print("  WARNING: Embedding server not available - skipping embeddings")
        embed_content = False

    start_time = time.time()

    # Insert document with summary/keywords/license if available
    doc_id = insert_document(
        slug=doc_name,
        title=title,
        source_file=source_file,
        extraction_date=doc_data.get("extraction_date", ""),
        model=doc_data.get("model", "unknown"),
        metadata=doc_data.get("metadata", {}),
        summary=doc_data.get("summary"),
        keywords=doc_data.get("keywords"),
        license=doc_data.get("license"),
    )
    if verbose:
        print(f"  Inserted document (id={doc_id})")

    # Process pages
    total_chunks = 0
    total_elements = 0

    for page in pages:
        page_num = page.get("page_number", 0)

        # Insert page with summary/keywords if available
        page_id = insert_page(
            document_id=doc_id,
            page_number=page_num,
            image_path=page.get("image", ""),
            annotated_image_path=page.get("annotated_image", ""),
            full_text=page.get("text", ""),
            width=page.get("width", 0),
            height=page.get("height", 0),
            summary=page.get("summary"),
            keywords=page.get("keywords"),
        )

        # Chunk and insert text
        text = clean_text_for_chunking(page.get("text", ""))
        page_chunks = 0
        if text:
            chunks = chunk_text(text, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP)

            # Batch embed chunks (in smaller batches to avoid timeouts)
            chunk_contents = [c.content for c in chunks]
            embeddings = None
            if embed_content and chunk_contents:
                embeddings = get_embeddings_batched(chunk_contents, verbose=verbose)

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
                page_chunks += 1

        # Insert elements
        page_elements = page.get("elements", [])
        for element in page_elements:
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
        if verbose:
            print(f"    Page {page_num}: {page_chunks} chunks, {len(page_elements)} elements")

    elapsed = time.time() - start_time
    if verbose:
        print(f"  Completed: {total_chunks} chunks, {total_elements} elements ({elapsed:.1f}s)")

    return True


def list_available_documents() -> List[Dict[str, Any]]:
    """
    List available documents and their ingestion status.

    Returns:
        List of dicts with document info:
        - name: Document slug
        - pages: Number of pages in extraction
        - elements: Number of elements in extraction
        - in_db: Whether document is in database
        - db_id: Database ID if in_db is True
    """
    data_dir = get_data_dir()
    docs = []

    if not data_dir.exists():
        return docs

    for item in data_dir.iterdir():
        if not item.is_dir():
            continue

        # Check for document.json (required)
        doc_file = item / "document.json"
        if not doc_file.exists():
            continue

        doc_name = item.name

        # Count pages and elements
        try:
            doc_data = load_extraction_data(item)
            pages = doc_data.get("pages", [])
            page_count = len(pages)
            element_count = sum(len(p.get("elements", [])) for p in pages)
        except Exception:
            page_count = 0
            element_count = 0

        # Check if in database
        db_doc = get_document_by_slug(doc_name)

        docs.append(
            {
                "name": doc_name,
                "pages": page_count,
                "elements": element_count,
                "in_db": db_doc is not None,
                "db_id": db_doc["id"] if db_doc else None,
            }
        )

    return sorted(docs, key=lambda x: x["name"])


def ingest_all(
    dry_run: bool = False,
    skip_existing: bool = False,
    delete_first: bool = False,
    embed_content: bool = True,
    verbose: bool = True,
) -> int:
    """
    Ingest all available documents.

    Returns:
        Number of successfully ingested documents
    """
    from datetime import datetime

    docs = list_available_documents()
    total_docs = len(docs)
    success_count = 0

    for idx, doc in enumerate(docs, 1):
        timestamp = datetime.now().strftime("%H:%M:%S")
        if verbose:
            print(f"\n[{idx}/{total_docs}] {timestamp} - {doc['name']}")
        if ingest_document(
            doc["name"],
            dry_run=dry_run,
            skip_existing=skip_existing,
            delete_first=delete_first,
            embed_content=embed_content,
            verbose=verbose,
        ):
            success_count += 1

    if verbose:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n{timestamp} - Ingested {success_count}/{total_docs} documents")

    return success_count


# --- CLI for testing ---

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m doclibrary.db.ingest <document|--list|--all>")
        print()
        print("Options:")
        print("  <document>     Ingest specific document")
        print("  --list         List available documents")
        print("  --all          Ingest all documents")
        print("  --dry-run      Preview without changes")
        print("  --skip-existing Skip already ingested")
        print("  --delete-first Delete before re-ingesting")
        sys.exit(1)

    args = sys.argv[1:]

    if "--list" in args:
        docs = list_available_documents()
        if docs:
            print("\nDocument Ingestion Status")
            print("=" * 70)
            for doc in docs:
                status = f"[in DB, id={doc['db_id']}]" if doc["in_db"] else "[not ingested]"
                print(
                    f"  {doc['name']:30} {doc['pages']:3} pages, {doc['elements']:3} elements  {status}"
                )
        else:
            print(f"No documents found in {get_data_dir()}")
    elif "--all" in args:
        ingest_all(
            dry_run="--dry-run" in args,
            skip_existing="--skip-existing" in args,
            delete_first="--delete-first" in args,
        )
    else:
        doc_name = args[0]
        ingest_document(
            doc_name,
            dry_run="--dry-run" in args,
            skip_existing="--skip-existing" in args,
            delete_first="--delete-first" in args,
        )
