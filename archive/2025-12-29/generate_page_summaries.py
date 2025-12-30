#!/usr/bin/env python3
"""
Generate page summaries using LLM.

Summarizes each page of a document and stores the result in the database.
Uses ministral-3-8b by default (best quality/speed from testing).

Usage:
    python generate_page_summaries.py eo_distortions     # Summarize one document
    python generate_page_summaries.py --all              # Summarize all documents
    python generate_page_summaries.py --list             # List documents and status
    python generate_page_summaries.py eo_distortions --skip-existing  # Skip already summarized
    python generate_page_summaries.py eo_distortions --dry-run        # Preview without changes
"""

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
from db.connection import fetch_all, fetch_one, execute

# Default model configuration
DEFAULT_MODEL_URL = "http://localhost:8082/v1/chat/completions"
DEFAULT_MODEL_NAME = "ministral-3-8b"

SUMMARY_PROMPT = """Summarize this page from a scientific document in 2-3 sentences.
Focus on the main topic and key findings. Be concise and factual.

Page content:
{page_text}"""


@dataclass
class PageInfo:
    """Page information from database."""

    id: int
    document_id: int
    document_slug: str
    page_number: int
    full_text: str
    chars: int
    has_summary: bool


def get_document_pages(doc_slug: str, skip_existing: bool = False) -> list[PageInfo]:
    """Get all pages for a document."""

    condition = "AND p.summary IS NULL" if skip_existing else ""

    query = f"""
        SELECT p.id, p.document_id, d.slug as document_slug, p.page_number, 
               p.full_text, LENGTH(p.full_text) as chars,
               p.summary IS NOT NULL as has_summary
        FROM pages p
        JOIN documents d ON p.document_id = d.id
        WHERE d.slug = %s {condition}
        ORDER BY p.page_number
    """

    rows = fetch_all(query, (doc_slug,))

    return [
        PageInfo(
            id=r["id"],
            document_id=r["document_id"],
            document_slug=r["document_slug"],
            page_number=r["page_number"],
            full_text=r["full_text"] or "",
            chars=r["chars"] or 0,
            has_summary=r["has_summary"],
        )
        for r in rows
    ]


def summarize_page(
    client: httpx.Client, page: PageInfo, model_url: str, timeout: float = 120.0
) -> tuple[str | None, float, str | None]:
    """
    Generate summary for a page.

    Returns: (summary, elapsed_seconds, error)
    """

    if not page.full_text or page.chars < 50:
        return None, 0.0, "Page too short to summarize"

    prompt = SUMMARY_PROMPT.format(page_text=page.full_text)

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 250,
        "temperature": 0.3,
    }

    start_time = time.perf_counter()

    try:
        response = client.post(model_url, json=payload, timeout=timeout)
        response.raise_for_status()

        data = response.json()
        elapsed = time.perf_counter() - start_time

        summary = data["choices"][0]["message"]["content"].strip()
        return summary, elapsed, None

    except httpx.TimeoutException:
        return None, timeout, "TIMEOUT"
    except httpx.ConnectError:
        return None, 0.0, "CONNECTION_FAILED - Is server running?"
    except Exception as e:
        return None, time.perf_counter() - start_time, str(e)


def update_page_summary(page_id: int, summary: str) -> None:
    """Store summary in database."""
    execute("UPDATE pages SET summary = %s WHERE id = %s", (summary, page_id))


def list_documents() -> None:
    """List all documents with summarization status."""

    docs = fetch_all("""
        SELECT d.id, d.slug, 
               COUNT(p.id) as total_pages,
               COUNT(p.summary) as summarized_pages,
               SUM(LENGTH(p.full_text)) as total_chars
        FROM documents d
        LEFT JOIN pages p ON d.id = p.document_id
        GROUP BY d.id, d.slug
        ORDER BY total_pages ASC
    """)

    print("\nDocuments and summarization status:")
    print("-" * 70)
    print(
        f"{'Document':<20} {'Pages':>6} {'Summarized':>12} {'Chars':>12} {'Status':<15}"
    )
    print("-" * 70)

    for doc in docs:
        total = doc["total_pages"]
        done = doc["summarized_pages"]
        chars = doc["total_chars"] or 0

        if done == 0:
            status = "pending"
        elif done == total:
            status = "complete"
        else:
            status = f"partial ({done}/{total})"

        print(f"{doc['slug']:<20} {total:>6} {done:>12} {chars:>12,} {status:<15}")


