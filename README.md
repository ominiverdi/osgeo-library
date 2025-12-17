# OSGeo Library

Extract figures, tables, and equations from geospatial research PDFs using vision-language models.

## Quick Start

```bash
# 1. Start model server (requires Qwen3-VL-235B)
# See docs/ARCHITECTURE.md for setup

# 2. Extract pages
python extract_document.py paper.pdf --pages 1,2,3 --output-dir web/data/paper

# 3. View results
cd web && python -m http.server 8080
```

## Documentation

- [CHANGELOG](docs/CHANGELOG.md) - What changed when
- [ARCHITECTURE](docs/ARCHITECTURE.md) - How the pipeline works
- [EXTRACTIONS](docs/EXTRACTIONS.md) - Catalog of processed documents
- [DECISIONS](docs/DECISIONS.md) - Technical decisions and alternatives

## Dependencies

**Python:** PyMuPDF, Pillow, openai, matplotlib

**System:** texlive (pdflatex), imagemagick

**Model:** Qwen3-VL-235B via llama.cpp

## Author

Lorenzo Becchi

## License

MIT
