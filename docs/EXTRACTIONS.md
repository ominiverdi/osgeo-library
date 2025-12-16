# Extractions

Catalog of processed documents.

## Summary

| Document | Pages | Figures | Tables | Equations | Rendered |
|----------|-------|---------|--------|-----------|----------|
| SAM3 | 12 | 8 | 8 | 3 | 3 |
| USGS Snyder | 13 | 8 | 0 | 23 | 23 |
| Alpine Change | 9 | 6 | 8 | 0 | 0 |
| **Total** | **34** | **22** | **16** | **26** | **26** |

---

## SAM3 Paper

**File:** `sam3.pdf` (aiSeg_sam3_2025.pdf)  
**Topic:** Segment Anything Model 3 - Promptable Concept Segmentation  
**Output:** `web/data/sam3/`

### Pages Extracted

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
**Output:** `web/data/usgs_snyder/`

### Pages Extracted

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
**Output:** `web/data/alpine_change/`

### Pages Extracted

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

## Detection Timing

Average per page (Qwen3-VL-235B):

| Document | Avg Time |
|----------|----------|
| SAM3 | ~40s |
| USGS Snyder | ~42s |
| Alpine Change | ~35s |

Processing rate: ~75-90 pages/hour
