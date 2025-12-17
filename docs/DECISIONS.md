# Technical Decisions

Why we chose X over Y.

---

## Visual Grounding: Qwen3-VL-235B

**Decision:** Use Qwen3-VL-235B for element detection with bounding boxes.

**Alternatives considered:**
| Approach | Result |
|----------|--------|
| PyMuPDF image extraction | Only embedded rasters, fragments composite figures |
| Caption-based heuristics | ~90% accuracy, misses captionless figures |
| Qwen3-VL-8B | Poor bounding boxes (placed Figure 1 at 41% instead of 72%) |
| Qwen3-VL-32B | Good for figures/tables, weaker on equations |
| **Qwen3-VL-235B** | **Excellent accuracy, best LaTeX extraction** |

**Why:** The 235B model provides ~98% accurate bounding boxes and reliably extracts LaTeX from equations. The 32B model works but occasionally misses equation boundaries.

**Model files required:**
- `Qwen3-VL-235B-A22B-Instruct-UD-TQ1_0.gguf` - Main language model (quantized)
- `mmproj-F16.gguf` - Multimodal projector (vision encoder bridge)

The mmproj (multimodal projector) bridges the vision encoder to the language model, translating image features into tokens the LLM can understand. Both files must be passed to llama-server for vision capabilities:

```bash
llama-server \
  --model models/Qwen3-VL-235B/Qwen3-VL-235B-A22B-Instruct-UD-TQ1_0.gguf \
  --mmproj models/Qwen3-VL-235B/mmproj-F16.gguf \
  ...
```

**Coordinate system:** Qwen3-VL returns bounding boxes in a 0-1000 relative scale. Convert to pixels with: `pixel = coord * image_size / 1000`.

---

## Local Inference vs Cloud APIs

**Decision:** Run Qwen3-VL locally via llama.cpp.

**Alternatives considered:**
| Approach | Result |
|----------|--------|
| OpenRouter (Gemini, Nova) | Rate limits, costs at scale |
| Claude API | Tested: faster (~13s) but less precise bounding boxes |
| **Local llama.cpp** | **No limits, no API costs, precise bboxes** |

**Claude comparison (Dec 2025):** We tested Claude on 10 pages with 27 elements. While faster (~13s vs ~90s avg), Claude's bounding boxes are noticeably looser - it estimates rather than detects with trained precision. See `web/comparison.html` for side-by-side results. Qwen3-VL's visual grounding training makes it significantly more accurate for this task.

**Why:** Processing 5000+ PDFs with cloud APIs would be expensive and slow (rate limits). Local GPU inference avoids API costs and rate limits.

---

## Figure Extraction: Region Rendering vs Image Extraction

**Decision:** Render page regions as images rather than extracting embedded images.

**Why:** PDF figures are often:
- Composite (multiple images + labels + arrows)
- Vector graphics (diagrams, flowcharts)
- Mixed raster + vector

PyMuPDF can only extract embedded raster images, which appear as fragments. Rendering the bounding box region captures everything as the user sees it.

**Examples of extracted elements:**

### Figures

Figures include maps, photographs, and composite images. The model generates rich semantic descriptions that capture spatial relationships, labels, legends, and visual elements.

| Extracted Image | Description |
|-----------------|-------------|
| ![Figure example](images/example_figure.png) | **Figure 1** *(alpine_change)*: Map of the study area showing the Gesäuse National Park in Styria, Austria, with overlays indicating the HabitAlp Dataset 2013 (blue), Cross-Temporal Dataset 2020 (orange), and the study area (red). The map includes a small inset of Austria with a red dot marking the location of the study area, a north arrow, and a scale bar (0-4 km). |

---

### Tables

Tables are detected with their structure preserved. Descriptions summarize column headers, data types, and key content.

