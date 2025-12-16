# OSGeo Library

Extract, catalog, and make searchable a collection of geospatial AI and Earth Observation research papers, enabling intelligent retrieval including figures and diagrams.

**[See PROGRESS.md for latest updates and next steps](PROGRESS.md)**

**[Live Demo on Cloudflare Pages](https://osgeo-library.pages.dev)** (if deployed)

## Goal

Build a knowledge base from 5000+ research PDFs that allows:
- Semantic search across paper content
- Figure retrieval by description ("show me the SAM3 architecture diagram")
- Integration with LLM assistants for scientific Q&A

## Current Approach: Visual Grounding with Qwen3-VL

We use **Qwen3-VL-32B** running locally via llama.cpp for accurate figure/table detection with bounding boxes.

### Why Visual Grounding?

| Method | Figures | Tables | Accuracy | Speed |
|--------|---------|--------|----------|-------|
| PyMuPDF | Fragments only | Basic | Poor | Fast |
| Caption heuristics | Good | Good | ~90% | Fast |
| **Qwen3-VL-32B** | **Excellent** | **Excellent** | **~98%** | ~40s/page |

The vision model understands page layout and returns precise bounding boxes in 0-1000 coordinate scale, which we convert to pixel coordinates for cropping.

## Scripts

### extract_document.py (Recommended)

Complete extraction pipeline using Qwen3-VL for visual grounding.

```bash
# Extract specific pages
python extract_document.py paper.pdf --pages 1,2,3 --output-dir web/data/paper_name

# Merge with existing extraction (incremental)
python extract_document.py paper.pdf --pages 4,5,6 --output-dir web/data/paper_name --merge

# Custom DPI for higher resolution
python extract_document.py paper.pdf --pages 1 --output-dir output --dpi 200
```

**Requires**: Qwen3-VL-32B server running on localhost:8090

**Output**:
- `page_XX.png` - Original page images
- `page_XX_annotated.png` - Pages with bounding boxes drawn
- `elements/` - Cropped figures, tables, diagrams
- `extraction.json` - Structured data with timing info

### extract_pdf.py

Traditional PDF extraction using PyMuPDF (fast, text-only).

```bash
python extract_pdf.py paper.pdf --output results.json
python extract_pdf.py paper.pdf --max-pages 3
python extract_pdf.py paper.pdf --text-only
```

### extract_figures.py

Caption-based figure extraction (heuristic approach).

```bash
python extract_figures.py paper.pdf --pages 2,3,4 --output-dir figures/
```

## Web Viewer

Interactive viewer for extracted documents. Deployed on Cloudflare Pages.

```bash
cd web
python -m http.server 8080
# Open http://localhost:8080
```

**Features**:
- Document selector dropdown
- Page navigation with keyboard shortcuts (arrow keys)
- Three-panel view: Original | Annotated | Extracted Elements
- Click images to view full size
- Shows extraction timing per page

## Sample Extractions

### SAM3 Paper (sam3.pdf)
- 7 pages extracted (1, 2, 3, 5, 6, 7, 8)
- 12 elements: 6 figures, 5 tables, 1 chart
- Average detection time: ~40s/page

### USGS Map Projections (usgs_snyder1987.pdf)
- 9 pages extracted (1, 9, 16, 21, 32, 34, 42, 51, 52)
- 8 figures including Mercator projection diagrams
- Average detection time: ~42s/page

## Local Setup

### 1. Install Dependencies

```bash
git clone https://github.com/ominiverdi/osgeo-library.git
cd osgeo-library

# Using uv (recommended)
uv venv
uv pip install PyMuPDF Pillow openai

# Or standard venv
python -m venv .venv
source .venv/bin/activate
pip install PyMuPDF Pillow openai
```

### 2. Start Vision Model Server

Requires llama.cpp with Qwen3-VL-32B:

```bash
cd /path/to/llm_toolbox
./llama.cpp-latest/build/bin/llama-server \
  --model models/Qwen3-VL-32B/Qwen3VL-32B-Instruct-Q4_K_M.gguf \
  --mmproj models/Qwen3-VL-32B/mmproj-Qwen3VL-32B-Instruct-F16.gguf \
  --host 0.0.0.0 --port 8090 \
  --ctx-size 8192 --parallel 1 -ngl 999
```

### 3. Run Extraction

```bash
# Check server health
curl http://localhost:8090/health

# Extract document
python extract_document.py document.pdf --pages 1,2,3 --output-dir web/data/doc_name

# View results
cd web && python -m http.server 8080
```

## Architecture

```
PDF Files (5000+)
       |
       v
+------+--------+
|               |
v               v
PyMuPDF         Qwen3-VL-32B
(text)          (visual grounding)
|               |
v               v
Text +          Bounding boxes
Metadata        + Descriptions
|               |
+-------+-------+
        |
        v
   Crop Elements
   (figures, tables)
        |
        v
   extraction.json
        |
        v
   Web Viewer / DB
        |
        v
   LLM Assistant
   "show me SAM3 architecture"
```

## Model Comparison

| Model | Grounding | Speed | Notes |
|-------|-----------|-------|-------|
| Qwen3-VL-8B | Poor | ~48s/page | Wrong bounding boxes |
| **Qwen3-VL-32B** | **Excellent** | ~40s/page | Recommended |
| Qwen3-VL-235B | Untested | Slower | Available, 47GB |

## Future Plans

- [ ] Test Qwen3-VL-235B for potentially better accuracy
- [ ] Process full library (~5000 PDFs)
- [ ] PostgreSQL database for search
- [ ] Vector embeddings for semantic figure search
- [ ] `search_research_papers()` function for LLM assistant

## Related Projects

- [matrix-llmagent](https://github.com/ominiverdi/matrix-llmagent) - Matrix chatbot with knowledge base

## License

MIT
