#!/usr/bin/env python3
"""
Configuration management for doclibrary.

Loads configuration from (in order of priority):
1. Environment variables (DOCLIBRARY_*)
2. Config file (~/.config/doclibrary/config.toml or ./config.toml)
3. Default values (minimal, require config file for full functionality)

Usage:
    from doclibrary.config import config

    print(config.llm_url)
    print(config.embed_url)
    print(config.data_dir)

Environment variables:
    DOCLIBRARY_LLM_URL          - LLM API endpoint
    DOCLIBRARY_LLM_MODEL        - Model name for chat
    DOCLIBRARY_LLM_API_KEY      - API key (for OpenRouter, etc.)
    DOCLIBRARY_VISION_LLM_URL   - Vision LLM endpoint (extraction)
    DOCLIBRARY_VISION_LLM_MODEL - Vision model name
    DOCLIBRARY_EMBED_URL        - Embedding server endpoint
    DOCLIBRARY_EMBED_DIM        - Embedding dimensions
    DOCLIBRARY_DATA_DIR         - Path to extracted data
    DOCLIBRARY_DB_NAME          - PostgreSQL database name
    DOCLIBRARY_DB_HOST          - Database host
    DOCLIBRARY_DB_PORT          - Database port
    DOCLIBRARY_DB_USER          - Database user
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Try to import toml, fall back gracefully
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


@dataclass
class Config:
    """Configuration container.

    Values are loaded from config.toml file. Environment variables can override.
    """

    # LLM settings (chat/search)
    llm_url: str = "http://localhost:8080/v1/chat/completions"
    llm_model: str = "qwen3-30b"
    llm_api_key: str = ""
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024

    # Vision LLM (extraction)
    vision_llm_url: str = "http://localhost:8090/v1"
    vision_llm_model: str = "qwen2-vl-7b"

    # Enrichment LLM (search_text generation)
    enrichment_llm_url: str = "http://localhost:8080/v1"
    enrichment_llm_model: str = "qwen3-30b"

    # Embedding server
    embed_url: str = "http://localhost:8094/embedding"
    embed_health_url: str = "http://localhost:8094/health"
    embed_dimensions: int = 1024

    # Database
    db_name: str = "osgeo_library"
    db_host: str = ""  # Empty for Unix socket
    db_port: str = "5432"
    db_user: str = ""  # Empty for current user
    db_password: str = ""  # Empty for peer auth

    # Paths
    data_dir: str = "db/data"
    cache_dir: str = "/tmp/doclibrary_cache"  # For chat bridge image caching

    # Display (chafa terminal preview)
    chafa_size: str = "80x35"
    chafa_size_equation: str = "100x20"
    chafa_size_table: str = "100x40"

    # Metadata
    config_source: str = "defaults"


def get_package_root() -> Path:
    """Get the root directory of the osgeo-library package."""
    # This file is at doclibrary/config.py, so parent.parent is repo root
    return Path(__file__).parent.parent.resolve()


def find_config_file() -> Optional[Path]:
    """Find config file in standard locations."""
    package_root = get_package_root()

    locations = [
        Path("config.local.toml"),  # Local override (gitignored)
        Path("config.toml"),  # Current directory
        package_root / "config.local.toml",  # Package root local override
        package_root / "config.toml",  # Package root
        Path.home() / ".config" / "doclibrary" / "config.toml",
        # Legacy location for backward compatibility
        Path.home() / ".config" / "osgeo-library" / "config.toml",
    ]

    for path in locations:
        if path.exists():
            return path
    return None


def load_config() -> Config:
    """Load configuration from file and environment."""
    config = Config()

    # Load from TOML file if available
    config_file = find_config_file()
    if config_file and tomllib:
        try:
            with open(config_file, "rb") as f:
                data = tomllib.load(f)

            # LLM section
            if "llm" in data:
                llm = data["llm"]
                config.llm_url = llm.get("url", config.llm_url)
                config.llm_model = llm.get("model", config.llm_model)
                config.llm_api_key = llm.get("api_key", config.llm_api_key)
                config.llm_temperature = llm.get("temperature", config.llm_temperature)
                config.llm_max_tokens = llm.get("max_tokens", config.llm_max_tokens)

            # Vision LLM section
            if "vision_llm" in data:
                vision = data["vision_llm"]
                config.vision_llm_url = vision.get("url", config.vision_llm_url)
                config.vision_llm_model = vision.get("model", config.vision_llm_model)

            # Enrichment LLM section
            if "enrichment_llm" in data:
                enrich = data["enrichment_llm"]
                config.enrichment_llm_url = enrich.get("url", config.enrichment_llm_url)
                config.enrichment_llm_model = enrich.get("model", config.enrichment_llm_model)

            # Embedding section
            if "embedding" in data:
                emb = data["embedding"]
                config.embed_url = emb.get("url", config.embed_url)
                if "url" in emb:
                    base = emb["url"].rsplit("/", 1)[0]
                    config.embed_health_url = f"{base}/health"
                config.embed_dimensions = emb.get("dimensions", config.embed_dimensions)

            # Database section
            if "database" in data:
                db = data["database"]
                config.db_name = db.get("name", config.db_name)
                config.db_host = db.get("host", config.db_host)
                config.db_port = str(db.get("port", config.db_port))
                config.db_user = db.get("user", config.db_user)
                config.db_password = db.get("password", config.db_password)

            # Paths section
            if "paths" in data:
                paths = data["paths"]
                data_dir = paths.get("data_dir", config.data_dir)
                # Resolve relative paths based on config file location
                data_dir_path = Path(data_dir)
                if not data_dir_path.is_absolute():
                    data_dir_path = (config_file.parent / data_dir_path).resolve()
                config.data_dir = str(data_dir_path)
                # Cache dir for chat bridges
                if "cache_dir" in paths:
                    config.cache_dir = paths["cache_dir"]

            # Display section
            if "display" in data:
                display = data["display"]
                config.chafa_size = display.get("chafa_size", config.chafa_size)
                config.chafa_size_equation = display.get(
                    "chafa_size_equation", config.chafa_size_equation
                )
                config.chafa_size_table = display.get("chafa_size_table", config.chafa_size_table)

            config.config_source = str(config_file)

        except Exception as e:
            print(f"Warning: Failed to load config from {config_file}: {e}", file=sys.stderr)

    # Environment variables override file config
    env_mappings = {
        "DOCLIBRARY_LLM_URL": "llm_url",
        "DOCLIBRARY_LLM_MODEL": "llm_model",
        "DOCLIBRARY_LLM_API_KEY": "llm_api_key",
        "DOCLIBRARY_VISION_LLM_URL": "vision_llm_url",
        "DOCLIBRARY_VISION_LLM_MODEL": "vision_llm_model",
        "DOCLIBRARY_ENRICHMENT_LLM_URL": "enrichment_llm_url",
        "DOCLIBRARY_ENRICHMENT_LLM_MODEL": "enrichment_llm_model",
        "DOCLIBRARY_EMBED_URL": "embed_url",
        "DOCLIBRARY_EMBED_DIM": "embed_dimensions",
        "DOCLIBRARY_DATA_DIR": "data_dir",
        "DOCLIBRARY_CACHE_DIR": "cache_dir",
        "DOCLIBRARY_DB_NAME": "db_name",
        "DOCLIBRARY_DB_HOST": "db_host",
        "DOCLIBRARY_DB_PORT": "db_port",
        "DOCLIBRARY_DB_USER": "db_user",
        "DOCLIBRARY_DB_PASSWORD": "db_password",
        "DOCLIBRARY_CHAFA_SIZE": "chafa_size",
    }

    for env_var, attr in env_mappings.items():
        value = os.environ.get(env_var)
        if value is not None:
            if attr == "embed_dimensions":
                value = int(value)
            setattr(config, attr, value)
            if config.config_source == "defaults":
                config.config_source = "environment"

    # Derive health URL if embed_url was set via env
    if os.environ.get("DOCLIBRARY_EMBED_URL"):
        base = config.embed_url.rsplit("/", 1)[0]
        config.embed_health_url = f"{base}/health"

    return config


# Global config instance - loaded once at import
config = load_config()


# --- CLI for testing ---

if __name__ == "__main__":
    print("doclibrary Configuration")
    print("=" * 50)
    print(f"Config source: {config.config_source}")
    print()

    print("[LLM - Chat/Search]")
    print(f"  url: {config.llm_url}")
    print(f"  model: {config.llm_model}")
    print(f"  api_key: {'***' if config.llm_api_key else '(not set)'}")
    print()

    print("[Vision LLM - Extraction]")
    print(f"  url: {config.vision_llm_url}")
    print(f"  model: {config.vision_llm_model}")
    print()

    print("[Enrichment LLM]")
    print(f"  url: {config.enrichment_llm_url}")
    print(f"  model: {config.enrichment_llm_model}")
    print()

    print("[Embedding]")
    print(f"  url: {config.embed_url}")
    print(f"  dimensions: {config.embed_dimensions}")
    print()

    print("[Database]")
    print(f"  name: {config.db_name}")
    print(f"  host: {config.db_host or '(Unix socket)'}")
    print(f"  port: {config.db_port}")
    print(f"  user: {config.db_user or '(current user)'}")
    print()

    print("[Paths]")
    print(f"  data_dir: {config.data_dir}")
    print(f"  cache_dir: {config.cache_dir}")
    print()

    print("[Display]")
    print(f"  chafa_size: {config.chafa_size}")
    print(f"  chafa_size_equation: {config.chafa_size_equation}")
    print(f"  chafa_size_table: {config.chafa_size_table}")
