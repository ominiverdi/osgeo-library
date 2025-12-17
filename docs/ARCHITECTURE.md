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

## Servers

| Service | Port | Model |
|---------|------|-------|
| Vision (extraction) | 8090 | Qwen3-VL-235B |
| Text (enrichment) | 8080 | Qwen3-30B-A3B |
| Embedding | 8094 | BGE-M3 |

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
│   └── db/data -> ~/data/osgeo-library  # Symlink to data
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

1. **Clone repo and create symlink:**
```bash
cd ~/github
git clone https://github.com/ominiverdi/osgeo-library.git
cd osgeo-library
mkdir -p db
ln -sf ~/data/osgeo-library db/data
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

