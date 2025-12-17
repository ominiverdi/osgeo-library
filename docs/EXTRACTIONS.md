# Extractions

Catalog of processed documents.

## Full Extraction (db/data/) - December 17, 2025

All pages extracted with LLM element detection to `db/data/` structure.

| Document | Pages | Figures | Tables | Equations | Size | Status |
|----------|-------|---------|--------|-----------|------|--------|
| SAM3 | 68 | 26 | 42 | 7 | 78 MB | complete |
| Alpine Change | 23 | 6 | 8 | 0 | 14 MB | complete |
| USGS Snyder | 397 | 53+ | 60+ | 651+ | 193 MB+ | in progress (238/397) |

### Timing

- **Started:** Tue Dec 16 23:44 CET
- **sam3 finished:** Wed Dec 17 00:41 CET (~57 min for 52 new pages)
- **alpine_change finished:** Wed Dec 17 00:53 CET (~12 min for 14 new pages)
- **usgs_snyder:** in progress, estimated completion ~13:00 CET

### Processing Rate

| Page Type | Time |
|-----------|------|
| No elements | ~30s |
| 1-3 elements | ~60-90s |
| 4-6 elements | ~120-150s |
| 8-10 elements | ~200-220s |

Average overall: ~50-60s/page (varies heavily with element count)

---

## Demo Extraction (web/data/) - December 16, 2025

Partial extraction for web viewer demo. Only pages with detected elements.

| Document | Pages | Figures | Tables | Equations | Rendered |
|----------|-------|---------|--------|-----------|----------|
| SAM3 | 12 | 8 | 8 | 3 | 3 |
| USGS Snyder | 13 | 8 | 0 | 23 | 23 |
| Alpine Change | 9 | 6 | 8 | 0 | 0 |
| **Total** | **34** | **22** | **16** | **26** | **26** |

---

## SAM3 Paper

**File:** `sam3.pdf`  
**Topic:** Segment Anything Model 3 - Promptable Concept Segmentation  
**Output:** `db/data/sam3/` (full), `web/data/sam3/` (demo)

### Full Extraction Stats (68 pages)
- 26 figures
- 42 tables
- 7 equations (with LaTeX rendered)
- 1 chart
- 78 MB total

### Notable Pages

| Page | Elements | Notes |
|------|----------|-------|
| 1 | Figure 1 | Title figure, SAM2 vs SAM3 comparison |
| 2 | Figure 2 | Interactive refinement workflow |
| 3 | Figure 3 | Architecture diagram |
| 4 | Equation 1 | Similarity function with Iverson bracket |
| 5 | Figure 4 | Training pipeline |
| 6 | Figure 5 | Video segmentation examples |
| 7 | Tables 1-3 | Benchmark results |
| 8 | Figure 6, Tables 4-5 | Chart and results |
| 9 | Tables 6, 8, 9 | More benchmark results |
| 26 | Figure 7 | Domain adaptation visualization |
| 29 | Figure 8 | Detailed architecture |
| 30 | Equations 1-3 | Loss functions |

---

## USGS Map Projections (Snyder 1987)

**File:** `usgs_snyder1987.pdf`  
**Topic:** Map Projections - A Working Manual  
**Output:** `db/data/usgs_snyder/` (full), `web/data/usgs_snyder/` (demo)

### Full Extraction Stats (397 pages) - IN PROGRESS
- 53+ figures (so far)
- 60+ tables (so far)
- 651+ equations (so far) - this is a math-heavy book!
- 193 MB+ (so far)

### Notable Pages

| Page | Elements | Notes |
|------|----------|-------|
| 1 | Figure 1 | Title page / frontispiece |
| 21 | Figure 2 | Meridians and parallels on sphere |
| 32 | Figure 3 | Tissot's Indicatrix |
| 34 | Figures 4, 4-cont | Distortion patterns |
| 42 | Figure 5 | Spherical triangle |
| 44 | Equations 5-9 to 5-14a | Trigonometric formulas (7 equations) |
| 51 | Figure 7 | Gerardus Mercator portrait |
| 52 | Figure 8 | The Mercator projection |
| 147 | Equations 18-37 to 18-50 | Projection formulas (7 equations) |
| 189 | Equations 1-4 | Perspective projection (4 equations) |
| 192 | Equations 23-62 to 23-81 | Inverse projection (5 equations) |

---

## Alpine Habitat Change

**File:** `2511.00073v1.pdf`  
**Topic:** Alpine habitat classification using deep learning  
**Output:** `db/data/alpine_change/` (full), `web/data/alpine_change/` (demo)

### Full Extraction Stats (23 pages)
- 6 figures
- 8 tables
- 0 equations
- 14 MB total

### Notable Pages

| Page | Elements | Notes |
|------|----------|-------|
| 6 | Figure 1 | Study area map |
| 7 | Table 1 | Dataset statistics |
| 8 | Tables 2-3 | Model configurations |
| 9 | Figure 2 | Results visualization |
| 12 | Table 4 | Performance metrics |
| 13 | Figures 3-4 | Confusion matrices / charts |
| 14 | Figure 5, Table 5 | Additional results |
| 15 | Figure 6, Table 6 | Ablation study |
| 16 | Tables 7-8 | Final comparison |

---

## Model Configuration

**Model:** Qwen3-VL-235B (A22B-Instruct-UD-TQ1_0)  
**Server:** llama.cpp on localhost:8090  
**Context:** 8192 tokens  
**Page DPI:** 150

---

## Storage Estimates

Based on current extractions:

| Per Page | Size |
|----------|------|
| Page image (PNG, 150 DPI) | ~500-700 KB |
| Annotated image | ~500-700 KB |
| Element crops (avg 2/page) | ~50-200 KB each |
| JSON metadata | ~2-5 KB |
| **Total per page** | **~1.2-1.5 MB** |

### Projection for 5000 PDFs

Assuming average 50 pages/PDF:
- 250,000 pages total
- ~300-375 GB storage
- ~3,500-4,000 hours processing time (~5-6 months continuous)

For batch processing at scale, consider:
- Multiple GPU instances in parallel
- Lower DPI for initial pass
- Selective extraction (only pages with detected elements)
