#!/usr/bin/env python3
"""
Comparative test for page summarization models.

Tests 3 small LLM models on a stratified sample of pages to compare:
- Speed (tokens/second, time per summary)
- Quality (manual review)
- Consistency (follows prompt format)
- Error rate

Usage:
    # Start the 3 servers first:
    # Port 8082: ministral-3-8b
    # Port 8083: qwen3-8b
    # Port 8084: granite-3.3-8b

    python test_page_summarization.py              # Run test
    python test_page_summarization.py --sample 10  # Quick test with 10 pages
    python test_page_summarization.py --report     # Show last report
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
from db.connection import fetch_all, fetch_one

# Model configurations
MODELS = {
    "ministral-3-8b": {
        "url": "http://localhost:8082/v1/chat/completions",
        "description": "Ministral 3 8B - Newest Mistral small model",
    },
    "qwen3-8b": {
        "url": "http://localhost:8083/v1/chat/completions",
        "description": "Qwen3 8B - Good quality for size",
    },
    "granite-3.3-8b": {
        "url": "http://localhost:8084/v1/chat/completions",
        "description": "IBM Granite 3.3 8B - Good at structured output",
    },
}

SUMMARY_PROMPT = """Summarize this page from a scientific document in 2-3 sentences.
Focus on the main topic and key findings. Be concise and factual.

