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

## Embedding Model: BAAI/bge-m3

**Decision:** Use BAAI/bge-m3 for semantic search embeddings.

**Alternatives considered (Dec 2025):**

| Model | Type | Size | Dimensions | Key Feature |
|-------|------|------|------------|-------------|
| **BAAI/bge-m3** | **Open** | **568M** | **1024** | **Battle-tested, multilingual, hybrid search** |
| GritLM-7B | Open | 7B | 4096 | Trained on scientific corpora |
| NV-Embed-v2 | Open | Large | 4096 | Top MTEB score, 32k context |
| Alibaba gte-Qwen2-1.5B | Open | 1.5B | 1536 | Instruction-tuned, 32k context |
| nomic-embed-text-v2-moe | Open | 475M | 768 | MoE architecture, efficient |
| OpenAI text-embedding-3-large | API | - | 3072 | Excellent accuracy, 8k context |
| Cohere Embed v3 | API | - | 1024 | Strong multilingual |

**Domain-specific alternatives:**
- **SciBERT**: Pre-trained on biomedical/scientific text
- **SPECTER-v2**: Unsupervised retriever for scientific papers
- **BioBERT**: Specialized for biomedical text

**Why BGE-M3:**
1. **Proven performance**: Widely used for RAG, battle-tested in production
2. **Small and fast**: 568M params, 1.16GB GGUF, fast inference
3. **Good for mixed content**: Handles technical text, equations (as text), tables
4. **Multilingual**: Supports 100+ languages
5. **Local inference**: No API costs, runs on llama.cpp

**Trade-off:** GritLM-7B is specifically trained on scientific corpora and might perform better on domain-specific queries, but it's 12x larger (7B vs 568M). We start with BGE-M3 for efficiency; can upgrade if retrieval quality needs improvement.

**Server configuration:**
```bash
# Port 8094 - embedding server
llama-server \
  --model models/bge-m3/bge-m3-F16.gguf \
  --embedding \
  --host 0.0.0.0 --port 8094 \
  -c 8192 -ngl 999
```

**API usage:**
```bash
curl http://localhost:8094/embedding \
  -H "Content-Type: application/json" \
  -d '{"input": "Map projection equations"}'
```

**Future evaluation:** Compare retrieval quality across embedding models (BGE-M3 vs GritLM-7B vs domain-specific) using a test set of scientific queries. Metrics: precision@k, recall, MRR on manually labeled relevant chunks/elements.

---

## Element Enrichment: Qwen3-30B-A3B

**What is enrichment?**

When we extract elements (figures, tables, equations), the vision model provides a visual description: "Map showing the study area with colored overlays..." But this description alone isn't enough for good search. A researcher might search for "alpine habitat classification Austria" or "change detection methodology" - terms that aren't in the visual description but ARE in the surrounding page text.

Enrichment generates a **search_text** field that connects each element to its page context:
- What does this element explain in THIS section of the paper?
- What technical terms would a researcher use to find it?
- What domain/application is it relevant to?

This search_text is what gets embedded and searched, not the raw visual description.

**Decision:** Use Qwen3-30B-A3B (MoE, ~3B active params) for generating search_text.

**Alternatives tested (Dec 2025):**

| Model | Avg Time | Quality |
|-------|----------|---------|
| **Qwen3-30B-A3B** | **2.5s** | Concise, domain-aware, correct technical terms |
| Mistral-Small | 14.8s | More verbose, good but slower |

**Why Qwen3-30B:**
1. **6x faster** than Mistral-Small (vulkan vs rocm on this chipset)
2. **Domain-aware** - correctly identified "IMW Modified Polyconic" projection from context
3. **Concise output** - no filler phrases, direct search terms
4. **MoE efficiency** - 30B total params but only ~3B active, fast inference

**Enrichment prompt:**
```
/no_think
Page content:
{page_text}

Element: {element_type} "{label}"
Extracted: {description}

What does this element explain in this context? List key search terms. 2-3 sentences, no filler.
```

**Example output (equation):**
> "This element explains the forward projection formulas for the IMW Modified Polyconic map projection, calculating coordinates (Xb, Yb, Xc, Yc) based on latitude and longitude parameters. Key search terms: Modified Polyconic, map projection, forward formulas, latitude longitude, coordinate calculation."

**Processing time:** ~47 minutes for 1131 elements (all three documents)

---

## Search Threshold and Keyword Extraction

**Decision:** Use distance threshold of 0.985 (5% relevance) and extract keywords from natural language queries.

### The Problem

Semantic search with BGE-M3 embeddings returns a distance score (L2 distance) for each result. Lower distance = better match. But what threshold should filter out irrelevant results?

**Initial threshold (0.94 / 20% relevance)** was too strict for entity searches:

| Query | Best Match Distance | Passed 0.94? |
|-------|---------------------|--------------|
| `TorchGeo deep learning` | 0.82 | Yes |
| `map projection equations` | 0.85 | Yes |
| `Adam Stewart` (person name) | 0.956 | **No** |
| `Adam J. Stewart` | 0.946 | **No** |

