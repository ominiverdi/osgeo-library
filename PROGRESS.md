# Progress Log

Tracking progress on the OSGeo Library extraction project.

## 2025-12-15: Initial Setup and Testing

### What we did

1. **Set up extraction pipeline** on osgeo7-gallery server
   - Created virtual environment with `uv`
   - Installed PyMuPDF for PDF processing
   
2. **Tested traditional extraction** (PyMuPDF)
   - Tested on `aiSeg_sam3_2025.pdf` (44MB, 68 pages) - SAM3 segmentation paper
   - Tested on `2403.04385.pdf` (37MB, 18 pages) - EO color/texture distortions paper
   - Result: Good text extraction, detects images but cannot describe them

3. **Tested multimodal extraction** (Gemini 2.0 Flash via OpenRouter)
   - Extracted page 1 of SAM3 paper
   - Result: Excellent figure descriptions, extracts key concepts and citations
   - Rate limiting is aggressive on free tier

4. **Built comparison website**
   - Side-by-side viewer: Original page | Traditional | Multimodal
   - Colleagues can evaluate extraction quality
   - Run locally: `cd web && python -m http.server 8765`

### Key findings

| Aspect | Traditional | Multimodal |
|--------|-------------|------------|
| Text | Good | Good |
| Figures | Count only | Full descriptions |
| Speed | Instant | ~10s/page |
| Cost | Free | Rate limited |

**Example multimodal output for Figure 1:**
> "The figure demonstrates the improvement of SAM 3 over SAM 2. On the left (promptable visual segmentation - SAM2), it shows an image and a video, both with interactive prompts... Examples include an image of striped cats, a round cell, a small window, kangaroos and hard hats."

### Decisions made

1. **Multimodal is essential** - Scientific users need figure understanding, not just text
2. **Quality over velocity** - If extraction takes a year with free tier, that's fine
3. **Separate database** - New `osgeo_research_kb` database for papers+images (not mixing with wiki KB)
4. **New LLM function** - Will create `search_research_papers()` for the assistant to query papers and return images

### Files created

```
osgeo-library/
├── extract_pdf.py          # Traditional extraction
├── extract_multimodal.py   # Multimodal extraction (OpenRouter)
├── generate_comparison.py  # Generate comparison data
├── web/
│   ├── index.html          # Comparison viewer
│   └── data/
│       ├── comparisons.json  # Extraction results
│       └── page_001.png      # Sample page image
```

---

## 2025-12-16: Image Extraction and Enhanced Visual Element Classification

### What we did

1. **Added image extraction from PDFs**
   - `extract_multimodal.py` now extracts embedded images from each page
   - Images saved to `images/` subdirectory with naming: `{pdf}_p{page}_img{n}.{ext}`
   - Skips tiny images (<50px) like icons and bullets
   - Records image metadata: size, format, position on page

2. **Enhanced visual element classification**
   - Prompt now asks Gemini to categorize each visual element:
     - `architecture_diagram` - Model architectures, system diagrams
     - `flowchart` - Process flows
     - `graph_chart` - Bar, line, scatter charts with axes/data
     - `results_figure` - Comparison visualizations
     - `map` / `satellite_image` - Geographic content
     - `table` - Structured data
     - `equation` - Mathematical content
   - Extracts structured table data (headers, rows, key findings)
   - Extracts reported metrics with context
   - Lists methods/models and datasets mentioned

3. **Updated web viewer**
   - Displays extracted images in a grid
   - Shows visual element types with color-coded tags
   - Displays structured table data
   - Shows reported metrics (e.g., "mAP: 0.85 on COCO")
   - Backward compatible with old extraction format

### New command options

```bash
# Extract with image extraction (default)
.venv/bin/python extract_multimodal.py /path/to/paper.pdf --pages 2,3,4 --model gemini

# Skip image extraction
.venv/bin/python extract_multimodal.py /path/to/paper.pdf --pages 2,3,4 --no-images

# Specify output directory for images
.venv/bin/python extract_multimodal.py /path/to/paper.pdf --output-dir ./output
```

### Recommended test pages for SAM3 paper

