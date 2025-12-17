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

| Pages | Figures | Tables | Equations | Charts |
|-------|---------|--------|-----------|--------|
| 68 | 26 | 42 | 7 | 1 |

---

## Alpine Habitat Change

**File:** `2511.00073v1.pdf`  
**Topic:** Alpine habitat classification using deep learning

| Pages | Figures | Tables | Equations |
|-------|---------|--------|-----------|
| 23 | 6 | 8 | 0 |

---

## USGS Map Projections (Snyder 1987)

**File:** `usgs_snyder1987.pdf`  
**Topic:** Map Projections - A Working Manual

| Pages | Figures | Tables | Equations |
|-------|---------|--------|-----------|
| 397 | 53+ | 60+ | 675+ |

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
| **Total per page** | **~1.2-1.5 MB** |

**Total: ~300-375 GB**

### Processing Time

| Setup | Time |
|-------|------|
| Single GPU (current) | ~3,500-4,000 hours (~5-6 months) |
| 4 GPUs parallel | ~1,000 hours (~6 weeks) |
| 8 GPUs parallel | ~500 hours (~3 weeks) |
