# Architecture

How the extraction pipeline works.

## Pipeline Overview

```
PDF File
    |
    v
PyMuPDF (page -> image)
    |
    v
Qwen3-VL-235B (visual grounding)
    |
    v
JSON response with bounding boxes
    |
    v
Parse + convert to pixel coordinates
    |
    +---> Crop elements (figures, tables, equations)
    |           |
    |           v (if equation with LaTeX)
    |       pdflatex + ImageMagick -> *_rendered.png
    |
    +---> Annotated page image (boxes drawn)
    |
    v
extraction.json + element images
    |
    v
Enrichment (Qwen3-30B-A3B)
    |
    +---> Generate search_text for each element
    |     (contextual descriptions for retrieval)
    |
    v
Ingestion (ingest_to_db.py)
    |
    +---> Chunk text (~800 chars, 200 overlap)
    +---> Embed chunks + elements (BGE-M3)
    +---> Insert to PostgreSQL + pgvector
    |
    v
Search Service (search_service.py)
    |
    +---> Embed query
    +---> Vector similarity search
    +---> Return ranked chunks + elements
```

## Scripts

### extract_document.py

Interactive extraction for specific pages. Useful for testing and demos.

```bash
python extract_document.py paper.pdf --pages 1,2,3 --output-dir web/data/paper
```

### extract_all_pages.py

Batch extraction for full documents. Resumable, outputs per-page JSON.

```bash
python extract_all_pages.py paper.pdf --name paper --skip-existing
python extract_all_pages.py --list  # Check status
```

### migrate_to_db.py

Converts web/data extractions to db/data structure for database ingestion.

## Output Structure

```
db/data/{document}/
  document.json           # Document metadata
  pages/
    page_001.json         # Per-page: text, elements, timing
    page_002.json
  images/
    page_001.png          # Original page render
    page_001_annotated.png
  elements/
    p01_figure_1_Figure_1.png
    p04_equation_1_Equation_1.png
    p04_equation_1_Equation_1_rendered.png  # Re-rendered from LaTeX
```

## Database Schema

PostgreSQL with pgvector extension.

```
documents: id, slug, title, source_file, extraction_date, model, metadata
pages: id, document_id, page_number, image_path, full_text, width, height
chunks: id, document_id, page_id, content, chunk_index, embedding vector(1024)
elements: id, document_id, page_id, element_type, label, description,
          search_text, latex, crop_path, embedding vector(1024)
```

## Search Flow

```
Query -> Embed (BGE-M3) -> Vector similarity (pgvector)
                               |
                               +---> chunks (text passages)
                               +---> elements (figures, tables, equations)
                               |
                               v
                          Ranked results with scores
```

## Search Scoring

The search uses L2 (Euclidean) distance with BGE-M3 normalized embeddings.

### Distance Ranges

| Query Type | Distance | Score | Description |
|------------|----------|-------|-------------|
| Exact content match | 0.30-0.60 | 100% | Using database content as query |
| Highly specific semantic | 0.75-0.82 | 60-84% | "map projection distortion" |
| Moderately specific | 0.82-0.87 | 43-60% | "Lambert conformal conic equations" |
| General in-domain | 0.87-0.92 | 27-43% | "neural network training" |
| Weak/tangential | 0.92-0.94 | 20-27% | Marginal relevance |
| Out of domain | >1.0 | 0% | "chocolate cake recipe" |

### Score Formula

```python
score_pct = max(0, min(100, (1.0 - distance) / 0.3 * 100))
```

This maps:
- distance <= 0.70 -> 100% (exact/near-exact matches)
- distance 0.70-1.0 -> 100%-0% (linear scale)
- distance >= 1.0 -> 0% (out of domain)

### Threshold

Results with score < 20% (distance > 0.94) are filtered out as they typically match:
- Bibliography/reference sections
- Index entries
- Incidental keyword matches in unrelated contexts

## Servers

| Service | Port | Model |
|---------|------|-------|
| Vision (extraction) | 8090 | Qwen3-VL-235B |
| Text (enrichment) | 8080 | Qwen3-30B-A3B |
| Embedding | 8094 | BGE-M3 |

## Configuration

All settings are managed through `config.py` which loads from multiple sources in order of priority:

1. Environment variables (`OSGEO_*`)
2. `config.local.toml` (gitignored, for local overrides)
3. `config.toml` (gitignored)
4. `~/.config/osgeo-library/config.toml`
5. Built-in defaults