Based on typical paper structure, try these pages for variety:
- Page 2-3: Architecture diagram (Figure 2 usually)
- Page 5-7: Method details, possibly equations
- Page 8-10: Results tables and comparison charts
- Page 12-14: Ablation studies, more tables/graphs

---

## 2025-12-16: Model Comparison and Claude Integration

### What we did

1. **Tested multiple free multimodal models via OpenRouter**

   | Model | Content Quality | Figure Description | Equations | Verdict |
   |-------|----------------|-------------------|-----------|---------|
   | Gemini 2.0 Flash | Good | Good | Untested | Aggressive rate limits |
   | Amazon Nova 2 | Good | Basic | Missed | Reliable, recommended |
   | Nemotron VL | Poor | Poor (hallucinated) | Missed | Not recommended |
   | Gemma 3 12B | Decent | Basic | Untested | Sometimes rate limited |
   | Mistral Small 3.1 | N/A | N/A | N/A | No image support (404) |

2. **Added Claude Sonnet 4 as reference extraction**
   - Manually extracted pages 2, 3, 4 by showing images to Claude
   - Excellent results:
     - **Figure 2**: Full workflow description with all 4 panels
     - **Figure 3**: Architecture diagram with all components listed
     - **Page 4 equation**: Full LaTeX + semantic explanation
   - Claude extractions saved to `web/data/sam3_claude_p2-4.json`

3. **Built model comparison features**
   - Model filter dropdown to compare specific models
   - Color-coded model badges (Claude=orange, Nova=orange-blue, etc.)
   - Page selector shows model name
   - Incremental merge preserves existing extractions

4. **Improved image extraction**
   - Area-based filtering (min 20,000 px) + min dimension (80px)
   - Deduplication of identical images
   - PyMuPDF extracts images in both Traditional and Multimodal panels

### Key findings

**Claude is the best for content understanding** - correctly identifies:
- Figure structure (4-panel workflow, architecture components)
- Mathematical equations with LaTeX representation
- Semantic meaning of equations (not just symbols)

**PyMuPDF limitations for figures:**
- Extracts embedded raster images only
- Composite figures appear as fragments
- Vector graphics (diagrams, equations) not extracted as images
- Need alternative approach for figure/equation extraction

### Available models (extract_multimodal.py)

```bash
--model nova      # Amazon Nova 2 (recommended, reliable)
--model gemma-12b # Gemma 3 12B (good, sometimes rate limited)
--model gemma-4b  # Gemma 3 4B (fast, untested quality)
--model nemotron  # Nemotron VL (not recommended)
--model gemini    # Gemini 2.0 Flash (best but rate limited)
```

### Current comparison data

```
Page 2: Claude Sonnet 4, Amazon Nova 2, Gemma 3 12B, Nemotron VL
Page 3: Claude Sonnet 4, Nemotron VL
Page 4: Claude Sonnet 4, Nemotron VL
```

---

## Next Steps

### Immediate
- [x] Colleagues evaluate extraction quality using comparison website
- [x] Test on diverse pages (architecture, tables, results)
- [ ] Research alternatives for figure/equation extraction (pdfplumber, pdfminer, Marker, Nougat)
- [ ] Test second PDF sample (2403.04385.pdf)

### Short term
- [ ] Design `osgeo_research_kb` database schema
- [x] Extract individual figures (not just page images)
- [ ] Improve equation extraction (LaTeX from PDF)
- [ ] Add vector embeddings for semantic search

### Long term
- [ ] Process full library (~5000 PDFs)
- [ ] Implement `search_research_papers()` function
- [ ] Enable queries like "show me the SAM3 architecture diagram"

---

## Research: Figure/Equation Extraction Alternatives

### Investigated Tools

#### Marker (datalab-to/marker) - 30.4k stars
- **Best for**: Full PDF to markdown/JSON conversion
- **Figures**: Extracts and saves images
- **Equations**: LaTeX fenced with `$$`
- **Tables**: Excellent (can use LLM for accuracy)
- **Speed**: Fast (~0.18s/page on H100)
- **License**: GPL (commercial requires paid license)
- **Install**: `pip install marker-pdf`
- **Use**: `marker_single paper.pdf -o output/ --use_llm`

