# Extractions

Catalog of processed documents in `db/data/`.

## Summary

| Document | Pages | Figures | Tables | Equations | Size | Status |
|----------|-------|---------|--------|-----------|------|--------|
| SAM3 | 68 | 26 | 42 | 7 | 78 MB | complete |
| Alpine Change | 23 | 6 | 8 | 0 | 14 MB | complete |
| USGS Snyder | 397 | 53+ | 60+ | 651+ | 193 MB+ | in progress (238/397) |

---

## Batch Extraction - December 17, 2025

### Timing

- **Started:** Tue Dec 16 23:44 CET
- **sam3 finished:** Wed Dec 17 00:41 CET (~57 min for 52 pages)
- **alpine_change finished:** Wed Dec 17 00:53 CET (~12 min for 14 pages)
- **usgs_snyder:** in progress, estimated completion ~13:00 CET

### Processing Rate

| Page Type | Time |
|-----------|------|
| No elements | ~30s |
| 1-3 elements | ~60-90s |
| 4-6 elements | ~120-150s |
| 8-10 elements | ~200-220s |

Average: ~50-60s/page (varies with element count)

---

## SAM3 Paper

**File:** `sam3.pdf`  
**Topic:** Segment Anything Model 3 - Promptable Concept Segmentation  
**Pages:** 68 | **Elements:** 76 (26 figures, 42 tables, 7 equations, 1 chart)

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
**Pages:** 397 | **Elements:** 764+ so far (53 figures, 60 tables, 651 equations)

This is a math-heavy reference book with extensive projection formulas.

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
**Pages:** 23 | **Elements:** 14 (6 figures, 8 tables)

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

- **Model:** Qwen3-VL-235B (A22B-Instruct-UD-TQ1_0)
- **Server:** llama.cpp on localhost:8090
- **Context:** 8192 tokens
- **Page DPI:** 150

---

## Storage Estimates

| Per Page | Size |
|----------|------|
| Page image (PNG, 150 DPI) | ~500-700 KB |
| Annotated image | ~500-700 KB |
| Element crops (avg 2/page) | ~50-200 KB each |
| JSON metadata | ~2-5 KB |
| **Total per page** | **~1.2-1.5 MB** |

### Projection for 5000 PDFs

Assuming average 50 pages/PDF = 250,000 pages:
- ~300-375 GB storage
- ~3,500-4,000 hours processing (~5-6 months continuous)
