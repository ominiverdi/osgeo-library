# Extractions

Catalog of processed documents in `db/data/`.

## Summary

| Document | Pages | Figures | Tables | Equations | Size | Status |
|----------|-------|---------|--------|-----------|------|--------|
| SAM3 | 68 | 26 | 42 | 7 | 78 MB | complete |
| Alpine Change | 23 | 6 | 8 | 0 | 14 MB | complete |
| USGS Snyder | 397 | 53+ | 60+ | 675+ | 193 MB+ | in progress (240/397) |

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
**Pages with elements:** 45/68

| Page | Elements |
|------|----------|
| 1 | Figure 1 |
| 2 | Figure 2 |
| 3 | Figure 3 |
| 4 | Equation 1 |
| 5 | Figure 4 |
| 6 | Figure 5 |
| 7 | Table 1, Table 2, Table 3 |
| 8 | Figure 6, Table 4, Table 5 |
| 9 | Table 6, Table 8, Table 9 |
| 23 | Table 10, Table 11, Table 12 |
| 24 | Table 13, Table 14 |
| 25 | Table 15, Table 16, Table 17 |
| 26 | Figure 7 |
| 27 | Table 18, Table 19 |
| 29 | Figure 8 |
| 30 | Equation 1, Equation 2, Equation 3 |
| 31 | Figure 9, Equation 1 |
| 34 | Table 20 |
| 35 | Table 21 |
| 36 | Table 22 |
| 37 | Table 23 |
| 38 | Table 24 |
| 40 | Table 25 |
| 43 | Figure 10 |
| 44 | Table 26, Table 27, Table 28 |
| 45 | Table 29, Table 30, Equation 1 |
| 46 | Table 31, Equation 1 |
| 48 | Figure 11 |
| 49 | Figure 12, Figure 13 |
| 50 | Figure 14 |
| 51 | Figure 15, Figure 16 |
| 52 | Table 32 |
| 53 | Table 33, Table 34 |
| 54 | Figure 17, Table 35, Table 36 |
| 55 | Table 37 |
| 57 | Table 38 |
| 58 | Figure 18 |
| 59 | Figure 19, Figure 20 |
| 62 | Figure 21 |
| 63 | Figure 22 |
| 64 | Figure 1 |
| 65 | Figure 23 |
| 66 | Figure 24, Table 39 |
| 67 | Table 40 |
| 68 | Table 41 |

---

## Alpine Habitat Change

**File:** `2511.00073v1.pdf`  
**Topic:** Alpine habitat classification using deep learning  
**Pages:** 23 | **Elements:** 14 (6 figures, 8 tables)  
**Pages with elements:** 9/23

| Page | Elements |
|------|----------|
| 6 | Figure 1 |
| 7 | Table 1 |
| 8 | Table 2, Table 3 |
| 9 | Figure 2 |
| 12 | Table 4 |
| 13 | Figure 3, Figure 4 |
| 14 | Figure 5, Table 5 |
| 15 | Figure 6, Table 6 |
| 16 | Table 7, Table 8 |

---

## USGS Map Projections (Snyder 1987)

**File:** `usgs_snyder1987.pdf`  
**Topic:** Map Projections - A Working Manual  
**Pages:** 397 | **Elements:** 788+ so far (53 figures, 60 tables, 675 equations)  
**Pages with elements:** 187/240 extracted so far (78%)

This is a math-heavy reference book with 675+ equations extracted so far.

Full element list will be generated when extraction completes.

---

## Model Configuration

- **Model:** Qwen3-VL-235B (A22B-Instruct-UD-TQ1_0)
- **Server:** llama.cpp on localhost:8090
- **Context:** 8192 tokens
- **Page DPI:** 150

---

## Estimates for 5000 PDFs

Assuming average 50 pages/PDF = 250,000 pages total.

### Storage

| Per Page | Size |
|----------|------|
| Page image (PNG, 150 DPI) | ~500-700 KB |
| Annotated image | ~500-700 KB |
| Element crops (avg 2/page) | ~50-200 KB each |
| JSON metadata | ~2-5 KB |
| **Total per page** | **~1.2-1.5 MB** |

**Total: ~300-375 GB**

### Processing Time

| Setup | Time |
|-------|------|
| Single GPU (current) | ~3,500-4,000 hours (~5-6 months) |
| 4 GPUs parallel | ~1,000 hours (~6 weeks) |
| 8 GPUs parallel | ~500 hours (~3 weeks) |
