# OSGeo Library

Extract, catalog, and make searchable a collection of geospatial AI and Earth Observation research papers, enabling intelligent retrieval including figures and diagrams.

**[See PROGRESS.md for latest updates and next steps](PROGRESS.md)**

## Goal

Build a knowledge base from 5000+ research PDFs that allows:
- Semantic search across paper content
- Figure retrieval by description ("show me the SAM3 architecture diagram")
- Integration with LLM assistants for scientific Q&A

## Approach

We use a hybrid extraction pipeline:

| Method | Tool | Purpose |
|--------|------|---------|
| Traditional | PyMuPDF | Text, metadata, image detection |
| Multimodal | Gemini 2.0 Flash | Figure descriptions, key concepts, structured extraction |

**Quality over velocity** - Multimodal extraction is rate-limited but essential for understanding visual content. If it takes a year to process the full library, that's acceptable.

## Scripts

### extract_pdf.py

Traditional PDF extraction using PyMuPDF.

```bash
# Extract all pages
python extract_pdf.py paper.pdf --output results.json

# Extract first 3 pages
python extract_pdf.py paper.pdf --max-pages 3

# Text-only output
python extract_pdf.py paper.pdf --text-only
```

### extract_multimodal.py

Multimodal extraction using vision LLMs via OpenRouter.

```bash
# Extract specific pages with Gemini
python extract_multimodal.py paper.pdf --pages 1,2,3 --model gemini

# Available models: gemini, nemotron-vl, nova
python extract_multimodal.py paper.pdf --pages 1 --model nemotron-vl
```

Requires OpenRouter API key in `~/github/matrix-llmagent/config.json` or via `--api-key`.

### generate_comparison.py

Generate comparison data for the web viewer.

```bash
python generate_comparison.py paper.pdf \
  --traditional traditional_results.json \
  --multimodal multimodal_results.json \
  --pages 1,2,3 \
  --output-dir web
```

## Comparison Website

A simple viewer to compare extraction methods side-by-side.

```bash
cd web
python -m http.server 8765
# Open http://localhost:8765
```

Shows:
- Original PDF page image
- Traditional extraction (text, image count, blocks)
- Multimodal extraction (figure descriptions, key concepts, citations)

## Sample Results

**Traditional extraction** detects:
- 3178 characters of text
- 11 images on page 1
- 20 text blocks

**Multimodal extraction** adds:
- Figure descriptions: "The figure demonstrates the improvement of SAM 3 over SAM 2..."
- Key concepts: SAM, PCS, PVS, interactive visual segmentation
- Citations: Kirillov et al., 2023; Ravi et al., 2024

## Setup

```bash
# Clone
git clone https://github.com/ominiverdi/osgeo-library.git
cd osgeo-library

# Create virtual environment (using uv)
uv venv
uv pip install PyMuPDF requests

# Or with standard venv
python -m venv .venv
source .venv/bin/activate
pip install PyMuPDF requests
```

## Architecture

```
PDF Files (5000+)
       |
       v
+------+-------+
|              |
v              v
Traditional    Multimodal
(PyMuPDF)      (Gemini)
|              |
v              v
Text +         Figure
Metadata       Descriptions
|              |
+------+-------+
       |
       v
 PostgreSQL DB
 (osgeo_research_kb)
       |
       v
 LLM Assistant
 search_research_papers()
       |
       v
 User: "show me SAM3 architecture"
 Bot: [returns figure + description]
```

## Future Plans

- [ ] Dedicated database for research papers (`osgeo_research_kb`)
- [ ] Individual figure extraction (not just page images)
- [ ] Vector embeddings for semantic figure search
- [ ] `search_research_papers()` function for LLM assistant
- [ ] Process full library over time

## Related Projects

- [matrix-llmagent](https://github.com/ominiverdi/matrix-llmagent) - Matrix chatbot with knowledge base
- OSGeo Wiki knowledge base (`osgeo_wiki_kb`)

## License

MIT
