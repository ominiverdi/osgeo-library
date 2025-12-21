# Deployment

How to deploy and maintain the OSGeo Library server.

## Requirements

- PostgreSQL 17 with pgvector extension
- llama.cpp (for embedding server)
- Python 3.10+ with venv
- chafa (optional, for CLI image preview)

---

## Server Structure

```
~/
├── github/osgeo-library/           # Code (git repo)
├── data/osgeo-library/             # Element images and page renders
│   ├── alpine_change/elements/
│   ├── sam3/elements/
│   └── usgs_snyder/elements/
├── models/
│   └── bge-m3-Q8_0.gguf            # Embedding model (606MB)
└── logs/
```

---

## Initial Setup

### 1. Clone and Configure

```bash
cd ~/github
git clone https://github.com/ominiverdi/osgeo-library.git
cd osgeo-library
cp config.example.toml config.toml
nano config.toml
```

Example `config.toml`:
```toml
[llm]
url = "https://openrouter.ai/api/v1/chat/completions"
model = "qwen/qwen3-30b-a3b"
api_key = "sk-or-v1-your-key-here"

[paths]
data_dir = "/home/user/data/osgeo-library"
```

### 2. Start Embedding Server

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/bge-m3-Q8_0.gguf \
  --embedding --host 127.0.0.1 --port 8094 \
  -c 2048 -b 512 -ub 512 -np 1 -t 4
```

### 3. Create Database

```bash
createdb osgeo_library
psql -d osgeo_library -c "CREATE EXTENSION vector;"
psql -d osgeo_library < ~/data/osgeo-library/osgeo_library.sql
```

### 4. Setup Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5. Start API Server

```bash
./servers/start-server.sh
```

### 6. Auto-start on Reboot

```bash
crontab -e
# Add:
@reboot ~/github/osgeo-library/servers/start-server.sh >> ~/logs/osgeo-library.log 2>&1
```

---

## Updating Server Code

When new features are added to the API:

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

**One-liner from minto:**
```bash
ssh osgeo7-gallery "cd ~/github/osgeo-library && git pull && pkill -f '\-\-port 8095'; sleep 2 && ./servers/start-server.sh >> ~/logs/osgeo-library.log 2>&1 &"
```

---

## Syncing Data to Remote

After processing new documents locally, sync to production.

### 1. Backup Both Databases

```bash
# Local backup
mkdir -p db_backup
pg_dump osgeo_library > db_backup/osgeo_library_$(date +%Y%m%d).sql

# Remote backup
ssh osgeo7-gallery "mkdir -p ~/db_backup && pg_dump osgeo_library > ~/db_backup/osgeo_library_\$(date +%Y%m%d).sql"
```

### 2. Sync Element Images

Sync images before database so queries don't reference missing files.

```bash
rsync -avz --progress db/data/ osgeo7-gallery:~/data/osgeo-library/
```

### 3. Update Database

Use a staging database to avoid downtime:

```bash
# Copy dump to remote
scp db_backup/osgeo_library_$(date +%Y%m%d).sql osgeo7-gallery:~/db_backup/

# Create staging, restore, then swap
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

### 4. Verify

```bash
ssh osgeo7-gallery "curl -s http://localhost:8095/health"
```

---

## Configuration

All settings are managed through `config.py`:

1. Environment variables (`OSGEO_*`)
2. `config.local.toml` (gitignored, for local overrides)
3. `config.toml` (gitignored)
4. `~/.config/osgeo-library/config.toml`
5. Built-in defaults

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OSGEO_LLM_URL` | LLM API endpoint |
| `OSGEO_LLM_MODEL` | Model name |
| `OSGEO_LLM_API_KEY` | API key for remote services |
| `OSGEO_EMBED_URL` | Embedding server endpoint |
| `OSGEO_DB_NAME` | PostgreSQL database |
| `OSGEO_DB_HOST` | Database host |
| `OSGEO_DATA_DIR` | Path to extracted data |

### Verify Configuration

```bash
python config.py
```

---

## Production Status (osgeo7-gallery)

| Component | Status |
|-----------|--------|
| Git repo | Deployed |
| Embedding model | Running (bge-m3-Q8_0.gguf) |
| Embedding server | Running on port 8094 |
| API server | Running on port 8095 |
| Database | PostgreSQL + pgvector |

### Service Checks

```bash
# Check API server
curl http://localhost:8095/health

# Check embedding server
curl http://localhost:8094/health
```

---

## Troubleshooting

### Server not responding

```bash
# Check if process is running
ps aux | grep "port 8095"

# Check logs
tail -50 ~/logs/osgeo-library.log

# Restart
pkill -f '\-\-port 8095'
./servers/start-server.sh >> ~/logs/osgeo-library.log 2>&1 &
```

### Database connection failed

```bash
# Check connection
psql -d osgeo_library -c "SELECT 1;"

# Check pgvector extension
psql -d osgeo_library -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

### Embedding server down

```bash
# Check health
curl http://localhost:8094/health

# Restart (example for osgeo7-gallery)
pkill -f "port 8094"
~/llama.cpp/build/bin/llama-server \
  -m ~/models/bge-m3-Q8_0.gguf \
  --embedding --host 127.0.0.1 --port 8094 \
  -c 2048 -b 512 -ub 512 -np 1 -t 4 &
```
