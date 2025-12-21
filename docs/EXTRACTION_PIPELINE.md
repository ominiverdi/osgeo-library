# Extraction Pipeline

Step-by-step guide for processing PDFs and syncing to production.

## Current Setup (minto)

### Servers

| Service | Port | Model | Script |
|---------|------|-------|--------|
| Vision (extraction) | 8090 | Qwen3-VL-235B | `/media/nvme2g-a/llm_toolbox/servers/qwen3-vl-235b-8090.sh` |
| Text (enrichment) | 8080 | Qwen3-30B-A3B | `/media/nvme2g-a/llm_toolbox/servers/qwen3-30b-32k.sh` |
| Embedding | 8094 | BGE-M3-F16 | `/media/nvme2g-a/llm_toolbox/servers/bge-m3-embed-8094.sh` |

### Paths

| What | Path |
|------|------|
| Code | `/home/ominiverdi/github/osgeo-library/` |
| PDFs | `/home/ominiverdi/github/osgeo-library/pdfs/` |
| Extracted data | `/home/ominiverdi/github/osgeo-library/db/data/` |
| Database backups | `/home/ominiverdi/github/osgeo-library/db_backup/` |
| Logs | `/home/ominiverdi/github/osgeo-library/logs/` |
| Config | `/home/ominiverdi/github/osgeo-library/config.toml` |

### Database

- PostgreSQL 16 with pgvector extension
- Database: `osgeo_library`
- Auth: peer (Unix socket, current user)

---

## Pre-flight Checks

Before starting extraction, verify all services are running:

```bash
cd ~/github/osgeo-library
source .venv/bin/activate

# Check servers
curl -s http://localhost:8090/health && echo " - Vision OK" || echo " - Vision FAILED"
curl -s http://localhost:8080/health && echo " - Text OK" || echo " - Text FAILED"
curl -s http://localhost:8094/health && echo " - Embedding OK" || echo " - Embedding FAILED"

# Check database
psql -d osgeo_library -c "SELECT COUNT(*) FROM documents;" && echo " - Database OK"
```

### Start Servers (if needed)

```bash
# Embedding server (BGE-M3)
/media/nvme2g-a/llm_toolbox/servers/bge-m3-embed-8094.sh &

# Text/enrichment server (Qwen3-30B)
/media/nvme2g-a/llm_toolbox/servers/qwen3-30b-32k.sh &

# Vision server (Qwen3-VL-235B)
/media/nvme2g-a/llm_toolbox/servers/qwen3-vl-235b-8090.sh &
```

---

## Processing a New PDF

### Step 1: Extract

Convert PDF pages to images, detect elements (figures, tables, equations), crop them.

```bash
# Full document (can take hours for large PDFs)
python extract_all_pages.py pdfs/document.pdf --name doc_name --skip-existing

# Background with logging
nohup python extract_all_pages.py pdfs/document.pdf --name doc_name --skip-existing \
  > logs/doc_name_extraction.log 2>&1 &

# Check progress
tail -f logs/doc_name_extraction.log
ls db/data/doc_name/pages/ | wc -l  # pages extracted
```

**Time estimate:** ~107 seconds/page average (varies by content density)

### Step 2: Enrich

Generate contextual `search_text` for each element using the text model.

```bash
python enrich_elements.py doc_name
```

**Time estimate:** ~2.5 seconds/element

### Step 3: Ingest

Chunk text, generate embeddings, insert into PostgreSQL.

```bash
python ingest_to_db.py doc_name
```

**Time estimate:** ~2 minutes for most documents

### Step 4: Verify

```bash
# Check database
psql -d osgeo_library -c "
  SELECT d.slug, COUNT(DISTINCT p.id) as pages, COUNT(DISTINCT e.id) as elements 
  FROM documents d 
  LEFT JOIN pages p ON d.id = p.document_id 
  LEFT JOIN elements e ON d.id = e.document_id 
  WHERE d.slug = 'doc_name'
  GROUP BY d.slug;
"

# Test search
python search_service.py "query about new document" --limit 3
```

---

## Sync to Remote Server (osgeo7-gallery)

After local processing is complete, sync to production.

### Step 1: Backup Both Databases

```bash
# Local backup
mkdir -p db_backup
pg_dump osgeo_library > db_backup/osgeo_library_$(date +%Y%m%d).sql

# Remote backup
ssh osgeo7-gallery "mkdir -p ~/db_backup && pg_dump osgeo_library > ~/db_backup/osgeo_library_\$(date +%Y%m%d).sql"
```

### Step 2: Sync Element Images First

Sync images before database so queries don't reference missing files.

