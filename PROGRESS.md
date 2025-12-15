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

## Next Steps

### Immediate
- [ ] Colleagues evaluate extraction quality using comparison website
- [ ] Extract more pages when API rate limits reset
- [ ] Test second PDF sample (2403.04385.pdf)

### Short term
- [ ] Design `osgeo_research_kb` database schema
- [ ] Extract individual figures (not just page images)
- [ ] Add vector embeddings for semantic search

### Long term
- [ ] Process full library (~5000 PDFs)
- [ ] Implement `search_research_papers()` function
- [ ] Enable queries like "show me the SAM3 architecture diagram"

---

## How to Test

### Run the comparison website

```bash
# On osgeo7-gallery
cd ~/github/osgeo-library/web
../.venv/bin/python -m http.server 8765

# From your machine, create SSH tunnel
ssh -L 8765:localhost:8765 osgeo7-gallery

# Open http://localhost:8765 in browser
```

### Run extraction on a new PDF

```bash
cd ~/github/osgeo-library

# Traditional
.venv/bin/python extract_pdf.py /path/to/paper.pdf --output results.json

# Multimodal (uses API quota)
.venv/bin/python extract_multimodal.py /path/to/paper.pdf --pages 1,2,3 --model gemini
```

### Generate comparison data

```bash
.venv/bin/python generate_comparison.py /path/to/paper.pdf \
  --traditional trad.json \
  --multimodal multi.json \
  --pages 1 \
  --output-dir web
```

---

## Questions for Colleagues

1. Is the multimodal figure description quality good enough?
2. What other information should we extract?
3. Priority: more papers or deeper extraction on fewer papers first?
