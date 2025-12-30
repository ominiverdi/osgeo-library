"""Unit tests for doclibrary.config module."""

import os
import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile


class TestConfig:
    """Tests for configuration loading."""

    def test_default_values(self, monkeypatch):
        """Should have sensible defaults."""
        # Clear any env vars that might override
        for key in list(os.environ.keys()):
            if key.startswith("DOCLIBRARY_"):
                monkeypatch.delenv(key, raising=False)

        # Force reimport to get fresh config
        import importlib
        import doclibrary.config

        importlib.reload(doclibrary.config)

        config = doclibrary.config.config

        # Check defaults exist
        assert config.llm_url is not None
        assert config.embed_url is not None
        assert config.db_name is not None

    def test_env_override(self, monkeypatch):
        """Should override defaults with environment variables."""
        monkeypatch.setenv("DOCLIBRARY_DB_NAME", "test_db")
        monkeypatch.setenv("DOCLIBRARY_LLM_MODEL", "test-model")

        # Reimport to pick up new env vars
        import importlib
        import doclibrary.config

        importlib.reload(doclibrary.config)

        config = doclibrary.config.config

        assert config.db_name == "test_db"
        assert config.llm_model == "test-model"

    def test_embed_dimensions_as_int(self, monkeypatch):
        """Should convert DOCLIBRARY_EMBED_DIM to integer."""
        monkeypatch.setenv("DOCLIBRARY_EMBED_DIM", "512")

        import importlib
        import doclibrary.config

        importlib.reload(doclibrary.config)

        config = doclibrary.config.config

        assert config.embed_dimensions == 512
        assert isinstance(config.embed_dimensions, int)


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_finds_local_config(self, tmp_path, monkeypatch):
        """Should find config.toml in current directory."""
        # Create a temp config file
        config_file = tmp_path / "config.toml"
        config_file.write_text('[llm]\nmodel = "test"\n')

        monkeypatch.chdir(tmp_path)

        from doclibrary.config import find_config_file

        found = find_config_file()

        assert found is not None
        assert found.name == "config.toml"

    def test_prefers_local_override(self, tmp_path, monkeypatch):
        """Should prefer config.local.toml over config.toml."""
        # Create both files
        (tmp_path / "config.toml").write_text('[llm]\nmodel = "base"\n')
        (tmp_path / "config.local.toml").write_text('[llm]\nmodel = "local"\n')

        monkeypatch.chdir(tmp_path)

        from doclibrary.config import find_config_file

        found = find_config_file()

        assert found is not None
        assert found.name == "config.local.toml"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_loads_from_toml(self, tmp_path, monkeypatch):
        """Should load config from TOML file."""
        config_content = """
[llm]
url = "http://test:8080/v1"
model = "test-llm"

[database]
name = "test_db"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)

        monkeypatch.chdir(tmp_path)
        # Clear env vars
        for key in list(os.environ.keys()):
            if key.startswith("DOCLIBRARY_"):
                monkeypatch.delenv(key, raising=False)

        from doclibrary.config import load_config

        config = load_config()

        assert config.llm_url == "http://test:8080/v1"
        assert config.llm_model == "test-llm"
        assert config.db_name == "test_db"

    def test_env_overrides_file(self, tmp_path, monkeypatch):
        """Environment variables should override file config."""
        config_content = """
[llm]
model = "file-model"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DOCLIBRARY_LLM_MODEL", "env-model")

        from doclibrary.config import load_config

        config = load_config()

        assert config.llm_model == "env-model"

    def test_tracks_config_source(self, tmp_path, monkeypatch):
        """Should track where config was loaded from."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[llm]\nmodel = "test"\n')

        monkeypatch.chdir(tmp_path)
        for key in list(os.environ.keys()):
            if key.startswith("DOCLIBRARY_"):
                monkeypatch.delenv(key, raising=False)

        from doclibrary.config import load_config

        config = load_config()

        assert "config.toml" in config.config_source
