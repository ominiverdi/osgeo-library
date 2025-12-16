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
JSON response with bounding boxes (0-1000 scale)
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
Web Viewer / Database
```

## Key Components

### extract_document.py

Main extraction script. Uses Qwen3-VL for visual grounding.

```bash
# Extract pages
python extract_document.py paper.pdf --pages 1,2,3 --output-dir web/data/paper

# Merge with existing
python extract_document.py paper.pdf --pages 4,5 --output-dir web/data/paper --merge
```

**Output structure:**
```
web/data/paper/
  extraction.json
  page_01.png
  page_01_annotated.png
  elements/
    p01_figure_1_Figure_1.png
    p04_equation_1_Equation_1.png
    p04_equation_1_Equation_1_rendered.png
```

### Coordinate System

Qwen3-VL returns bounding boxes in 0-1000 relative scale:
```python
pixel_x = int(coord_1000 / 1000 * image_width)
pixel_y = int(coord_1000 / 1000 * image_height)
```

### LaTeX Rendering

For equations, the model extracts LaTeX in the description field:
```
LaTeX: \frac{a}{b} = c
```

Pipeline:
1. `extract_latex_from_description()` parses LaTeX from model output
2. `render_latex_to_image()` creates standalone TeX document
3. pdflatex compiles to PDF
4. ImageMagick converts PDF to PNG

## Model Server

Requires llama.cpp with Qwen3-VL-235B:

```bash
cd /media/nvme2g-a/llm_toolbox
./llama.cpp-latest/build-rocm/bin/llama-server \
  --model models/Qwen3-VL-235B/Qwen3-VL-235B-A22B-Instruct-UD-TQ1_0.gguf \
  --mmproj models/Qwen3-VL-235B/mmproj-F16.gguf \
  --host 0.0.0.0 --port 8090 \
  --ctx-size 8192 --parallel 1 -ngl 999
```

Check health: `curl http://localhost:8090/health`

## Dependencies

**Python:**
- PyMuPDF (fitz) - PDF to image
- Pillow - image processing  
- openai - API client for llama.cpp server
- matplotlib - fallback LaTeX rendering

**System:**
- texlive (pdflatex) - LaTeX compilation
- imagemagick (convert) - PDF to PNG

## Web Viewer

Static HTML/JS viewer. Serves from `web/` directory.

```bash
cd web && python -m http.server 8080
```

Features:
- Document selector
- Page navigation (arrows)
- Three panels: Original | Annotated | Elements
- Dual equation display: cropped + rendered
