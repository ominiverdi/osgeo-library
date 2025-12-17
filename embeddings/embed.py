#!/usr/bin/env python3
"""
Embedding generation using BGE-M3 via llama.cpp server.

Model: BAAI/bge-m3 (568M params, 1024 dimensions)
Server: llama.cpp with --embedding flag on port 8094

Usage:
    from embeddings.embed import get_embedding, get_embeddings

    # Single text
    embedding = get_embedding("Map projection equations")

    # Batch (more efficient)
    embeddings = get_embeddings(["text1", "text2", "text3"])
"""

import requests
from typing import List, Optional
import time
import sys
import os

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

MAX_RETRIES = 3
RETRY_DELAY = 1.0


def get_embedding(text: str, normalize: bool = True) -> Optional[List[float]]:
    """
    Get embedding for a single text string.

    Args:
        text: Input text to embed
        normalize: Whether to L2-normalize the embedding (default True)

    Returns:
        List of floats (1024 dimensions) or None on error
    """
    embeddings = get_embeddings([text], normalize=normalize)
    return embeddings[0] if embeddings else None


def get_embeddings(
    texts: List[str], normalize: bool = True
) -> Optional[List[List[float]]]:
    """
    Get embeddings for multiple texts in a single request.

    Args:
        texts: List of input texts to embed
        normalize: Whether to L2-normalize embeddings (default True)

    Returns:
        List of embeddings (each 1024 dimensions) or None on error
    """
    if not texts:
        return []

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                config.embed_url,
                json={"input": texts},
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            response.raise_for_status()

            data = response.json()

            # llama.cpp returns: [{"index": 0, "embedding": [[...]]}, ...]
            embeddings = []
            for item in data:
                emb = item["embedding"]
                # Handle nested list format
                if isinstance(emb[0], list):
                    emb = emb[0]

                if normalize:
                    emb = l2_normalize(emb)

                embeddings.append(emb)

            return embeddings

        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                print(f"Embedding request failed (attempt {attempt + 1}): {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"Embedding request failed after {MAX_RETRIES} attempts: {e}")
                return None
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error parsing embedding response: {e}")
            return None


def l2_normalize(vec: List[float]) -> List[float]:
    """L2 normalize a vector."""
    import math

    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def check_server() -> bool:
    """Check if embedding server is running."""
    try:
        response = requests.get(config.embed_health_url, timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


# --- CLI for testing ---

if __name__ == "__main__":
    import sys

    if not check_server():
        print("ERROR: Embedding server not running on port 8094")
        print("Start it with: /media/nvme2g-a/llm_toolbox/servers/bge-m3-embed-8094.sh")
        sys.exit(1)

    # Test embeddings
    test_texts = [
        "Map projection equations for geographic coordinate systems",
        "The Oblique Mercator projection transforms coordinates using spherical trigonometry",
        "Machine learning models for image segmentation",
    ]

    print("Testing BGE-M3 embeddings...")
    print(f"Server: {config.embed_url}")
    print(f"Expected dimensions: {config.embed_dimensions}")
    print()

    start = time.time()
    embeddings = get_embeddings(test_texts)
    elapsed = time.time() - start

    if embeddings:
        print(f"Generated {len(embeddings)} embeddings in {elapsed:.2f}s")
        print(f"Dimensions: {len(embeddings[0])}")
        print()

        # Show similarity matrix
        print("Cosine similarity matrix:")
        for i, text_i in enumerate(test_texts):
            for j, text_j in enumerate(test_texts):
                sim = cosine_similarity(embeddings[i], embeddings[j])
                print(f"  [{i}][{j}]: {sim:.3f}", end="")
            print()

        print()
        print("Texts:")
        for i, text in enumerate(test_texts):
            print(f"  [{i}]: {text[:60]}...")
    else:
        print("ERROR: Failed to generate embeddings")
        sys.exit(1)
