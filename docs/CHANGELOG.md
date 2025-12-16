# Changelog

Brief log of what changed and when.

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