#### Nougat (facebookresearch/nougat) - 9.8k stars
- **Best for**: Academic papers (trained on arXiv/PMC)
- **Figures**: Semantic understanding only (no image extraction)
- **Equations**: Native LaTeX output (excellent)
- **Tables**: Good (Mathpix Markdown format)
- **Speed**: Slower (neural model)
- **License**: MIT (code), CC-BY-NC (model weights)
- **Install**: `pip install nougat-ocr`
- **Use**: `nougat paper.pdf -o output/`
- **Limitation**: English only, no CJK support

### Comparison for Our Use Case

| Tool | Figures | Equations | Tables | Best For |
|------|---------|-----------|--------|----------|
| **PyMuPDF** | Raw images only | None | Basic | Text extraction, speed |
| **Marker** | Extracts images | LaTeX (good) | Excellent | General PDFs, RAG |
| **Nougat** | Semantic only | LaTeX (excellent) | Good | Scientific papers |
| **Claude** | Via vision | Excellent | Excellent | Quality reference |

### Recommended Hybrid Approach

1. **PyMuPDF**: Fast text extraction, image detection
2. **Marker**: Figure extraction + LaTeX equations
3. **Nougat**: Academic-specific, equation-heavy papers
4. **Claude/Multimodal**: Quality verification, figure descriptions

### Testing Results (2025-12-16)

**Tested Marker on osgeo7-gallery (CPU-only server):**
- Installed via `uv pip install marker-pdf nougat-ocr`
- Ran `marker_single` on SAM3 paper (5 pages)
- **Result: Impractical without GPU**
  - Used 7GB RAM
  - Stuck at "Recognizing Layout" step
  - Neural models (Surya OCR, layout detection) too slow on CPU
  - Killed after 5+ minutes with no progress

**Conclusion: Marker/Nougat require GPU acceleration**

For 5000+ papers, CPU-only processing is not viable.

---

## Tool Evaluation Notes

### PyMuPDF (fitz)

**What it does well:**
- Fast text extraction with position information
- Extracts embedded raster images
- Gets document metadata, page count, structure
- Can render pages to images at any DPI
- Detects text blocks, lines, spans with bounding boxes
- Access to vector drawing paths (though raw, not semantically grouped)

**Limitations:**
- Cannot extract complete figures - only embedded raster images
- Composite figures (multiple images + labels) appear as fragments
- Vector graphics (diagrams, flowcharts) not extractable as images
- Equations rendered as vectors are not captured
- No semantic understanding of figure boundaries

**Best for:** Text extraction, page rendering, basic image extraction

### pdfplumber

**What it does well:**
- Similar to PyMuPDF for text extraction
- Good table detection and extraction
- Access to curves, lines, rectangles (vector elements)
- Character-level positioning

**Limitations:**
- Same figure extraction problems as PyMuPDF
- No automatic figure detection
- Slower than PyMuPDF for large documents

**Best for:** Table extraction, detailed text positioning

### Marker (marker-pdf)

**What it does well (in theory):**
- Full PDF to markdown conversion
- LaTeX equation extraction
- Uses neural models for layout detection
- LLM integration for accuracy

**Limitations:**
- Requires GPU - impractical on CPU (stuck after 5+ minutes)
- Heavy memory usage (7GB+ RAM)
- GPL license (commercial use restricted)

**Best for:** If you have GPU, general PDF to markdown conversion

### Nougat (nougat-ocr)

**What it does well (in theory):**
- Academic paper specialist (trained on arXiv/PMC)
- Native LaTeX output for equations
- Semantic figure understanding

**Limitations:**
- Requires GPU
- English only
- No actual image extraction (semantic descriptions only)
- CC-BY-NC license for model weights

**Best for:** If you have GPU, equation-heavy academic papers

### Local Vision Models (Qwen-VL via llama.cpp)

**What it does well:**
- Excellent content understanding from page images
- Describes figures, equations, tables accurately
- Extracts structured data (methods, datasets, metrics)
- No rate limits, no API costs
- ~48s per page on local GPU

**Limitations:**
- Requires GPU (but we have 128GB VRAM)
- Cannot "extract" figures - only describes them
- Needs page rendered as image first

