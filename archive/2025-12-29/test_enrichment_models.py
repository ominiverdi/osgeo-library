#!/usr/bin/env python3
"""
Compare enrichment quality between different LLM models.

Usage:
    # Start model on port 8080, then:
    python test_enrichment_models.py --model qwen3-30b

    # Switch model, then:
    python test_enrichment_models.py --model mistral-small

    # Compare results:
    python test_enrichment_models.py --compare
"""

import argparse
import json
import time
from pathlib import Path
from openai import OpenAI

LLM_URL = "http://localhost:8080/v1"
RESULTS_DIR = Path("enrichment_comparison")

ENRICHMENT_PROMPT = """/no_think
Page content:
{page_text}

Element: {element_type} "{label}"
Extracted: {description}

What does this element explain in this context? List key search terms. 2-3 sentences, no filler."""


# Sample elements for testing (mix of types)
TEST_SAMPLES = [
    # Equation from usgs_snyder
    {
        "doc": "usgs_snyder",
        "page": 147,
        "type": "equation",
        "label": "Equation 18-37 to 18-40",
    },
    # Figure from alpine_change
    {
        "doc": "alpine_change",
        "page": 6,
        "type": "figure",
        "label": "Figure 1",
    },
    # Table from sam3
    {
        "doc": "sam3",
        "page": 7,
        "type": "table",
        "label": "Table 1",
    },
]


def load_element(doc: str, page: int, label: str) -> dict | None:
    """Load element data from extraction."""
    page_file = Path(f"db/data/{doc}/pages/page_{page:03d}.json")
    if not page_file.exists():
        print(f"Page file not found: {page_file}")
        return None

    with open(page_file) as f:
        data = json.load(f)

    for el in data.get("elements", []):
        if el.get("label") == label:
            return {
                "element": el,
                "page_text": data.get("text", "")[:3000],
            }

    print(f"Element not found: {label} on page {page}")
    return None


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> tags from output."""
    import re

    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def enrich_element(client, element: dict, page_text: str) -> tuple[str, float]:
    """Generate enrichment and return (text, time_seconds)."""
    prompt = ENRICHMENT_PROMPT.format(
        element_type=element.get("type", "element"),
        label=element.get("label", "Unknown"),
        description=element.get("description", ""),
        page_text=page_text,
    )

    start = time.time()
    try:
        response = client.chat.completions.create(
            model="test",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        elapsed = time.time() - start
        result = strip_think_tags(response.choices[0].message.content.strip())
        return result, elapsed
    except Exception as e:
        return f"ERROR: {e}", time.time() - start


def run_test(model_name: str):
    """Run enrichment test on sample elements."""
    print(f"\nTesting model: {model_name}")
    print("=" * 60)

    client = OpenAI(base_url=LLM_URL, api_key="not-needed")

    # Check server
    try:
        client.models.list()
    except Exception as e:
        print(f"ERROR: Cannot connect to server at {LLM_URL}")
        print(f"  {e}")
        return

    results = {
        "model": model_name,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "samples": [],
    }

    total_time = 0

    for sample in TEST_SAMPLES:
        print(f"\n--- {sample['doc']} / {sample['label']} ---")

        data = load_element(sample["doc"], sample["page"], sample["label"])
        if not data:
            continue

        element = data["element"]
        page_text = data["page_text"]

        print(f"Type: {element.get('type')}")
        print(f"Description: {element.get('description', '')[:100]}...")

        enriched, elapsed = enrich_element(client, element, page_text)
        total_time += elapsed

        print(f"Time: {elapsed:.1f}s")
        print(f"Enriched:\n{enriched}")

        results["samples"].append(
            {
                "doc": sample["doc"],
                "page": sample["page"],
                "label": sample["label"],
                "type": element.get("type"),
                "original_description": element.get("description", "")[:200],
                "enriched": enriched,
                "time_seconds": elapsed,
            }
        )

    results["total_time"] = total_time
    results["avg_time"] = (
        total_time / len(results["samples"]) if results["samples"] else 0
    )

    # Save results
    RESULTS_DIR.mkdir(exist_ok=True)
    output_file = RESULTS_DIR / f"{model_name}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Total time: {total_time:.1f}s")
    print(f"Average: {results['avg_time']:.1f}s per element")
    print(f"Results saved to: {output_file}")


def compare_results():
    """Compare results from different models."""
    print("\nComparison of Enrichment Models")
    print("=" * 60)

    results_files = list(RESULTS_DIR.glob("*.json"))
    if not results_files:
        print("No results found. Run tests first.")
        return

    all_results = []
    for f in results_files:
        with open(f) as fp:
            all_results.append(json.load(fp))

    # Summary table
    print(f"\n{'Model':<20} {'Avg Time':<12} {'Total Time':<12}")
    print("-" * 44)
    for r in all_results:
        print(f"{r['model']:<20} {r['avg_time']:.1f}s{'':<8} {r['total_time']:.1f}s")

    # Side by side comparison
    print("\n\nSide-by-side Comparison:")
    print("=" * 60)

    for i, sample in enumerate(TEST_SAMPLES):
        print(f"\n--- {sample['label']} ({sample['doc']}) ---\n")

        for r in all_results:
            if i < len(r["samples"]):
                s = r["samples"][i]
                print(f"[{r['model']}] ({s['time_seconds']:.1f}s):")
                print(f"{s['enriched'][:300]}...")
                print()


def main():
    parser = argparse.ArgumentParser(description="Compare enrichment models")
    parser.add_argument("--model", help="Model name for test run")
    parser.add_argument("--compare", action="store_true", help="Compare saved results")

    args = parser.parse_args()

    if args.compare:
        compare_results()
    elif args.model:
        run_test(args.model)
    else:
        parser.print_help()
        print("\nExample workflow:")
        print("  1. Start qwen3-30b on port 8080")
        print("  2. python test_enrichment_models.py --model qwen3-30b")
        print("  3. Stop qwen3-30b, start mistral-small on port 8080")
        print("  4. python test_enrichment_models.py --model mistral-small")
        print("  5. python test_enrichment_models.py --compare")


if __name__ == "__main__":
    main()