Page content:
{page_text}"""

REPORT_DIR = Path("reports")


@dataclass
class SummaryResult:
    """Result from a single summarization attempt."""

    model: str
    page_id: int
    document_slug: str
    page_number: int
    input_chars: int
    input_tokens_est: int
    summary: Optional[str] = None
    output_tokens: int = 0
    elapsed_seconds: float = 0.0
    tokens_per_second: float = 0.0
    error: Optional[str] = None


@dataclass
class TestPage:
    """A page selected for testing."""

    id: int
    document_id: int
    document_slug: str
    page_number: int
    full_text: str
    chars: int
    category: str  # 'normal', 'short', 'long', 'stratified'


def select_test_pages(target_count: int = 30) -> list[TestPage]:
    """
    Select a stratified sample of pages for testing.

    Strategy:
    - At least 2 pages from each document (20 pages for 10 docs)
    - Edge cases: 3-5 very short pages (< 800 chars)
    - Edge cases: 3-5 very long pages (> 4000 chars)
    - Rest: random normal pages
    """
    pages = []

    # Get document list
    docs = fetch_all("""
        SELECT d.id, d.slug, COUNT(p.id) as page_count
        FROM documents d
        JOIN pages p ON d.id = p.document_id
        GROUP BY d.id, d.slug
        ORDER BY d.slug
    """)

    print(f"Found {len(docs)} documents")

    # 1. Stratified sample: 2 random pages per document
    for doc in docs:
        doc_pages = fetch_all(
            """
            SELECT p.id, p.document_id, p.page_number, p.full_text, LENGTH(p.full_text) as chars
            FROM pages p
            WHERE p.document_id = %s 
              AND LENGTH(p.full_text) > 300
            ORDER BY RANDOM()
            LIMIT 2
        """,
            (doc["id"],),
        )

        for p in doc_pages:
            pages.append(
                TestPage(
                    id=p["id"],
                    document_id=p["document_id"],
                    document_slug=doc["slug"],
                    page_number=p["page_number"],
                    full_text=p["full_text"],
                    chars=p["chars"],
                    category="stratified",
                )
            )

    print(f"  Stratified pages: {len(pages)}")

    # 2. Edge case: very short pages (< 800 chars)
    short_pages = fetch_all(
        """
        SELECT p.id, p.document_id, d.slug, p.page_number, p.full_text, LENGTH(p.full_text) as chars
        FROM pages p
        JOIN documents d ON p.document_id = d.id
        WHERE LENGTH(p.full_text) BETWEEN 100 AND 800
          AND p.id NOT IN %s
        ORDER BY RANDOM()
        LIMIT 5
    """,
        (tuple(p.id for p in pages) or (0,),),
    )

    for p in short_pages:
        pages.append(
            TestPage(
                id=p["id"],
                document_id=p["document_id"],
                document_slug=p["slug"],
                page_number=p["page_number"],
                full_text=p["full_text"],
                chars=p["chars"],
                category="short",
            )
        )

    print(f"  + Short pages: {len(short_pages)}")

    # 3. Edge case: very long pages (> 4000 chars)
    long_pages = fetch_all(
        """
        SELECT p.id, p.document_id, d.slug, p.page_number, p.full_text, LENGTH(p.full_text) as chars
        FROM pages p
        JOIN documents d ON p.document_id = d.id
        WHERE LENGTH(p.full_text) > 4000
          AND p.id NOT IN %s
        ORDER BY RANDOM()
        LIMIT 5
    """,
        (tuple(p.id for p in pages) or (0,),),
    )

    for p in long_pages:
        pages.append(
            TestPage(
                id=p["id"],
                document_id=p["document_id"],
                document_slug=p["slug"],
                page_number=p["page_number"],
                full_text=p["full_text"],
                chars=p["chars"],
                category="long",
            )
        )

    print(f"  + Long pages: {len(long_pages)}")

    # 4. Fill remaining with random normal pages if needed
    remaining = target_count - len(pages)
    if remaining > 0:
        random_pages = fetch_all(
            """
            SELECT p.id, p.document_id, d.slug, p.page_number, p.full_text, LENGTH(p.full_text) as chars
            FROM pages p
            JOIN documents d ON p.document_id = d.id
            WHERE LENGTH(p.full_text) BETWEEN 800 AND 4000
              AND p.id NOT IN %s
            ORDER BY RANDOM()
            LIMIT %s
        """,
            (tuple(p.id for p in pages) or (0,), remaining),
        )

        for p in random_pages:
            pages.append(
                TestPage(
                    id=p["id"],
                    document_id=p["document_id"],
                    document_slug=p["slug"],
                    page_number=p["page_number"],
                    full_text=p["full_text"],
                    chars=p["chars"],
                    category="normal",
                )
            )

        print(f"  + Random pages: {len(random_pages)}")

    print(f"Total test pages: {len(pages)}")
    return pages


async def call_model(
    client: httpx.AsyncClient,
    model_name: str,
    model_config: dict,
    page: TestPage,
    timeout: float = 60.0,
) -> SummaryResult:
    """Call a model to summarize a page."""

    result = SummaryResult(
        model=model_name,
        page_id=page.id,
        document_slug=page.document_slug,
        page_number=page.page_number,
        input_chars=page.chars,
        input_tokens_est=page.chars // 4,
    )

    prompt = SUMMARY_PROMPT.format(page_text=page.full_text)

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.3,
    }

    start_time = time.perf_counter()

    try:
        response = await client.post(model_config["url"], json=payload, timeout=timeout)
        response.raise_for_status()

        data = response.json()

        result.elapsed_seconds = time.perf_counter() - start_time
        result.summary = data["choices"][0]["message"]["content"].strip()
        summary_len = len(result.summary) if result.summary else 0
        result.output_tokens = data.get("usage", {}).get(
            "completion_tokens", summary_len // 4
        )

        if result.elapsed_seconds > 0:
            result.tokens_per_second = result.output_tokens / result.elapsed_seconds

    except httpx.TimeoutException:
        result.error = "TIMEOUT"
        result.elapsed_seconds = timeout
    except httpx.ConnectError:
        result.error = "CONNECTION_FAILED - Is server running?"
        result.elapsed_seconds = 0
    except Exception as e:
        result.error = str(e)
        result.elapsed_seconds = time.perf_counter() - start_time

    return result


async def test_page_with_all_models(
    client: httpx.AsyncClient, page: TestPage, models: dict
) -> dict[str, SummaryResult]:
    """Test a single page with all models in parallel."""

    tasks = [call_model(client, name, config, page) for name, config in models.items()]

    results = await asyncio.gather(*tasks)

    return {r.model: r for r in results}


async def run_test(pages: list[TestPage], models: dict) -> list[dict]:
    """Run the full test suite."""

    all_results = []

    async with httpx.AsyncClient() as client:
        for i, page in enumerate(pages):
            print(
                f"\n[{i + 1}/{len(pages)}] Testing page {page.document_slug} p.{page.page_number} ({page.chars} chars, {page.category})"
            )

            results = await test_page_with_all_models(client, page, models)

            # Print quick summary
            for model_name, result in results.items():
                if result.error:
                    status = f"ERROR: {result.error}"
                else:
                    status = f"{result.elapsed_seconds:.2f}s, {result.tokens_per_second:.1f} tok/s"
                print(f"  {model_name}: {status}")

            all_results.append(
                {
                    "page": {
                        "id": page.id,
                        "document_slug": page.document_slug,
                        "page_number": page.page_number,
                        "chars": page.chars,
                        "category": page.category,
                    },
                    "results": {
                        name: {
                            "summary": r.summary,
                            "elapsed_seconds": r.elapsed_seconds,
                            "output_tokens": r.output_tokens,
                            "tokens_per_second": r.tokens_per_second,
                            "error": r.error,
                        }
                        for name, r in results.items()
                    },
                }
            )

    return all_results


def generate_report(all_results: list[dict], models: dict) -> str:
    """Generate a markdown report from test results."""

    lines = []
    lines.append("# Page Summarization Model Comparison Report")
    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"\nPages tested: {len(all_results)}")
    lines.append(f"\nModels tested: {', '.join(models.keys())}")

    # Summary statistics
    lines.append("\n## Summary Statistics\n")

    stats = {
        name: {
            "total_time": 0,
            "total_tokens": 0,
            "success_count": 0,
            "error_count": 0,
            "times": [],
            "tps": [],
        }
        for name in models
    }

    for result in all_results:
        for model_name, r in result["results"].items():
            if r["error"]:
                stats[model_name]["error_count"] += 1
            else:
                stats[model_name]["success_count"] += 1
                stats[model_name]["total_time"] += r["elapsed_seconds"]
                stats[model_name]["total_tokens"] += r["output_tokens"]
                stats[model_name]["times"].append(r["elapsed_seconds"])
                stats[model_name]["tps"].append(r["tokens_per_second"])

    lines.append("| Model | Success | Errors | Avg Time | Avg tok/s | Total Time |")
    lines.append("|-------|---------|--------|----------|-----------|------------|")

    for model_name in models:
        s = stats[model_name]
        if s["success_count"] > 0:
            avg_time = s["total_time"] / s["success_count"]
            avg_tps = sum(s["tps"]) / len(s["tps"]) if s["tps"] else 0
        else:
            avg_time = 0
            avg_tps = 0

        lines.append(
            f"| {model_name} | {s['success_count']} | {s['error_count']} | {avg_time:.2f}s | {avg_tps:.1f} | {s['total_time']:.1f}s |"
        )

    # Detailed results by category
    lines.append("\n## Results by Category\n")

    for category in ["stratified", "short", "long", "normal"]:
        cat_results = [r for r in all_results if r["page"]["category"] == category]
        if not cat_results:
            continue

        lines.append(f"\n### {category.title()} Pages ({len(cat_results)} pages)\n")

        for result in cat_results:
            page = result["page"]
            lines.append(
                f"\n#### {page['document_slug']} - Page {page['page_number']} ({page['chars']} chars)\n"
            )

            for model_name in models:
                r = result["results"][model_name]
                lines.append(f"**{model_name}**")
                if r["error"]:
                    lines.append(f"- ERROR: {r['error']}")
                else:
                    lines.append(
                        f"- Time: {r['elapsed_seconds']:.2f}s | Tokens: {r['output_tokens']} | {r['tokens_per_second']:.1f} tok/s"
                    )
                    lines.append(f"- Summary: {r['summary']}")
                lines.append("")

    # Performance comparison chart (ASCII)
    lines.append("\n## Performance Comparison\n")
    lines.append("```")
    lines.append("Average Time per Page (lower is better):")

    max_time = max(
        stats[m]["total_time"] / stats[m]["success_count"]
        for m in models
        if stats[m]["success_count"] > 0
    )

    for model_name in models:
        s = stats[model_name]
        if s["success_count"] > 0:
            avg_time = s["total_time"] / s["success_count"]
            bar_len = int((avg_time / max_time) * 40)
            lines.append(f"{model_name:20} {'#' * bar_len} {avg_time:.2f}s")

    lines.append("\nAverage Tokens/Second (higher is better):")

    max_tps = max(
        sum(stats[m]["tps"]) / len(stats[m]["tps"]) for m in models if stats[m]["tps"]
    )

    for model_name in models:
        s = stats[model_name]
        if s["tps"]:
            avg_tps = sum(s["tps"]) / len(s["tps"])
            bar_len = int((avg_tps / max_tps) * 40)
            lines.append(f"{model_name:20} {'#' * bar_len} {avg_tps:.1f} tok/s")

    lines.append("```")

    return "\n".join(lines)


async def check_servers(models: dict) -> dict[str, bool]:
    """Check which model servers are running."""
    status = {}

    async with httpx.AsyncClient() as client:
        for name, config in models.items():
            health_url = config["url"].replace("/v1/chat/completions", "/health")
            try:
                response = await client.get(health_url, timeout=5.0)
                status[name] = response.status_code == 200
            except Exception:
                status[name] = False

    return status


async def main():
    parser = argparse.ArgumentParser(description="Compare page summarization models")
    parser.add_argument(
        "--sample", type=int, default=30, help="Number of pages to test"
    )
    parser.add_argument("--report", action="store_true", help="Show last report")
    parser.add_argument("--check", action="store_true", help="Check server status only")
    args = parser.parse_args()

    REPORT_DIR.mkdir(exist_ok=True)

    if args.report:
        # Show most recent report
        reports = sorted(REPORT_DIR.glob("summary_comparison_*.md"))
        if reports:
            print(reports[-1].read_text())
        else:
            print("No reports found. Run the test first.")
        return

    if args.check:
        print("Checking model servers...")
        status = await check_servers(MODELS)
        for name, running in status.items():
            icon = "[OK]" if running else "[NOT RUNNING]"
            print(f"  {icon} {name}: {MODELS[name]['url']}")
        return

    # Check servers before running
    print("Checking model servers...")
    status = await check_servers(MODELS)

    running_models = {name: config for name, config in MODELS.items() if status[name]}
    not_running = [name for name, config in MODELS.items() if not status[name]]

    if not_running:
        print(f"\nWARNING: These servers are not running: {', '.join(not_running)}")
        print("Start them with:")
        for name in not_running:
            port = MODELS[name]["url"].split(":")[-1].split("/")[0]
            print(
                f"  /media/nvme2g-a/llm_toolbox/servers/{name.replace('.', '-')}-*.sh {port} &"
            )

    if not running_models:
        print("\nERROR: No model servers are running. Start at least one server.")
        sys.exit(1)

    print(f"\nRunning models: {', '.join(running_models.keys())}")

    # Select test pages
    print(f"\nSelecting {args.sample} test pages...")
    pages = select_test_pages(args.sample)

    # Run tests
    print(f"\nRunning tests...")
    results = await run_test(pages, running_models)

    # Generate report
    report = generate_report(results, running_models)

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"summary_comparison_{timestamp}.md"
    report_path.write_text(report)
    print(f"\nReport saved to: {report_path}")

    # Save raw results as JSON
    json_path = REPORT_DIR / f"summary_comparison_{timestamp}.json"
    json_path.write_text(json.dumps(results, indent=2))
    print(f"Raw results saved to: {json_path}")

    # Print summary to console
    print("\n" + "=" * 60)
    print(report.split("## Results by Category")[0])  # Print just the summary stats


if __name__ == "__main__":
    asyncio.run(main())
