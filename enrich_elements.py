#!/usr/bin/env python3
"""
Enrich extracted elements with contextual search_text via LLM second pass.

For each element (figure, table, chart, diagram, equation), generates a
search-optimized description that connects the element to its page context,
enabling better semantic retrieval.

Usage:
    python enrich_elements.py sam3                    # Enrich one document
    python enrich_elements.py --all                   # Enrich all documents
    python enrich_elements.py sam3 --dry-run          # Preview without changes
    python enrich_elements.py sam3 --skip-existing    # Skip already enriched
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from openai import OpenAI

# LLM server for enrichment - qwen3-30b on port 8080 (vulkan, fast)
LLM_URL = os.environ.get("LLM_URL", "http://localhost:8080/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3-30b")

DB_DATA_DIR = Path("db/data")

ENRICHMENT_PROMPT = """/no_think
Page content:
{page_text}

Element: {element_type} "{label}"
Extracted: {description}

What does this element explain in this context? List key search terms. 2-3 sentences, no filler."""


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> tags from output."""
    import re

    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def get_llm_client():
    """Get OpenAI-compatible client for local LLM."""
    return OpenAI(base_url=LLM_URL, api_key="not-needed")


def enrich_element(client, element: dict, page_text: str) -> str | None:
    """Generate search_text for an element using LLM."""

    description = element.get("description", "")

    prompt = ENRICHMENT_PROMPT.format(
        element_type=element.get("type", "element"),
        label=element.get("label", "Unknown"),
        description=description,
        page_text=page_text[:3000],  # Truncate to avoid token limits
    )

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()
        return strip_think_tags(result)
    except Exception as e:
        print(f"  ERROR generating enrichment: {e}")
        return None


def process_document(doc_name: str, dry_run: bool = False, skip_existing: bool = False):
    """Enrich all elements in a document."""

    doc_path = DB_DATA_DIR / doc_name
    if not doc_path.exists():
        print(f"ERROR: Document not found: {doc_path}")
        return False

    pages_dir = doc_path / "pages"
    if not pages_dir.exists():
        print(f"ERROR: No pages directory: {pages_dir}")
        return False

    client = get_llm_client() if not dry_run else None

    # Get all page files
    page_files = sorted(pages_dir.glob("page_*.json"))
    total_elements = 0
    enriched_count = 0
    skipped_count = 0

    print(f"\nProcessing {doc_name}: {len(page_files)} pages")

    for page_file in page_files:
        with open(page_file) as f:
            page_data = json.load(f)

        page_num = page_data.get("page_number", "?")
        elements = page_data.get("elements", [])
        page_text = page_data.get("text", "")

        if not elements:
            continue

        modified = False

        for element in elements:
            total_elements += 1

            # Skip if already has search_text
            if skip_existing and element.get("search_text"):
                skipped_count += 1
                continue

            label = element.get("label", "Unknown")
            elem_type = element.get("type", "element")

            if dry_run:
                print(
                    f"  [DRY RUN] Page {page_num}: Would enrich {elem_type} '{label}'"
                )
                enriched_count += 1
                continue

            print(
                f"  Page {page_num}: Enriching {elem_type} '{label}'...",
                end=" ",
                flush=True,
            )
            start = time.time()

            search_text = enrich_element(client, element, page_text)

            if search_text:
                element["search_text"] = search_text
                modified = True
                enriched_count += 1
                elapsed = time.time() - start
                print(f"OK ({elapsed:.1f}s)")
            else:
                print("FAILED")

        # Save updated page
        if modified and not dry_run:
            with open(page_file, "w") as f:
                json.dump(page_data, f, indent=2)

    print(f"\nSummary for {doc_name}:")
    print(f"  Total elements: {total_elements}")
    print(f"  Enriched: {enriched_count}")
    print(f"  Skipped (existing): {skipped_count}")

    return True


def list_documents():
    """List available documents in db/data."""
    if not DB_DATA_DIR.exists():
        print(f"No data directory: {DB_DATA_DIR}")
        return []

    docs = []
    for item in DB_DATA_DIR.iterdir():
        if item.is_dir() and (item / "pages").exists():
            # Count elements
            pages_dir = item / "pages"
            element_count = 0
            enriched_count = 0
            for page_file in pages_dir.glob("page_*.json"):
                with open(page_file) as f:
                    page_data = json.load(f)
                for el in page_data.get("elements", []):
                    element_count += 1
                    if el.get("search_text"):
                        enriched_count += 1

            docs.append(
                {
                    "name": item.name,
                    "elements": element_count,
                    "enriched": enriched_count,
                }
            )

    return docs


def main():
    parser = argparse.ArgumentParser(
        description="Enrich elements with contextual search_text"
    )
    parser.add_argument("document", nargs="?", help="Document name to process")
    parser.add_argument("--all", action="store_true", help="Process all documents")
    parser.add_argument("--list", action="store_true", help="List available documents")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without changes"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip elements that already have search_text",
    )

    args = parser.parse_args()

    if args.list:
        docs = list_documents()
        if docs:
            print("\nAvailable documents:")
            print("-" * 60)
            for doc in docs:
                status = f"{doc['enriched']}/{doc['elements']} enriched"
                if doc["enriched"] == doc["elements"] and doc["elements"] > 0:
                    status += " [complete]"
                elif doc["enriched"] > 0:
                    status += " [partial]"
                print(f"  {doc['name']:20} {status}")
        else:
            print("No documents found in db/data/")
        return

    if args.all:
        docs = list_documents()
        for doc in docs:
            process_document(doc["name"], args.dry_run, args.skip_existing)
    elif args.document:
        process_document(args.document, args.dry_run, args.skip_existing)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