| Extracted Image | Description |
|-----------------|-------------|
| ![Table example](images/example_table.png) | **Table 1** *(sam3)*: Evaluation on image concept segmentation with text. Contains performance metrics (CGF1, AP, Gold, Silver, Bronze, Bio, etc.) for various models including OWLv2, gDino-T, LLMDet-L, APE-D, DINO-X, Gemini 2.5, and SAM 3 across benchmarks like LVIS, SA-Co, COCO, ADE-847, PC-59, and Cityscapes. Includes human performance bounds for reference. |

---

### Charts

Line charts, bar charts, and other data visualizations are captured with descriptions of axes, data series, and visual elements.

| Extracted Image | Description |
|-----------------|-------------|
| ![Chart example](images/example_chart.png) | **Figure 6** *(sam3)*: Line chart comparing SAM 3's interactive exemplar prompts vs. ideal PVS baseline on SA-Co, showing CGF1 score (y-axis, 40-80 range) vs. number of box prompts (x-axis, 0-8). Shows three lines for positive exemplar, negative exemplar, and PVS performance curves. |

---

### Diagrams

Flowcharts, architecture diagrams, and schematic illustrations are detected with descriptions of components, data flow, and relationships.

| Extracted Image | Description |
|-----------------|-------------|
| ![Diagram example](images/example_diagram.png) | **Figure 2** *(alpine_change)*: Flow chart of the experimental framework showing the process from input data processing and labels processing to model training, change map generation, and model evaluation. It includes two approaches: Post-Classification CD and Direct CD (RGB only), with various models like Prithvi-EO-2.0, Clay 1.0, U-Net, and ChangeViT. The diagram also includes training and test sets, saved model states, and evaluation metrics such as IOU, OA, and F1 Score. |

---

### Equations

Equations posed a unique challenge during extraction. While Qwen3-VL successfully detected equations and extracted their LaTeX notation with high accuracy, the **bounding boxes were the least precise** of all element types. Common issues included:

- Bounding boxes extending into surrounding text
- Partial cuts through subscripts or superscripts
- Inclusion of equation numbers in the crop

However, the **LaTeX extraction was remarkably accurate** - the model correctly identified mathematical symbols, Greek letters, subscripts, superscripts, and equation structure even from low-resolution page renders.

**Solution:** We re-render equations from extracted LaTeX using pdflatex + ImageMagick. This produces clean, high-quality equation images regardless of bbox precision. Both the original crop and rendered version are stored.

| Crop from PDF (imprecise bbox) | Re-rendered from LaTeX (clean) |
|-------------------------------|-------------------------------|
| ![Equation crop](images/example_equation_crop.png) | ![Equation rendered](images/example_equation_rendered.png) |

**Extracted LaTeX** *(usgs_snyder, Equations 5-9/5-10)*:
```latex
\sin \phi = \sin \alpha \sin \phi' + \cos \alpha \cos \phi' \cos (\lambda' - \beta)
```

The crop (left) shows fuzzy edges and potential text bleeding from imprecise bbox detection. The rendered version (right) is pixel-perfect, generated directly from the extracted LaTeX. For downstream applications (search, display, embedding), the rendered version is preferred.

---

## Text Cleaning: Remove Line Numbers

**Decision:** Auto-detect and remove margin line numbers (e.g., ICLR format: 000, 001, 002...).

**Why:** Academic paper submissions often have line numbers in margins for reviewer reference. These pollute extracted text and confuse semantic analysis.

**Implementation:** Regex pattern matches 3-digit numbers at line starts, removes if consistent pattern detected.

---

## Tools Not Used

### Marker (marker-pdf)
- Requires GPU, stuck on CPU after 5+ minutes
- GPL license restricts commercial use
- Would be good if we had dedicated GPU server

### Nougat (nougat-ocr)
- Requires GPU
- English only
- Semantic descriptions only, no actual image extraction
- CC-BY-NC license for model weights

### LayoutParser + Detectron2
- Heavy dependencies
- Would need separate model server
- Qwen3-VL handles layout detection well enough