**Best for:** Content understanding, figure descriptions, semantic extraction

### Caption-Based Figure Extraction (our solution)

**What it does well:**
- Extracts complete figures including vector graphics
- Works by finding captions and rendering regions
- No ML models needed - pure heuristics
- Fast and reliable for standard paper formats

**Limitations:**
- Requires consistent caption format ("Figure X:", "Table X:")
- Heuristic region detection may miss some cases
- Doesn't work for captionless figures

**Best for:** Scientific papers with standard figure captions

---

## 2025-12-16: Local GPU + Vision Models (New Approach)

### Available Resources on minto (local workstation)

**GPU**: Available for local inference

**Vision Models (GGUF format):**
- `Qwen2.5-VL-72B` - Large, high quality
- `Qwen2-VL-7B` - Medium, good balance
- `Qwen2-VL-2B-Instruct` - Small, fast
- `Qwen3-VL-8B` - Latest Qwen3 vision
- `Qwen3-VL-1B` - Lightweight Qwen3 vision

**llama.cpp with Vision Support:**
- Location: `/media/nvme2g-a/llm_toolbox/llama.cpp-latest/`
- Supports multimodal models (Qwen-VL, LLaVA, etc.)
- Can run vision models locally without API costs

**Existing Server Scripts:**
- `/media/nvme2g-a/llm_toolbox/servers/` - Ready-to-use launch scripts

### New Approach: Local Vision Model Extraction

Instead of:
- Marker/Nougat (too slow on CPU)
- OpenRouter API (rate limits, costs at scale)

Use:
- **llama.cpp server** with Qwen-VL model locally
- No rate limits, no API costs
- GPU-accelerated inference
- Same extraction pipeline, different endpoint

### Local Vision Model Benchmark (2025-12-16)

Tested on SAM3 paper page 2 (contains Figure 2 + text).

| Model | Time | Quality | Notes |
|-------|------|---------|-------|
| **Qwen3-VL-8B** | 47.8s | Excellent | Best balance of speed/quality |
| Qwen2-VL-7B | 179.7s | Good | 3.7x slower, similar quality |
| Qwen3-VL-1B | N/A | N/A | Merged GGUF lacks vision support |
| Qwen2.5-VL-72B | N/A | N/A | Missing main model GGUF |

**Winner: Qwen3-VL-8B**
- Fast enough for batch processing (75 pages/hour)
- Excellent content extraction (matches Claude quality)
- Correctly identified Figure 2 structure
- Extracted all key concepts and terminology
- No rate limits, no API costs

**Sample output (Qwen3-VL-8B on page 2):**
- Identified SAM 3 as model for Promptable Concept Segmentation
- Described Figure 2: interactive refinement with initial prompt, output, refinement prompts
- Listed key terms: presence head, SA-Co benchmark, zero-shot mask AP
- Noted performance: 47.0 mAP on LVIS, 30ms/image on H200

### Recommended Setup

```bash
# Start Qwen3-VL-8B server
cd /media/nvme2g-a/llm_toolbox
./llama.cpp-latest/build-rocm/bin/llama-server \
  --model models/Qwen3-VL-8B/Qwen3VL-8B-Instruct-Q4_K_M.gguf \
  --mmproj models/Qwen3-VL-8B/mmproj-Qwen3VL-8B-Instruct-F16.gguf \
  --host 0.0.0.0 --port 8090 \
  --ctx-size 8192 \
  --n-gpu-layers 99
```

### Figure Extraction Solution (2025-12-16)

**Problem:** PyMuPDF extracts fragmented images, not complete figures.

**Solution:** Caption-based region rendering using `extract_figures.py`

**Technique:**
1. **Find captions**: Regex search for "Figure X:", "Fig. X.", "Table X:" patterns
2. **Locate caption position**: Get bounding box of caption text using PyMuPDF
3. **Estimate figure boundaries**:
   - Top: Search upward for text blocks, figure starts after last paragraph
   - Bottom: Caption position + small margin
   - Left/Right: Page margins (configurable)
4. **Render region**: Use `page.get_pixmap(clip=region)` to render just that area
   - This captures EVERYTHING in the region: raster images, vector graphics, text labels
   - No need to extract individual elements - just screenshot the region

