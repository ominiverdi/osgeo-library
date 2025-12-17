#!/usr/bin/env python3
"""
Configuration management for OSGeo Library.

Loads configuration from (in order of priority):
1. Environment variables (OSGEO_*)
2. Config file (~/.config/osgeo-library/config.toml or ./config.toml)
3. Default values

Usage:
    from config import config

    print(config.llm_url)
    print(config.embed_url)
    print(config.data_dir)

Environment variables:
    OSGEO_LLM_URL         - LLM API endpoint
    OSGEO_LLM_MODEL       - Model name for chat
    OSGEO_LLM_API_KEY     - API key (for OpenRouter, etc.)
    OSGEO_EMBED_URL       - Embedding server endpoint
    OSGEO_EMBED_DIM       - Embedding dimensions
    OSGEO_DATA_DIR        - Path to extracted data (elements, images)
    OSGEO_DB_NAME         - PostgreSQL database name
    OSGEO_DB_HOST         - Database host (empty for Unix socket/peer auth)
    OSGEO_DB_PORT         - Database port
    OSGEO_DB_USER         - Database user (empty for current Unix user)
    OSGEO_CHAFA_SIZE      - Terminal image preview size
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Try to import toml, fall back gracefully
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore  # pip install tomli for Python < 3.11
    except ImportError:
        tomllib = None  # type: ignore


@dataclass
class Config:
    """Configuration container with defaults."""

    # LLM settings
    llm_url: str = "http://localhost:8080/v1/chat/completions"
    llm_model: str = "qwen3-30b"
    llm_api_key: str = ""  # Empty for local, set for OpenRouter
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024

    # Embedding server
    embed_url: str = "http://localhost:8094/embedding"
    embed_health_url: str = "http://localhost:8094/health"
    embed_dimensions: int = 1024

    # Database (empty values = peer authentication)
    db_name: str = "osgeo_library"
    db_host: str = ""  # Empty for Unix socket
    db_port: str = "5432"
    db_user: str = ""  # Empty for current Unix user
    db_password: str = ""  # Empty for peer auth / .pgpass

    # Paths
    data_dir: str = "db/data"  # Relative to repo root, or absolute

    # Display - chafa terminal image sizes
    chafa_size: str = "80x35"  # Default for figures/diagrams
    chafa_size_equation: str = "100x20"  # Wider for equations (usually horizontal)
    chafa_size_table: str = "100x40"  # Larger for tables

    # Metadata
    config_source: str = "defaults"


def find_config_file() -> Optional[Path]:
    """Find config file in standard locations."""
    locations = [
        Path("config.toml"),  # Current directory
        Path("config.local.toml"),  # Local override (gitignored)
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

            # Embedding section
            if "embedding" in data:
                emb = data["embedding"]
                config.embed_url = emb.get("url", config.embed_url)
                if "url" in emb:
                    # Derive health URL from embedding URL
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
                config.data_dir = paths.get("data_dir", config.data_dir)

            # Display section
            if "display" in data:
                display = data["display"]
                config.chafa_size = display.get("chafa_size", config.chafa_size)
                config.chafa_size_equation = display.get(
                    "chafa_size_equation", config.chafa_size_equation
                )
                config.chafa_size_table = display.get(
                    "chafa_size_table", config.chafa_size_table
                )

            config.config_source = str(config_file)

        except Exception as e:
            print(f"Warning: Failed to load config from {config_file}: {e}")

    # Environment variables override file config
    env_mappings = {
        "OSGEO_LLM_URL": "llm_url",
        "OSGEO_LLM_MODEL": "llm_model",
        "OSGEO_LLM_API_KEY": "llm_api_key",
        "OSGEO_EMBED_URL": "embed_url",
        "OSGEO_EMBED_DIM": "embed_dimensions",
        "OSGEO_DATA_DIR": "data_dir",
        "OSGEO_DB_NAME": "db_name",
        "OSGEO_DB_HOST": "db_host",
        "OSGEO_DB_PORT": "db_port",
        "OSGEO_DB_USER": "db_user",
        "OSGEO_DB_PASSWORD": "db_password",
        "OSGEO_CHAFA_SIZE": "chafa_size",
    }

    for env_var, attr in env_mappings.items():
        value = os.environ.get(env_var)
        if value is not None:
            # Handle type conversion
            if attr == "embed_dimensions":
                value = int(value)
            setattr(config, attr, value)
            if config.config_source == "defaults":
                config.config_source = "environment"

    # Derive health URL if embed_url was set via env
    if os.environ.get("OSGEO_EMBED_URL"):
        base = config.embed_url.rsplit("/", 1)[0]
        config.embed_health_url = f"{base}/health"

    return config


# Global config instance - loaded once at import
config = load_config()


# --- CLI for testing ---

if __name__ == "__main__":
    import sys

    print("OSGeo Library Configuration")
    print("=" * 50)
    print(f"Config source: {config.config_source}")
    print()

    print("[LLM]")
    print(f"  url: {config.llm_url}")
    print(f"  model: {config.llm_model}")
    print(f"  api_key: {'***' if config.llm_api_key else '(not set)'}")
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
    print(f"  password: {'***' if config.db_password else '(peer auth / .pgpass)'}")
    print()

    print("[Paths]")
    print(f"  data_dir: {config.data_dir}")
    print()

    print("[Display]")
    print(f"  chafa_size: {config.chafa_size}")
    print(f"  chafa_size_equation: {config.chafa_size_equation}")
    print(f"  chafa_size_table: {config.chafa_size_table}")
