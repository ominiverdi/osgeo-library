# OSGeo Library

Extract figures, tables, and equations from geospatial research PDFs using vision-language models, then search them with semantic embeddings.

![CLI Demo - semantic search with terminal preview and GUI viewer](docs/images/cli-demo-1.png)

*Semantic search for "Alpine Habitat" with terminal preview (`show`) and GUI viewer (`open`)*

## Quick Start

```bash
# 1. Configure (copy and edit for your environment)
cp config.example.toml config.toml
nano config.toml

# 2. Start model server (requires Qwen3-VL-235B for extraction)
# See docs/ARCHITECTURE.md for setup

# 3. Extract pages
python extract_document.py paper.pdf --pages 1,2,3 --output-dir web/data/paper

# 4. View results
cd web && python -m http.server 8080

# 5. Or use the chat CLI (requires embedding server + LLM)
python chat_cli.py
```

## Configuration

Settings are loaded from `config.toml` (copy from `config.example.toml`).

Key settings:
- **LLM:** Local llama.cpp server or OpenRouter API
- **Embedding:** BGE-M3 server for semantic search
- **Database:** PostgreSQL with pgvector (peer auth supported)
- **Paths:** Data directory (no symlinks needed)

See [ARCHITECTURE.md](docs/ARCHITECTURE.md#configuration) for full details.

## Documentation

- [CHANGELOG](docs/CHANGELOG.md) - What changed when
- [ARCHITECTURE](docs/ARCHITECTURE.md) - How the pipeline works, configuration
- [EXTRACTIONS](docs/EXTRACTIONS.md) - Catalog of processed documents
- [DECISIONS](docs/DECISIONS.md) - Technical decisions and alternatives

## Dependencies

**Python:** PyMuPDF, Pillow, openai, requests, psycopg2-binary

**System:** texlive (pdflatex), imagemagick, chafa (optional, for CLI image preview)

**Models:** 
- Qwen3-VL-235B (extraction) via llama.cpp
- Qwen3-30B (chat) via llama.cpp or OpenRouter
- BGE-M3 (embeddings) via llama.cpp

## Author

Lorenzo Becchi

## License

MIT