**Why this works:**
- Scientific papers have consistent layouts
- Figures are placed between paragraphs with whitespace
- Captions are always directly below figures
- Rendering the region captures vectors (diagrams, flowcharts) that can't be "extracted"

**Algorithm improvements (v2):**
- Detect image blocks (embedded images) to find figure boundaries
- Skip line number columns (narrow text blocks on margins)
- Use image block positions as hints for figure top boundary
- Handle stacked figures (e.g., Figure 5 with video + images)

**Results on SAM3 paper (pages 1-8):**
```
Extracted 11 figures/tables:
- Figure 1-6: Main paper figures (including stacked Figure 5)
- Table 1-5: Results tables
All include complete vector graphics and labels
```

**Known limitations:**
- Some marginal clipping on complex layouts
- Equations without "Equation X:" captions not detected
- Multi-column layouts may need adjustment

**Future improvement: VL-based bounding box detection**

Could use vision model to get precise bounding boxes:
1. Send page image to Qwen-VL with prompt asking for coordinates
2. Model returns JSON with [x1, y1, x2, y2] for each figure/table
3. Use those coordinates to crop precisely

Options explored:
- **Qwen-VL**: Can give approximate boxes, not trained for precision
- **LayoutParser + Detectron2**: PubLayNet model trained on scientific papers
- **PDFFigures2**: Java tool, specialized but requires JVM

For now, caption-based heuristics work well for ~90% of cases.

**Usage:**
```bash
.venv/bin/python extract_figures.py pdfs/paper.pdf \
  --pages 2,3,4 \
  --output-dir web/data/figures \
  --output-json web/data/figures_extracted.json
```

### Recommended Extraction Pipeline

1. **PyMuPDF**: Text extraction (fast, accurate)
2. **extract_figures.py**: Complete figure images (caption-based)
3. **Qwen3-VL-8B**: Figure descriptions + semantic content (via llama.cpp)

This hybrid approach:
- Gets full text with PyMuPDF
- Gets complete figures as images
- Gets semantic understanding from vision model

### Next Steps

1. Test figure extraction on more pages/papers
2. Integrate figure extraction into main pipeline
3. Process full library (~5000 papers)

---

## Local Setup (minto)

### 1. Start the Vision Model Server

```bash
# Start Qwen3-VL-8B (recommended)
cd /media/nvme2g-a/llm_toolbox
./llama.cpp-latest/build-rocm/bin/llama-server \
  --model models/Qwen3-VL-8B/Qwen3VL-8B-Instruct-Q4_K_M.gguf \
  --mmproj models/Qwen3-VL-8B/mmproj-Qwen3VL-8B-Instruct-F16.gguf \
  --host 0.0.0.0 --port 8090 \
  --ctx-size 8192 \
  --n-gpu-layers 99
```

### 2. Run Extraction

```bash
cd ~/github/osgeo-library

# Extract specific pages (local model - no API key needed)
.venv/bin/python extract_multimodal.py pdfs/aiSeg_sam3_2025.pdf \
  --pages 2,3,4 \
  --output web/data/sam3_qwen3vl_p2-4.json \
  --output-dir web/data

# Extract all pages (takes ~48s per page)
.venv/bin/python extract_multimodal.py pdfs/aiSeg_sam3_2025.pdf \
  --output web/data/sam3_full.json \
  --output-dir web/data

# Use OpenRouter model (needs API key)
.venv/bin/python extract_multimodal.py pdfs/paper.pdf \
  --model nova \
  --pages 1,2,3
```

### 3. View Results

```bash
cd ~/github/osgeo-library/web
python -m http.server 8765
# Open http://localhost:8765
```

### Available Models

| Model | Backend | Notes |
|-------|---------|-------|
| `qwen3-vl-8b` | local | Default, ~48s/page, excellent quality |
| `qwen2-vl-7b` | local | ~180s/page, good quality |
| `nova` | OpenRouter | Free tier, rate limited |
| `gemini` | OpenRouter | Free tier, aggressive rate limits |
| `gemma-12b` | OpenRouter | Free tier, sometimes rate limited |

### Test PDFs Location

