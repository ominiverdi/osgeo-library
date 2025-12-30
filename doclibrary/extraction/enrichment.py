#!/usr/bin/env python3
"""
Enrich extracted documents with LLM-generated metadata.

Generates:
- search_text for elements (figures, tables, equations)
- summary and keywords for pages
- summary, keywords, and license for documents

Usage:
    from doclibrary.extraction import enrich_document

    # Enrich all elements, pages, and document
    enrich_document("sam3")

    # Skip already enriched items
    enrich_document("sam3", skip_existing=True)
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from openai import OpenAI

from doclibrary.config import config
from doclibrary.core.llm import strip_think_tags

# Default data directory
DEFAULT_DATA_DIR = Path("db/data")

# --- Prompt Templates ---

# Element search_text generation
ELEMENT_ENRICHMENT_PROMPT = """/no_think
Page content:
{page_text}

Element: {element_type} "{label}"
Extracted: {description}

What does this element explain in this context? List key search terms. 2-3 sentences, no filler."""

# Page summary and keywords
PAGE_SUMMARY_PROMPT = """/no_think
Page content from a scientific document:

{page_text}

Summarize this page in 2-3 sentences. Then list 5-8 keywords (no more than 8).

Format:
SUMMARY: <your summary>
KEYWORDS: <comma-separated list of 5-8 keywords only>"""

# Document summary (from page summaries)
DOCUMENT_SUMMARY_PROMPT = """/no_think
This is a collection of page summaries from a scientific document titled "{title}":

{page_summaries}

Task:
1. Write a comprehensive summary of this document (3-5 sentences).
2. List the 10 most important keywords only. Do NOT list more than 10.

Format your response EXACTLY like this:
SUMMARY: <your 3-5 sentence summary>
KEYWORDS: keyword1, keyword2, keyword3, keyword4, keyword5, keyword6, keyword7, keyword8, keyword9, keyword10"""

# License extraction
LICENSE_PROMPT = """/no_think
Extract the license or copyright information from this text. If no license is found, respond with "NONE".

Text from first and last pages:
{text}

