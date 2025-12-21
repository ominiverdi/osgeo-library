# Extraction

How to process PDFs and ingest them into the knowledge base.

## Overview

```
PDF File
    |
    v
extract_all_pages.py (Vision model - Qwen3-VL-235B)
    |
    +---> Page images + annotated versions
    +---> Element crops (figures, tables, equations)
    +---> Per-page JSON with text and metadata
    |
    v
enrich_elements.py (Text model - Qwen3-30B)
    |
    +---> Generate search_text for each element
    |
    v
ingest_to_db.py (Embedding model - BGE-M3)
    |
    +---> Chunk text (~800 chars, 200 overlap)
    +---> Embed chunks + elements
    +---> Insert to PostgreSQL + pgvector
```

---

## Servers (minto)

| Service | Port | Model | Script |
|---------|------|-------|--------|
| Vision | 8090 | Qwen3-VL-235B | `/media/nvme2g-a/llm_toolbox/servers/qwen3-vl-235b-8090.sh` |
| Text | 8080 | Qwen3-30B-A3B | `/media/nvme2g-a/llm_toolbox/servers/qwen3-30b-32k.sh` |
| Embedding | 8094 | BGE-M3-F16 | `/media/nvme2g-a/llm_toolbox/servers/bge-m3-embed-8094.sh` |

---

## Processing a New PDF

### Pre-flight Checks

```bash
cd ~/github/osgeo-library
source .venv/bin/activate

# Check servers
curl -s http://localhost:8090/health && echo " - Vision OK" || echo " - Vision FAILED"
curl -s http://localhost:8080/health && echo " - Text OK" || echo " - Text FAILED"
curl -s http://localhost:8094/health && echo " - Embedding OK" || echo " - Embedding FAILED"

# Check database
psql -d osgeo_library -c "SELECT COUNT(*) FROM documents;"
```

### Step 1: Extract

Convert PDF pages to images, detect elements, crop them.

```bash
# Full document
python extract_all_pages.py pdfs/document.pdf --name doc_name --skip-existing

# Background with logging
nohup python extract_all_pages.py pdfs/document.pdf --name doc_name --skip-existing \
  > logs/doc_name_extraction.log 2>&1 &

# Check progress
tail -f logs/doc_name_extraction.log
ls db/data/doc_name/pages/ | wc -l
```

**Time estimate:** ~107 seconds/page average

### Step 2: Enrich

Generate contextual `search_text` for each element.

```bash
python enrich_elements.py doc_name
```

**Time estimate:** ~2.5 seconds/element

### Step 3: Ingest

Chunk text, generate embeddings, insert into PostgreSQL.

```bash
python ingest_to_db.py doc_name
```

**Time estimate:** ~2 minutes for most documents

### Step 4: Verify

```bash
psql -d osgeo_library -c "
  SELECT d.slug, COUNT(DISTINCT p.id) as pages, COUNT(DISTINCT e.id) as elements 
  FROM documents d 
  LEFT JOIN pages p ON d.id = p.document_id 
  LEFT JOIN elements e ON d.id = e.document_id 
  WHERE d.slug = 'doc_name'
  GROUP BY d.slug;
"
```

---

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

---

## Current Documents

As of 2025-12-20:

| Slug | Pages | Elements | Source File |
|------|-------|----------|-------------|
| digital_earth | 844 | 456 | ManualOfDigitalEarth_2020.pdf |
| usgs_snyder | 397 | 1041 | usgs_snyder1987.pdf |
| sam3 | 68 | 76 | sam3.pdf |
| aiseg_sam3 | 62 | 70 | aiSeg_sam3_2025.pdf |
| aibench | 47 | 30 | aiBench_pangaea_2025.pdf |
| torchgeo | 27 | 7 | torchgeo_acm_2025.pdf |
| aiseg | 25 | 13 | aiSeg_ag_2025.pdf |
| mlcs_libs | 24 | 5 | mlCS_libs_stewart_2025.pdf |
| alpine_change | 23 | 14 | 2511.00073v1.pdf |
| eo_distortions | 18 | 19 | 2403.04385.pdf |

**Total:** 10 documents, 1535 pages, 1731 elements

---

## Processing Rates

| Page Type | Avg Time |
|-----------|----------|
| No elements | 47s |
| 1-3 elements | 81s |
| 4-6 elements | 173s |
| 7+ elements | 268s |
| **Overall** | **107s** |

---

## Estimates for Scale

For 5000 PDFs (assuming 50 pages avg = 250,000 pages):

### Storage

| Per Page | Size |
|----------|------|
| Page image (PNG, 150 DPI) | ~500-700 KB |
| Annotated image | ~500-700 KB |
| Element crops (avg 2/page) | ~50-200 KB each |
| JSON metadata | ~2-5 KB |
| **Total for 250k pages** | **~300-375 GB** |

### Processing Time

| Setup | Time |
|-------|------|
| Single GPU | ~7,400 hours (~10 months) |
| 4 GPUs parallel | ~1,850 hours (~2.5 months) |
| 8 GPUs parallel | ~925 hours (~5 weeks) |

---

## Troubleshooting

### Extraction errors

**"Coordinate 'right' is less than 'left'"**
- Vision model returned invalid bounding box
- Usually with pages that have line numbers or unusual layouts
- Skip the page and continue; extraction still gets the text

**Timeout on extraction**
- Rich pages with many elements can take 3-5 minutes
- Normal for pages with many figures/tables/equations

### Enrichment failures

- Usually due to missing crop files or API errors
- Check if element crop exists in `db/data/doc_name/elements/`
- Re-run enrichment; it skips already-enriched elements

### Start servers (if needed)

```bash
# Embedding server
/media/nvme2g-a/llm_toolbox/servers/bge-m3-embed-8094.sh &

# Text/enrichment server
/media/nvme2g-a/llm_toolbox/servers/qwen3-30b-32k.sh &

# Vision server (requires ~51GB VRAM)
/media/nvme2g-a/llm_toolbox/servers/qwen3-vl-235b-8090.sh &
```