PDFs are stored in `pdfs/` (gitignored):
- `aiSeg_sam3_2025.pdf` - SAM3 segmentation paper (68 pages)
- `2403.04385.pdf` - EO color/texture paper (18 pages)

Copy more from osgeo7-gallery:
```bash
scp osgeo7-gallery:/home/shared/openlibrarymisc/EO_AI_fModel/contribs/PAPER.pdf pdfs/
```

---

## Questions for Colleagues

1. Is the multimodal figure description quality good enough?
2. What other information should we extract?
3. Priority: more papers or deeper extraction on fewer papers first?

---

## 2025-12-16: Visual Grounding with Qwen3-VL-32B

### Major Breakthrough: Accurate Bounding Box Detection

Discovered that **Qwen3-VL-32B** provides excellent visual grounding - it can accurately locate figures, tables, and diagrams with precise bounding boxes.

### Model Comparison for Grounding

| Model | Grounding Quality | Notes |
|-------|-------------------|-------|
| Qwen3-VL-8B | Poor | Wrong regions (e.g., placed Figure 1 at 41% instead of 72%) |
| **Qwen3-VL-32B** | Excellent | Accurate bounding boxes, correct element detection |
| Qwen3-VL-235B | Untested | Downloaded (47GB), available for testing |

### New Extraction Pipeline

Created `extract_document.py` - a complete pipeline using visual grounding:

1. **Convert PDF pages to images** using PyMuPDF
2. **Send to Qwen3-VL-32B** for element detection with bounding boxes
3. **Parse JSON response** with coordinates in 0-1000 scale
4. **Convert to pixel coordinates** and crop detected elements
5. **Create annotated images** with bounding boxes drawn
6. **Output structured JSON** with timing information

**Usage:**
```bash
python extract_document.py document.pdf --pages 1,2,3 --output-dir web/data/doc_name
python extract_document.py document.pdf --pages 4,5 --output-dir web/data/doc_name --merge
```

### Features Added

- **Extraction timing**: Each page records detection time in seconds
- **Merge mode**: `--merge` flag to add pages to existing extraction
- **Annotated images**: Bounding boxes drawn with color coding (red=figure, blue=table, green=diagram)
- **Element cropping**: Figures/tables saved as individual images

### Extraction Results

**SAM3 Paper (sam3.pdf)**
- Pages: 1, 2, 3, 5, 6, 7, 8 (7 pages)
- Elements: 12 total (6 figures, 5 tables, 1 chart)
- Average detection time: ~40s/page

**USGS Map Projections (usgs_snyder1987.pdf)**
- Pages: 1, 9, 16, 21, 32, 34, 42, 51, 52 (9 pages)
- Elements: 8 figures including:
  - FIGURE 2: Meridians and parallels on the sphere
  - FIGURE 3: Tissot's Indicatrix
  - FIGURE 4: Distortion patterns on conformal map projections
  - FIGURE 5: Spherical triangle
  - FIGURE 7: Gerardus Mercator portrait
  - FIGURE 8: The Mercator projection
- Average detection time: ~42s/page

### Timing Results (Snyder extraction)

| Page | Elements | Detection Time |
|------|----------|----------------|
| 9    | 0        | 18.2s          |
| 21   | 1 figure | 39.3s          |
| 32   | 1 figure | 51.5s          |
| 34   | 2 figures| 59.3s          |
| 42   | 1 figure | 38.6s          |
| 51   | 1 figure | 41.8s          |
| 52   | 1 figure | 38.6s          |

### Updated Web Viewer

- Document selector dropdown
- Page navigation (Previous/Next buttons, arrow keys)
- Three-panel layout: Original | Annotated | Extracted Elements
- Shows detection timing per page
- Click images for full-size view

### Technical Details

**Coordinate System:**
- Qwen3-VL uses 0-1000 relative coordinates
- Conversion: `pixel_x = int(coord_1000 / 1000 * image_width)`

**Server Configuration (Qwen3-VL-32B):**
```bash
./llama-server \
  --model Qwen3VL-32B-Instruct-Q4_K_M.gguf \
  --mmproj mmproj-Qwen3VL-32B-Instruct-F16.gguf \
  --host 0.0.0.0 --port 8090 \
  --ctx-size 8192 --parallel 1 -ngl 999
```

