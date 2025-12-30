# doclibrary

Extract figures, tables, diagrams, and equations from scientific PDFs using vision-language models, then search them with semantic embeddings.

![CLI Demo - semantic search with terminal preview and GUI viewer](docs/images/cli-demo-1.png)

*Semantic search for "Alpine Habitat" with terminal preview (`show`) and GUI viewer (`open`)*

## Overview

This project provides two main capabilities:

1. **Extraction** - Convert PDF pages to images, detect visual elements (figures, tables, equations) with bounding boxes, crop them, and generate structured JSON
2. **Semantic Search** - Store extracted content in PostgreSQL with vector embeddings, then search using natural language via CLI, REST API, or MCP server

## Installation

```bash
git clone https://github.com/ominiverdi/osgeo-library.git
cd osgeo-library
pip install -e .
```

**With development dependencies:**
```bash
pip install -e ".[dev]"
```

**With MCP server support (for Claude Desktop):**
```bash
pip install -e ".[mcp]"
```

**System dependencies:**

```bash
# Debian/Ubuntu
sudo apt install texlive-latex-base imagemagick chafa

# texlive - LaTeX rendering for equations
# imagemagick - PDF to PNG conversion  
# chafa - Terminal image preview (optional)
```

## Quick Start

### 1. Configure

```bash
cp config.example.toml config.toml
# Edit config.toml with your LLM and database settings
```

Or use environment variables:
```bash
export DOCLIBRARY_LLM_URL="http://localhost:8080/v1/chat/completions"
export DOCLIBRARY_EMBED_URL="http://localhost:8094/embedding"
export DOCLIBRARY_DB_NAME="osgeo_library"
```

### 2. Initialize Database

```bash
createdb osgeo_library
psql osgeo_library < doclibrary/db/schema.sql
```

### 3. Extract a PDF

```bash
doclibrary extract paper.pdf --pages 1-10 --output-dir data/paper
```

### 4. Enrich with Search Text

```bash
doclibrary enrich paper
```

### 5. Ingest into Database

```bash
doclibrary ingest paper
```

### 6. Start the Chat CLI

```bash
doclibrary chat
```

## CLI Commands

The `doclibrary` CLI provides these subcommands:

```bash
doclibrary extract   # Extract elements from PDF
doclibrary enrich    # Generate search_text for elements
doclibrary ingest    # Ingest documents into PostgreSQL database
doclibrary search    # Search from command line
doclibrary chat      # Interactive chat interface
doclibrary serve     # Start REST API server
doclibrary mcp       # Start MCP server (for Claude Desktop)
doclibrary config    # Show current configuration
```

### Chat Commands

Inside the chat interface:
- `show N` - Preview element N in terminal (using chafa)
- `open N` - Open element N in GUI viewer
- `sources` - List sources from last answer
- `help` - Show all commands

![CLI Demo - equation search and rendered LaTeX](docs/images/cli-demo-2.png)

*Follow-up query for equations with rendered LaTeX preview*

## Extraction Pipeline

Extract visual elements from PDF pages using a vision-language model.

**Requirements:**
- Vision-language model with OpenAI-compatible API and bounding box support
- Tested with Qwen2-VL-7B and Qwen3-VL via llama.cpp

**Extract pages:**
```bash
doclibrary extract paper.pdf --pages 1,2,3,4,5 --output-dir data/paper
```

**Output structure:**
```
data/paper/
  extraction.json           # Structured data with bounding boxes
  page_01.png               # Page images
  page_01_annotated.png     # With element boxes drawn
  elements/
    p01_figure_1_Figure_1.png
    p02_table_1_Table_1.png
    p03_equation_1_Equation_1.png
    p03_equation_1_Equation_1_rendered.png  # LaTeX rendered
```

**View results** in the web viewer:
```bash
cd web && python -m http.server 8000
# Open http://localhost:8000
```

## API Server

Start the REST API:
```bash
doclibrary serve --port 8000
```

Endpoints:
- `GET /search?q=query` - Semantic search
- `GET /documents` - List documents
- `GET /elements/{id}` - Get element details
- `GET /health` - Health check

See [docs/API.md](docs/API.md) for full API documentation.

## MCP Server (Claude Desktop)

Start the MCP server for Claude Desktop integration:
```bash
doclibrary mcp
```

Or configure in `~/.config/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "doclibrary": {
      "command": "doclibrary",
      "args": ["mcp"]
    }
  }
}
```

Available tools:
- `search_documents` - Semantic search over document library
- `search_visual_elements` - Search figures, tables, equations
- `get_element_details` - Get element by ID
- `list_documents` - List available documents

## Configuration

Settings are loaded from (in priority order):
1. Environment variables (`DOCLIBRARY_*`)
2. `config.local.toml` (gitignored)
3. `config.toml`
4. `~/.config/doclibrary/config.toml`

Key settings:
- **LLM:** Local llama.cpp server or OpenRouter API
- **Vision LLM:** For PDF extraction (Qwen2-VL recommended)
- **Embedding:** BGE-M3 server for semantic search
- **Database:** PostgreSQL with pgvector

```bash
# Show current configuration
doclibrary config
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full configuration details.

## Development

### Running Tests

```bash
# Unit tests only (no external dependencies)
pytest tests/unit/ -v

# All tests including integration (requires postgres, embedding server)
pytest tests/ --run-integration

# With coverage
pytest tests/unit/ --cov=doclibrary --cov-report=term-missing
```

### Package Structure

```
doclibrary/
  cli.py              # Main CLI entry point
  config.py           # Configuration management
  core/               # Shared utilities (LLM, text, formatting)
  db/                 # Database operations, chunking
  search/             # Embedding and search service
  extraction/         # PDF extraction, enrichment
  chat/               # Interactive chat interface
  servers/            # REST API and MCP server
```

## Documentation

- [ARCHITECTURE](docs/ARCHITECTURE.md) - System design and configuration
- [EXTRACTION](docs/EXTRACTION.md) - Extraction pipeline details
- [API](docs/API.md) - REST API reference
- [DECISIONS](docs/DECISIONS.md) - Technical decisions and alternatives
- [CHANGELOG](docs/CHANGELOG.md) - Version history

## Author

Lorenzo Becchi

## License

MIT