Person names and specific entities don't have strong semantic meaning to the embedding model - they're just tokens. A threshold of 0.94 filtered them out.

### Solution 1: Lower Threshold to 0.985

**New threshold: 0.985 (5% relevance)**

This allows entity searches while still filtering noise:

| Query | Distance | Passes 0.985? |
|-------|----------|---------------|
| `Adam Stewart` | 0.956 | Yes |
| `Adam J. Stewart` | 0.946 | Yes |
| `Stewart Adam` (reversed) | 0.981 | Yes |
| `Adem Stewart` (typo) | 0.999 | No |
| `Adam Steward` (wrong name) | 1.079 | No |

The threshold correctly accepts:
- Exact name matches
- With middle initial
- Reversed order

And rejects:
- Significant typos
- Wrong names entirely

### Solution 2: Keyword Extraction for Questions

Natural language questions add noise that hurts semantic matching:

| Query | Best Distance |
|-------|---------------|
| `what papers include Adam Stewart somehow?` | 0.992 |
| `papers Adam Stewart` (keywords only) | 0.919 |

Stopwords like "what", "include", "somehow" dilute the semantic signal.

**Implementation:** The search function now:
1. Extracts keywords by removing stopwords (what, how, is, include, somehow, etc.)
2. Searches with BOTH the original query AND the keywords
3. Keeps the best (lowest) score for each result
4. Filters by threshold

```python
STOPWORDS = {'what', 'which', 'who', 'how', 'is', 'are', 'include', 'somehow', ...}

def extract_keywords(query: str) -> str:
    # Preserves capitalized words (proper nouns like "Adam Stewart")
    # Removes stopwords from lowercase words
    ...
```

**Result:** Colloquial questions now work:
```
$ osgeo-library search "what papers include Adam Stewart somehow?"
1 results:
[t:1] TEXT chunk 0 - Mlcs Libs p.24 | 25%
24 Adam J. Stewart et al. Stewart, Adam, Nils Lehmann...
```

### Trade-offs

| Threshold | Pros | Cons |
|-----------|------|------|
| 0.94 (strict) | Less noise | Misses entity/name searches |
| **0.985 (current)** | **Finds names, handles typos well** | **May include marginally relevant results** |
| 1.0+ (loose) | Finds everything | Too much noise |

---

## Hybrid Search: Semantic + BM25

**Decision:** Combine semantic (vector) search with BM25 (keyword) search for best results.

### The Problem

Semantic search alone struggles with:
- Person names ("Adam Stewart")
- Exact terms and acronyms ("TorchGeo", "SSL4EO-L")  
- Specific identifiers

These don't have strong semantic meaning - they're just tokens to the embedding model.

### Solution: Hybrid Search

We now run **both** search methods and merge results:

1. **Semantic search** (BGE-M3 embeddings) - finds conceptually related content
2. **BM25 keyword search** (PostgreSQL tsvector) - finds exact term matches

Results are deduplicated, keeping the best score for each document.

**Implementation:**

```sql
-- Added tsvector columns for full-text search
ALTER TABLE chunks ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

ALTER TABLE elements ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', 
        label || ' ' || description || ' ' || search_text
    )) STORED;

-- GIN indexes for fast lookup
CREATE INDEX idx_chunks_tsv ON chunks USING GIN(tsv);
CREATE INDEX idx_elements_tsv ON elements USING GIN(tsv);
```

**Score normalization:** BM25 returns higher-is-better scores (0-1). We convert to distance (lower-is-better) for consistency: `distance = 1 - (bm25_score * 2)`.

### Results

Before (semantic only):
```
$ osgeo-library search "Adam Stewart"
No results found.
```

After (hybrid):
```
$ osgeo-library search "Adam Stewart"
10 results:
[t:1] Mlcs Libs p.24 | 100% - Adam J. Stewart et al...
[t:2] Torchgeo p.22 | 100% - [117] Andreas Steiner...Adam Stewart...
...
```

### Performance

| Search Type | Query Time | Index Size |
|-------------|------------|------------|
| Semantic (ivfflat) | ~50ms | ~4MB per 10k vectors |
| BM25 (GIN) | ~5ms | ~1MB per 10k docs |
| Hybrid (both) | ~60ms | Both |

The overhead is minimal since PostgreSQL handles both efficiently.

### When Each Method Wins

| Query Type | Winner | Example |
|------------|--------|---------|
| Concepts/topics | Semantic | "deep learning for satellite imagery" |
| Person names | BM25 | "Adam Stewart" |
| Exact terms | BM25 | "TorchGeo" |
| Natural language questions | Both (via keyword extraction) | "what papers include Adam Stewart?" |
| Synonyms/related terms | Semantic | "remote sensing" finds "satellite imagery" |

---