```bash
rsync -avz --progress db/data/ osgeo7-gallery:~/data/osgeo-library/
```

### Step 3: Update Database (Transactional)

Use a staging database to avoid downtime. The old database stays live until the new one is ready.

```bash
# Copy dump to remote
scp db_backup/osgeo_library_$(date +%Y%m%d).sql osgeo7-gallery:~/db_backup/

# Create staging database, restore, then swap
ssh osgeo7-gallery "
  dropdb --if-exists osgeo_library_new &&
  createdb osgeo_library_new &&
  psql -d osgeo_library_new -c 'CREATE EXTENSION vector;' &&
  psql -d osgeo_library_new < ~/db_backup/osgeo_library_$(date +%Y%m%d).sql &&
  psql -c 'ALTER DATABASE osgeo_library RENAME TO osgeo_library_old;' &&
  psql -c 'ALTER DATABASE osgeo_library_new RENAME TO osgeo_library;' &&
  dropdb osgeo_library_old
"
```

This ensures:
- No moment where the database is missing
- Queries continue against old DB until swap completes
- Swap is atomic (just a rename)

### Step 4: Verify Remote

```bash
ssh osgeo7-gallery "cd ~/github/osgeo-library && source .venv/bin/activate && \
  python search_service.py 'test query' --limit 3"
```

---

## Current Documents

As of 2025-12-20:

| Slug | Pages | Elements | Source File |
|------|-------|----------|-------------|
| digital_earth | 844 | 456 | ManualOfDigitalEarth_2020.pdf |
| usgs_snyder | 397 | 1041 | usgs_snyder1987.pdf |
| sam3 | 68 | 76 | sam3.pdf |
| aiseg_sam3 | 62 | 70 | aiSeg_sam3_2025.pdf |
| aibench | 47 | 30 | aiBench_pangaea_2025.pdf |
| torchgeo | 27 | 7 | torchgeo_acm_2025.pdf |
| aiseg | 25 | 13 | aiSeg_ag_2025.pdf |
| mlcs_libs | 24 | 5 | mlCS_libs_stewart_2025.pdf |
| alpine_change | 23 | 14 | 2511.00073v1.pdf |
| eo_distortions | 18 | 19 | 2403.04385.pdf |

**Total:** 10 documents, 1535 pages, 1731 elements

---

## Troubleshooting

### Extraction errors

**"Coordinate 'right' is less than 'left'"**
- Vision model returned invalid bounding box
- Usually happens with pages that have line numbers or unusual layouts
- Skip the page and continue: extraction still gets the text

**Timeout on extraction**
- Rich pages with many elements can take 3-5 minutes
- Normal for pages with many figures/tables/equations

### Enrichment failures

- Usually due to missing crop files or API errors
- Check if element crop exists in `db/data/doc_name/elements/`
- Re-run enrichment; it skips already-enriched elements

### Database issues

```bash
# Check connection
psql -d osgeo_library -c "SELECT 1;"

# Check pgvector extension
psql -d osgeo_library -c "SELECT * FROM pg_extension WHERE extname = 'vector';"

# Rebuild from backup
psql -d osgeo_library < db_backup/osgeo_library_YYYYMMDD.sql
```

---

## Remote Server Setup (osgeo7-gallery)

### Paths

| What | Path |
|------|------|
| Code | `~/github/osgeo-library/` |
| Data | `~/data/osgeo-library/` |
| Models | `~/models/bge-m3-Q8_0.gguf` |
| Backups | `~/db_backup/` |
| Logs | `~/logs/` |

### Services

```bash
# Check API server
curl http://localhost:8095/health

# Check embedding server  
curl http://localhost:8094/health

# Restart API server
cd ~/github/osgeo-library && source .venv/bin/activate
./servers/start-server.sh
```

### Updating Server Code

When new features are added to the API, deploy to osgeo7-gallery:

```bash
# 1. SSH to the server
ssh osgeo7-gallery

# 2. Pull latest code
cd ~/github/osgeo-library
git pull

# 3. Update dependencies (if requirements.txt changed)
source .venv/bin/activate
pip install -r requirements.txt

# 4. Restart the API server
pkill -f "uvicorn server:app --host 127.0.0.1 --port 8095"
sleep 1
./servers/start-server.sh >> ~/logs/osgeo-library.log 2>&1 &

# 5. Verify
curl -s http://localhost:8095/health | python3 -m json.tool
```

Or as a one-liner from minto:

```bash
ssh osgeo7-gallery "cd ~/github/osgeo-library && git pull && pkill -f 'port 8095'; sleep 1 && ./servers/start-server.sh >> ~/logs/osgeo-library.log 2>&1 &"
```