### Files Created/Modified

```
osgeo-library/
├── extract_document.py      # NEW: Main extraction pipeline
├── web/
│   ├── index.html           # UPDATED: New viewer with timing
│   └── data/
│       ├── sam3/
│       │   ├── extraction.json
│       │   ├── page_*.png
│       │   ├── page_*_annotated.png
│       │   └── elements/*.png
│       └── usgs_snyder/
│           ├── extraction.json
│           ├── page_*.png
│           ├── page_*_annotated.png
│           └── elements/*.png
```

### Next Steps

- [x] Test Qwen3-VL-235B for comparison
- [ ] Extract more pages from both documents
- [x] Add more test documents
- [ ] Deploy web viewer to Cloudflare Pages

---

## 2025-12-16: Equation Detection and LaTeX Rendering

### Major Improvements

1. **Upgraded to Qwen3-VL-235B** for better equation detection accuracy
   - Switched from 32B model for improved bounding box precision on equations
   - Model: `Qwen3-VL-235B-A22B-Instruct-UD-TQ1_0.gguf` (47GB)

2. **Added equation extraction with LaTeX**
   - Model extracts LaTeX representation of detected equations
   - Both cropped image AND rendered LaTeX saved for comparison
   - Handles multi-line equations (splits on `\\`)
   - Handles `\begin{cases}...\end{cases}` by converting to stacked lines

3. **LaTeX-to-image rendering**
   - Uses matplotlib mathtext with Computer Modern font (`math_fontfamily='cm'`)
   - Font size: 18pt for readability
   - Output: `{element}_rendered.png` alongside cropped `{element}.png`

4. **Filename sanitization**
   - Removed special characters from filenames (parentheses, em-dashes)
   - Pattern: `p{page}_{type}_{idx}_{label}.png`
   - Example: `p44_equation_1_Equation_5-9_and_5-10.png` (was `Equation_(5-9)_and_(.png`)

### Documents Extracted

**SAM3 Paper** - Added pages 4 and 30 with equations:
- Page 4: Equation 1 (similarity function with Iverson bracket)
- Page 30: Equations 1-4 (loss functions including cases notation)

**USGS Snyder 1987** - Page 44 with 7 equations:
- Equations 5-9 through 5-14a (trigonometric formulas)
- All equations have both cropped and rendered versions

**Alpine Habitat Change (2511.00073v1.pdf)** - New document:
- Pages 6, 9, 13-15 extracted
- 6 figures including radar charts
- 2 tables

### Updated Web Viewer

- Shows both "Cropped from PDF" and "Rendered from LaTeX" for equations
- Side-by-side comparison allows quality verification
- Detection timing displayed per page

### Server Configuration (Qwen3-VL-235B)

```bash
cd /media/nvme2g-a/llm_toolbox
./llama.cpp-latest/build-rocm/bin/llama-server \
  --model models/Qwen3-VL-235B/Qwen3-VL-235B-A22B-Instruct-UD-TQ1_0.gguf \
  --mmproj models/Qwen3-VL-235B/mmproj-F16.gguf \
  --host 0.0.0.0 --port 8090 \
  --ctx-size 8192 --parallel 1 -ngl 999
```

### Known Limitations

1. **Equation bounding boxes** - Sometimes slightly off (model limitation), hence LaTeX rendering as backup
2. **LaTeX extraction errors** - Model occasionally misreads complex formulas (e.g., SAM3 p30 Equation 3)
3. **Multi-line equations** - Required special handling for `\begin{cases}` notation

### Files Modified

- `extract_document.py` - Added LaTeX extraction and rendering, filename sanitization
- `web/index.html` - Dual display for equation images (cropped + rendered)
- `web/data/sam3/` - Added equation extractions for pages 4, 30
- `web/data/usgs_snyder/` - Re-extracted page 44 with clean filenames
- `web/data/alpine_change/` - New document extraction

### Next Steps

- [ ] Process more equation-heavy documents
- [ ] Improve LaTeX parsing for edge cases
- [ ] Add batch processing for full library