### Quick Setup

```bash
# Copy the example config
cp config.example.toml config.toml

# Edit for your environment
nano config.toml
```

### Configuration Sections

```toml
[llm]
url = "http://localhost:8080/v1/chat/completions"
model = "qwen3-30b"
api_key = ""  # Empty for local, set for OpenRouter
temperature = 0.3
max_tokens = 1024

[embedding]
url = "http://localhost:8094/embedding"
dimensions = 1024

[database]
name = "osgeo_library"
host = ""      # Empty = Unix socket (peer auth)
port = 5432
user = ""      # Empty = current Unix user
password = ""  # Empty = peer auth or ~/.pgpass

[paths]
data_dir = "db/data"  # Relative or absolute path

[display]
chafa_size = "60x25"
```

### Environment Variables

All config values can be overridden with environment variables:

| Variable | Config Key | Description |
|----------|------------|-------------|
| `OSGEO_LLM_URL` | llm.url | LLM API endpoint |
| `OSGEO_LLM_MODEL` | llm.model | Model name |
| `OSGEO_LLM_API_KEY` | llm.api_key | API key for remote services |
| `OSGEO_EMBED_URL` | embedding.url | Embedding server endpoint |
| `OSGEO_EMBED_DIM` | embedding.dimensions | Embedding dimensions |
| `OSGEO_DB_NAME` | database.name | PostgreSQL database |
| `OSGEO_DB_HOST` | database.host | Database host |
| `OSGEO_DB_PORT` | database.port | Database port |
| `OSGEO_DB_USER` | database.user | Database user |
| `OSGEO_DATA_DIR` | paths.data_dir | Path to extracted data |
| `OSGEO_CHAFA_SIZE` | display.chafa_size | Terminal image size |

### Database Authentication

The config supports multiple PostgreSQL authentication methods:

- **Peer auth (default):** Leave `host`, `user`, and `password` empty. Uses Unix socket with current user.
- **Password auth:** Set all fields. Password can also be stored in `~/.pgpass`.
- **Remote connection:** Set `host` to the server address.

### Example Configurations

**Local development (minto):**
```toml
[llm]
url = "http://localhost:8080/v1/chat/completions"
model = "qwen3-30b"

[paths]
data_dir = "db/data"
```

**Remote server with OpenRouter:**
```toml
[llm]
url = "https://openrouter.ai/api/v1/chat/completions"
model = "qwen/qwen3-30b-a3b"
api_key = "sk-or-v1-..."

[paths]
data_dir = "/home/user/data/osgeo-library"
```

### Verify Configuration

```bash
python config.py
```

This displays the current configuration and its source.

## Deployment

### Requirements

- PostgreSQL 17 with pgvector extension
- llama.cpp (for embedding server)
- Python 3.10+ with venv
- chafa (optional, for CLI image preview)

### Server Structure

```
~/
├── github/osgeo-library/           # Code (git repo)
├── data/osgeo-library/
│   ├── alpine_change/elements/     # Element images
│   ├── sam3/elements/
│   ├── usgs_snyder/elements/
│   └── osgeo_library.sql           # Database dump
├── models/
│   └── bge-m3-Q8_0.gguf            # Embedding model (606MB)
└── logs/
```

### Setup Steps

1. **Clone repo and configure:**
```bash
cd ~/github
git clone https://github.com/ominiverdi/osgeo-library.git
cd osgeo-library
cp config.example.toml config.toml

# Edit config.toml to set paths and LLM settings
nano config.toml
```

Example `config.toml` for remote server:
```toml
[llm]
url = "https://openrouter.ai/api/v1/chat/completions"
model = "qwen/qwen3-30b-a3b"
api_key = "sk-or-v1-your-key-here"

[paths]
data_dir = "/home/user/data/osgeo-library"
```

2. **Start embedding server:**
```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/bge-m3-Q8_0.gguf \
  --embedding --host 127.0.0.1 --port 8094 \
  -c 2048 -b 512 -ub 512 -np 1 -t 4
```

3. **Create database (requires pgvector):**
```bash
createdb osgeo_library
psql -d osgeo_library -c "CREATE EXTENSION vector;"
psql -d osgeo_library < ~/data/osgeo-library/osgeo_library.sql
```