def process_document(
    doc_slug: str,
    model_url: str = DEFAULT_MODEL_URL,
    skip_existing: bool = False,
    dry_run: bool = False,
) -> dict:
    """Process all pages of a document."""

    # Get document info
    doc = fetch_one(
        "SELECT id, slug, title FROM documents WHERE slug = %s", (doc_slug,)
    )
    if not doc:
        print(f"ERROR: Document '{doc_slug}' not found")
        return {"success": False, "error": "Document not found"}

    # Get pages
    pages = get_document_pages(doc_slug, skip_existing)

    if not pages:
        if skip_existing:
            print(f"All pages already summarized for '{doc_slug}'")
        else:
            print(f"No pages found for '{doc_slug}'")
        return {"success": True, "processed": 0, "skipped": 0}

    print(f"\nProcessing: {doc['title'] or doc_slug}")
    print(f"Pages to summarize: {len(pages)}")
    print(f"Model: {model_url}")
    print("-" * 60)

    if dry_run:
        print("[DRY RUN] Would summarize these pages:")
        for page in pages:
            print(f"  Page {page.page_number}: {page.chars} chars")
        return {"success": True, "processed": 0, "dry_run": True}

    # Process pages
    stats = {
        "processed": 0,
        "skipped": 0,
        "errors": 0,
        "total_time": 0.0,
        "start_time": datetime.now().isoformat(),
    }

    with httpx.Client() as client:
        for i, page in enumerate(pages):
            print(
                f"[{i + 1}/{len(pages)}] Page {page.page_number} ({page.chars} chars)... ",
                end="",
                flush=True,
            )

            summary, elapsed, error = summarize_page(client, page, model_url)

            if error:
                print(f"ERROR: {error}")
                stats["errors"] += 1
                continue

            if summary:
                update_page_summary(page.id, summary)
                stats["processed"] += 1
                stats["total_time"] += elapsed

                # Show preview
                preview = summary[:80].replace("\n", " ")
                if len(summary) > 80:
                    preview += "..."
                print(f"OK ({elapsed:.1f}s) - {preview}")
            else:
                print("SKIPPED (empty)")
                stats["skipped"] += 1

    # Summary
    print("-" * 60)
    print(f"Completed: {stats['processed']} pages summarized")
    print(f"Skipped: {stats['skipped']}")
    print(f"Errors: {stats['errors']}")
    if stats["processed"] > 0:
        avg_time = stats["total_time"] / stats["processed"]
        print(f"Average time: {avg_time:.1f}s per page")
        print(f"Total time: {stats['total_time']:.1f}s")

    stats["success"] = True
    stats["end_time"] = datetime.now().isoformat()

    return stats


def check_server(model_url: str) -> bool:
    """Check if model server is running."""
    health_url = model_url.replace("/v1/chat/completions", "/health")
    try:
        response = httpx.get(health_url, timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate page summaries using LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_page_summaries.py --list
  python generate_page_summaries.py eo_distortions
  python generate_page_summaries.py --all --skip-existing
        """,
    )
    parser.add_argument("document", nargs="?", help="Document slug to process")
    parser.add_argument("--all", action="store_true", help="Process all documents")
    parser.add_argument("--list", action="store_true", help="List documents and status")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip pages that already have summaries",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without making changes"
    )
    parser.add_argument(
        "--model-url",
        default=DEFAULT_MODEL_URL,
        help=f"Model server URL (default: {DEFAULT_MODEL_URL})",
    )

    args = parser.parse_args()

    if args.list:
        list_documents()
        return

    if not args.document and not args.all:
        parser.print_help()
        return

    # Check server
    if not args.dry_run:
        print(f"Checking model server at {args.model_url}...")
        if not check_server(args.model_url):
            print(f"ERROR: Model server not responding at {args.model_url}")
            print("Start it with:")
            print("  /media/nvme2g-a/llm_toolbox/servers/ministral-3-8b-8082.sh 8082 &")
            sys.exit(1)
        print("Server OK")

    if args.all:
        # Get all documents ordered by size
        docs = fetch_all("""
            SELECT d.slug FROM documents d
            JOIN pages p ON d.id = p.document_id
            GROUP BY d.id, d.slug
            ORDER BY COUNT(p.id) ASC
        """)

        for doc in docs:
            process_document(
                doc["slug"],
                model_url=args.model_url,
                skip_existing=args.skip_existing,
                dry_run=args.dry_run,
            )
    else:
        process_document(
            args.document,
            model_url=args.model_url,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
