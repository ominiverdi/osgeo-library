# Changelog

Brief log of what changed and when.

## 2025-12-18 (v0.1.2)

- **CLI `--open` flag**: Open images in GUI viewer (xdg-open/open)
  - Works with SSH tunneling: client runs locally, fetches images over tunnel
  - Available in search command and chat mode (`open N`)
- **Documentation**: Added GUI viewer section to CLIENT.md

## 2025-12-18 (v0.1.1)

- **CLI image rendering improvements**
  - Server returns `rendered_path` and image dimensions in API response
  - Client uses proportional sizing based on terminal dimensions
  - Equations prefer rendered LaTeX images over raw crops
  - Chafa quality options: `--symbols all -w 9 -c full`
- **CLI help improvements**: Added examples and element types list
- **Documentation**: Completed CLIENT.md with troubleshooting and image rendering sections

## 2025-12-16 (evening)

- **db/data structure**: New per-page JSON structure for database ingestion
  - `db/data/{doc}/document.json` - document metadata
  - `db/data/{doc}/pages/page_001.json` - per-page text, elements, timing
  - `db/data/{doc}/images/` - page renders and annotated versions
  - `db/data/{doc}/elements/` - cropped figures, tables, equations
- **migrate_to_db.py**: Converts existing web/data extractions to db/data structure
- **extract_all_pages.py**: Batch extraction of all PDF pages with resumability
  - Skips already-extracted pages (`--skip-existing`)
  - Per-page JSON output (not monolithic)
  - Progress tracking in document.json
- **run_extraction.sh**: Wrapper script for overnight batch runs
- **gitignore**: Added db/data/ (generated content too large for git)

## 2025-12-16

- **LaTeX rendering**: Switched from matplotlib to pdflatex + ImageMagick for full LaTeX support (`align*`, `cases`, matrices)
- **Text cleaning**: Auto-remove margin line numbers from academic papers (ICLR format)
- **New extractions**: USGS Snyder pages 147, 189, 192 (16 equations); Alpine Change pages 7, 8, 12, 16
- **Upgraded model**: Qwen3-VL-32B -> Qwen3-VL-235B for better equation detection
- **Equation pipeline**: Auto-extract LaTeX from model output, render to `*_rendered.png`
- **Filename sanitization**: Remove special chars from element filenames
- **Visual grounding**: New `extract_document.py` using Qwen3-VL bounding boxes (0-1000 scale)
- **Web viewer**: Three-panel layout, document selector, equation dual-display (crop + rendered)
- **Caption-based extraction**: `extract_figures.py` using regex + region rendering
- **Local inference**: Benchmarked Qwen3-VL-8B (~48s/page) vs Qwen2-VL-7B (~180s/page)

## 2025-12-15

- **Initial setup**: Virtual environment, PyMuPDF for text extraction
- **Multimodal testing**: Gemini 2.0 Flash via OpenRouter (rate limited)
- **Comparison website**: Side-by-side viewer for extraction quality evaluation
- **Model comparison**: Tested Nova, Gemma, Nemotron via OpenRouter; Claude as reference