Respond with just the license name or terms (e.g., "CC-BY-4.0", "MIT", "All rights reserved", or the full license text if custom)."""


def _get_enrichment_client() -> OpenAI:
    """Get OpenAI client for enrichment LLM server."""
    return OpenAI(base_url=config.enrichment_llm_url, api_key="not-needed")


def enrich_element(
    element: Dict[str, Any],
    page_text: str,
    client: Optional[OpenAI] = None,
) -> Optional[str]:
    """Generate search_text for an element using LLM.

    Args:
        element: Element dictionary with 'type', 'label', 'description'
        page_text: Full text content of the page
        client: Optional OpenAI client (created if not provided)

    Returns:
        Generated search_text string, or None on error
    """
    if client is None:
        client = _get_enrichment_client()

    description = element.get("description", "")

    prompt = ELEMENT_ENRICHMENT_PROMPT.format(
        element_type=element.get("type", "element"),
        label=element.get("label", "Unknown"),
        description=description,
        page_text=page_text[:3000],  # Truncate to avoid token limits
    )

    try:
        response = client.chat.completions.create(
            model=config.enrichment_llm_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        content = response.choices[0].message.content
        if content is None:
            return None
        result = content.strip()
        return strip_think_tags(result)
    except Exception as e:
        print(f"  ERROR generating enrichment: {e}")
        return None


def _parse_summary_keywords(
    response: str, max_keywords: int = 10
) -> Tuple[Optional[str], List[str]]:
    """Parse SUMMARY: and KEYWORDS: from LLM response.

    Args:
        response: LLM response text
        max_keywords: Maximum number of keywords to return (default 10)

    Returns:
        Tuple of (summary, keywords list)
    """
    summary = None
    keywords = []

    # Extract summary
    summary_match = re.search(
        r"SUMMARY:\s*(.+?)(?=KEYWORDS:|$)", response, re.DOTALL | re.IGNORECASE
    )
    if summary_match:
        summary = summary_match.group(1).strip()

    # Extract keywords
    keywords_match = re.search(r"KEYWORDS:\s*(.+)", response, re.DOTALL | re.IGNORECASE)
    if keywords_match:
        keywords_text = keywords_match.group(1).strip()
        # Split by comma, clean up each keyword, limit to max
        keywords = [k.strip().lower() for k in keywords_text.split(",") if k.strip()]
        keywords = keywords[:max_keywords]  # Hard limit

    return summary, keywords


def summarize_page(
    page_text: str,
    client: Optional[OpenAI] = None,
) -> Tuple[Optional[str], List[str]]:
    """Generate summary and keywords for a page.

    Args:
        page_text: Full text content of the page
        client: Optional OpenAI client

    Returns:
        Tuple of (summary, keywords list)
    """
    if client is None:
        client = _get_enrichment_client()

    if not page_text or len(page_text.strip()) < 100:
        return None, []

    prompt = PAGE_SUMMARY_PROMPT.format(page_text=page_text[:4000])

    try:
        response = client.chat.completions.create(
            model=config.enrichment_llm_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        content = response.choices[0].message.content
        if content is None:
            return None, []
        result = strip_think_tags(content.strip())
        return _parse_summary_keywords(result, max_keywords=8)  # 5-8 keywords per page
    except Exception as e:
        print(f"  ERROR generating page summary: {e}")
        return None, []


def summarize_document(
    title: str,
    page_summaries: List[str],
    client: Optional[OpenAI] = None,
) -> Tuple[Optional[str], List[str]]:
    """Generate document summary and keywords from page summaries.

    Args:
        title: Document title
        page_summaries: List of page summary strings
        client: Optional OpenAI client

    Returns:
        Tuple of (summary, keywords list)
    """
    if client is None:
        client = _get_enrichment_client()

    if not page_summaries:
        return None, []

    # Combine page summaries with page numbers
    summaries_text = "\n".join(f"Page {i + 1}: {s}" for i, s in enumerate(page_summaries) if s)

    # Truncate if too long
    if len(summaries_text) > 8000:
        summaries_text = summaries_text[:8000] + "\n..."

    prompt = DOCUMENT_SUMMARY_PROMPT.format(title=title, page_summaries=summaries_text)

    try:
        response = client.chat.completions.create(
            model=config.enrichment_llm_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )
        content = response.choices[0].message.content
        if content is None:
            return None, []
        result = strip_think_tags(content.strip())
        return _parse_summary_keywords(result, max_keywords=10)  # 10 keywords for document
    except Exception as e:
        print(f"  ERROR generating document summary: {e}")
        return None, []


def extract_license(
    first_page_text: str,
    last_page_text: str,
    client: Optional[OpenAI] = None,
) -> Optional[str]:
    """Extract license information from document.

    Args:
        first_page_text: Text from first page
        last_page_text: Text from last page
        client: Optional OpenAI client

    Returns:
        License string or None if not found
    """
    if client is None:
        client = _get_enrichment_client()

    # Combine first and last page text
    combined = f"FIRST PAGE:\n{first_page_text[:2000]}\n\nLAST PAGE:\n{last_page_text[:2000]}"

    prompt = LICENSE_PROMPT.format(text=combined)

    try:
        response = client.chat.completions.create(
            model=config.enrichment_llm_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1,
        )
        content = response.choices[0].message.content
        if content is None:
            return None
        result = strip_think_tags(content.strip())
        if result.upper() == "NONE" or not result:
            return None
        return result
    except Exception as e:
        print(f"  ERROR extracting license: {e}")
        return None


def enrich_document(
    doc_name: str,
    data_dir: Optional[Union[str, Path]] = None,
    dry_run: bool = False,
    skip_existing: bool = False,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Enrich document with search_text, summaries, keywords, and license.

    Enriches:
    - Elements: search_text (contextual description for retrieval)
    - Pages: summary and keywords
    - Document: summary, keywords, and license

    Args:
        doc_name: Document name (subdirectory in data_dir)
        data_dir: Path to data directory (default: db/data)
        dry_run: If True, preview without making changes
        skip_existing: If True, skip items that already have enrichment
        verbose: Print progress

    Returns:
        Dictionary with counts for elements, pages, document enrichment
    """
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    doc_path = data_dir / doc_name

    if not doc_path.exists():
        if verbose:
            print(f"ERROR: Document not found: {doc_path}")
        return {"error": True}

    pages_dir = doc_path / "pages"
    if not pages_dir.exists():
        if verbose:
            print(f"ERROR: No pages directory: {pages_dir}")
        return {"error": True}

    doc_file = doc_path / "document.json"
    if not doc_file.exists():
        if verbose:
            print(f"ERROR: No document.json: {doc_file}")
        return {"error": True}

    client = _get_enrichment_client() if not dry_run else None

    # Load document metadata
    with open(doc_file) as f:
        doc_data = json.load(f)

    # Get all page files
    page_files = sorted(pages_dir.glob("page_*.json"))

    if verbose:
        print(f"\nProcessing {doc_name}: {len(page_files)} pages")

    # Stats tracking
    stats = {
        "elements_total": 0,
        "elements_enriched": 0,
        "elements_skipped": 0,
        "pages_summarized": 0,
        "pages_skipped": 0,
        "document_enriched": False,
    }

    # Collect page summaries for document-level summary
    page_summaries: List[str] = []
    first_page_text = ""
    last_page_text = ""

    # --- Phase 1: Enrich elements and pages ---
    for i, page_file in enumerate(page_files):
        with open(page_file) as f:
            page_data = json.load(f)

        page_num = page_data.get("page_number", i + 1)
        elements = page_data.get("elements", [])
        page_text = page_data.get("text", "")

        # Track first/last page text for license extraction
        if i == 0:
            first_page_text = page_text
        if i == len(page_files) - 1:
            last_page_text = page_text

        modified = False

        # --- Enrich elements ---
        for element in elements:
            stats["elements_total"] += 1

            if skip_existing and element.get("search_text"):
                stats["elements_skipped"] += 1
                continue

            label = element.get("label", "Unknown")
            elem_type = element.get("type", "element")

            if dry_run:
                if verbose:
                    print(f"  [DRY RUN] Page {page_num}: Would enrich {elem_type} '{label}'")
                stats["elements_enriched"] += 1
                continue

            if verbose:
                print(f"  Page {page_num}: Enriching {elem_type} '{label}'...", end=" ", flush=True)

            start = time.time()
            search_text = enrich_element(element, page_text, client)

            if search_text:
                element["search_text"] = search_text
                modified = True
                stats["elements_enriched"] += 1
                if verbose:
                    print(f"OK ({time.time() - start:.1f}s)")
            else:
                if verbose:
                    print("FAILED")

        # --- Summarize page ---
        if skip_existing and page_data.get("summary"):
            stats["pages_skipped"] += 1
            # Still collect for document summary
            page_summaries.append(page_data.get("summary", ""))
        elif page_text and len(page_text.strip()) >= 100:
            if dry_run:
                if verbose:
                    print(f"  [DRY RUN] Page {page_num}: Would generate summary")
                stats["pages_summarized"] += 1
            else:
                if verbose:
                    print(f"  Page {page_num}: Generating summary...", end=" ", flush=True)

                start = time.time()
                summary, keywords = summarize_page(page_text, client)

                if summary:
                    page_data["summary"] = summary
                    page_data["keywords"] = keywords
                    page_summaries.append(summary)
                    modified = True
                    stats["pages_summarized"] += 1
                    if verbose:
                        print(f"OK ({time.time() - start:.1f}s) - {len(keywords)} keywords")
                else:
                    if verbose:
                        print("FAILED")

        # Save updated page
        if modified and not dry_run:
            with open(page_file, "w") as f:
                json.dump(page_data, f, indent=2)

    # --- Phase 2: Document-level enrichment ---
    doc_modified = False

    # Generate document summary from page summaries
    if skip_existing and doc_data.get("summary"):
        if verbose:
            print(f"\n  Document summary: skipped (exists)")
    elif page_summaries:
        if dry_run:
            if verbose:
                print(
                    f"\n  [DRY RUN] Would generate document summary from {len(page_summaries)} pages"
                )
        else:
            if verbose:
                print(
                    f"\n  Generating document summary from {len(page_summaries)} pages...",
                    end=" ",
                    flush=True,
                )

            start = time.time()
            title = doc_data.get("title", doc_name)
            doc_summary, doc_keywords = summarize_document(title, page_summaries, client)

            if doc_summary:
                doc_data["summary"] = doc_summary
                doc_data["keywords"] = doc_keywords
                doc_modified = True
                stats["document_enriched"] = True
                if verbose:
                    print(f"OK ({time.time() - start:.1f}s) - {len(doc_keywords)} keywords")
            else:
                if verbose:
                    print("FAILED")

    # Extract license
    if skip_existing and doc_data.get("license"):
        if verbose:
            print(f"  License: skipped (exists)")
    else:
        if dry_run:
            if verbose:
                print(f"  [DRY RUN] Would extract license")
        else:
            if verbose:
                print(f"  Extracting license...", end=" ", flush=True)

            start = time.time()
            license_text = extract_license(first_page_text, last_page_text, client)

            if license_text:
                doc_data["license"] = license_text
                doc_modified = True
                if verbose:
                    print(f"OK ({time.time() - start:.1f}s) - {license_text[:50]}...")
            else:
                if verbose:
                    print("None found")

    # Save document.json
    if doc_modified and not dry_run:
        with open(doc_file, "w") as f:
            json.dump(doc_data, f, indent=2)

    # Print summary
    if verbose:
        print(f"\nSummary for {doc_name}:")
        print(
            f"  Elements: {stats['elements_enriched']} enriched, {stats['elements_skipped']} skipped"
        )
        print(f"  Pages: {stats['pages_summarized']} summarized, {stats['pages_skipped']} skipped")
        print(f"  Document: {'enriched' if stats['document_enriched'] else 'skipped/failed'}")

    return stats


def list_documents(data_dir: Optional[Union[str, Path]] = None) -> list:
    """List available documents in data directory.

    Args:
        data_dir: Path to data directory (default: db/data)

    Returns:
        List of dicts with 'name', 'elements', 'enriched' counts
    """
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR

    if not data_dir.exists():
        return []

    docs = []
    for item in data_dir.iterdir():
        if item.is_dir() and (item / "pages").exists():
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


# --- CLI for testing ---

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enrich elements with contextual search_text")
    parser.add_argument("document", nargs="?", help="Document name to process")
    parser.add_argument("--all", action="store_true", help="Process all documents")
    parser.add_argument("--list", action="store_true", help="List available documents")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
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
    elif args.all:
        docs = list_documents()
        for doc in docs:
            enrich_document(doc["name"], dry_run=args.dry_run, skip_existing=args.skip_existing)
    elif args.document:
        enrich_document(args.document, dry_run=args.dry_run, skip_existing=args.skip_existing)
    else:
        parser.print_help()
