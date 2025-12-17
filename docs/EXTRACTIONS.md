# Extractions

Catalog of processed documents in `db/data/`.

## Summary

| Document | Pages | Figures | Tables | Equations | Total Elements | Status |
|----------|-------|---------|--------|-----------|----------------|--------|
| SAM3 | 68 | 26 | 42 | 7 | 76 | complete |
| Alpine Change | 23 | 6 | 8 | 0 | 14 | complete |
| USGS Snyder | 397 | 63 | 69 | 909 | 1041 | complete |
| **Total** | **488** | **95** | **119** | **916** | **1131** | |

---

## Batch Extraction - December 17, 2025

### Timing

- **Started:** Tue Dec 16 23:44 CET
- **sam3 finished:** Wed Dec 17 00:41 CET (~57 min for 52 pages)
- **alpine_change finished:** Wed Dec 17 00:53 CET (~12 min for 14 pages)
- **usgs_snyder finished:** Wed Dec 17 12:46 CET (~11.9 hours for 384 pages)

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

| Pages | Figures | Tables | Equations | Total | Avg Time |
|-------|---------|--------|-----------|-------|----------|
| 397 | 63 | 69 | 909 | 1041 | 111s |

*Extraction complete. 10 blank pages (cover, section dividers). Math-heavy reference book with 909 equations.*

---

## Database Ingestion - December 17, 2025

All documents enriched and ingested to PostgreSQL with embeddings.

| Metric | Count |
|--------|-------|
| Documents | 3 |
| Pages | 488 |
| Text chunks | 2,195 |
| Elements | 1,131 |
| Embeddings | 3,326 (chunks + elements) |

**Enrichment:** ~47 minutes for 1131 elements (Qwen3-30B-A3B)  
**Ingestion:** ~100 seconds for all documents (BGE-M3 embeddings)

---

## Model Configuration

- **Vision Model:** Qwen3-VL-235B (A22B-Instruct-UD-TQ1_0) - port 8090
- **Enrichment Model:** Qwen3-30B-A3B - port 8080
- **Embedding Model:** BGE-M3 (1024 dimensions) - port 8094
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