4. **Setup Python environment:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests psycopg2-binary langchain langchain-community
```

5. **Run CLI:**
```bash
python chat_cli.py
```

## Client-Server Architecture

For multi-user access, the system uses a client-server model:

```
Users: alice, bob, darkblueb
  |
  +-- osgeo-lib (Rust CLI) --+
                              | HTTP localhost:8095
                              v
  +--------------------------------------------+
  | osgeo-library server (Python FastAPI)      |
  | runs as: ominiverdi                        |
  | owns: config.toml, API keys, DB access     |
  +------+----------------+----------+---------+
         |                |          |
         v                v          v
     BGE-M3:8094     PostgreSQL   OpenRouter API
```

### Components

| Component | Description |
|-----------|-------------|
| `server.py` | FastAPI server with `/search`, `/chat`, `/health` endpoints |
| `clients/rust/` | Lightweight Rust CLI `osgeo-library` (2MB static binary) |
| `servers/start-server.sh` | Startup script for the API server |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server status and dependency checks |
| `/search` | POST | Semantic search over documents |
| `/chat` | POST | Search + LLM-powered response |
| `/element/{id}` | GET | Get element details by ID |

### Server Setup

**Start the server (one-time or testing):**
```bash
./servers/start-server.sh
```

**Auto-start on reboot (cron):**
```bash
crontab -e
# Add this line:
@reboot ~/github/osgeo-library/servers/start-server.sh >> ~/logs/osgeo-library.log 2>&1
```

**Verify:**
```bash
curl http://localhost:8095/health
```

### Rust CLI Installation

**Build from source:**
```bash
cd clients/rust
cargo build --release
sudo cp target/release/osgeo-library /usr/local/bin/
```

**Usage:**
```bash
# Interactive chat (default)
osgeo-library

# Search documents
osgeo-library search "transverse mercator projection"

# One-shot question
osgeo-library ask "What is the UTM projection?"

# Check server status
osgeo-library health
```

### Remote Access (SSH Port Forwarding)

To use the CLI from a remote machine:

```bash
# Set up SSH tunnel (in one terminal)
ssh -L 8095:localhost:8095 osgeo7-gallery

# Run CLI locally (in another terminal)
osgeo-lib
```

**Convenience setup** - add to `~/.ssh/config`:
```
Host osgeo-lib
    HostName osgeo7-gallery
    LocalForward 8095 localhost:8095
```

Then just: `ssh osgeo-lib` and run `osgeo-library` locally.

### Connection Errors

If the server is not accessible, the CLI shows helpful guidance:

```
Error: Could not connect to server at localhost:8095

The osgeo-library server is not running or not accessible.

If you're on the server (osgeo7-gallery):
  - Check if the server is running: systemctl status osgeo-library
  - Start the server: sudo systemctl start osgeo-library

If you're on a remote machine:
  - Set up SSH port forwarding:
    ssh -L 8095:localhost:8095 osgeo7-gallery
```

## Syncing to Remote Server

After extracting new documents locally, sync the database and images to the remote server.

### Quick Reference

```bash
# 1. Backup local database
mkdir -p db_backup
pg_dump osgeo_library > db_backup/osgeo_library_$(date +%Y%m%d).sql

# 2. Backup remote database
ssh osgeo7-gallery "mkdir -p ~/db_backup && pg_dump osgeo_library > ~/db_backup/osgeo_library_\$(date +%Y%m%d).sql"

# 3. Copy and restore database to remote
scp db_backup/osgeo_library_$(date +%Y%m%d).sql osgeo7-gallery:~/db_backup/
ssh osgeo7-gallery "psql -d osgeo_library -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;' && psql -d osgeo_library < ~/db_backup/osgeo_library_$(date +%Y%m%d).sql"

# 4. Sync element images
rsync -avz --progress db/data/ osgeo7-gallery:~/data/osgeo-library/
```

### Full Extraction Pipeline

For processing a new PDF end-to-end:

```bash
# 1. Extract (requires vision model on port 8090)
python extract_all_pages.py pdfs/document.pdf --name doc_name --skip-existing

# 2. Enrich (requires text model on port 8080)
python enrich_elements.py doc_name

# 3. Ingest to database (requires embedding server on port 8094)
python ingest_to_db.py doc_name

# 4. Sync to remote (see Quick Reference above)
```

