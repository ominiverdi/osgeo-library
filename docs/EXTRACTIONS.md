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

| Page Type | Pages | Avg Time |
|-----------|-------|----------|
| No elements | 92 | 47s |
| 1-3 elements | 161 | 81s |
| 4-6 elements | 42 | 173s |
| 7+ elements | 44 | 268s |
| **Total** | **339** | **107s** |

---

## SAM3 Paper

**File:** `sam3.pdf`  
**Topic:** Segment Anything Model 3 - Promptable Concept Segmentation

| Pages | Figures | Tables | Equations | Charts | Avg Time |
|-------|---------|--------|-----------|--------|----------|
| 68 | 26 | 42 | 7 | 1 | 55s |

---

## Alpine Habitat Change

**File:** `2511.00073v1.pdf`  
**Topic:** Alpine habitat classification using deep learning

| Pages | Figures | Tables | Equations | Avg Time |
|-------|---------|--------|-----------|----------|
| 23 | 6 | 8 | 0 | 59s |

---

## USGS Map Projections (Snyder 1987)

**File:** `usgs_snyder1987.pdf`  
**Topic:** Map Projections - A Working Manual

| Pages | Figures | Tables | Equations | Avg Time |
|-------|---------|--------|-----------|----------|
| 397 | 53+ | 60+ | 675+ | 126s |

*In progress (240/397 pages). This is a math-heavy reference book.*

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
| Total per page | ~1.2-1.5 MB |
| **Total for 250,000 pages** | **~300-375 GB** |

### Processing Time

At ~107s/page average (from actual measurements):

| Setup | Time |
|-------|------|
| Single GPU (current) | ~7,400 hours (~10 months) |
| 4 GPUs parallel | ~1,850 hours (~2.5 months) |
| 8 GPUs parallel | ~925 hours (~5 weeks) |
