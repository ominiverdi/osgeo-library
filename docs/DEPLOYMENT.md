# Deployment

How to deploy and maintain the OSGeo Library server.

## Architecture Overview

The library has two server types:

| Server | Port | Transport | Purpose | Persistent |
|--------|------|-----------|---------|------------|
| **REST API** | 8095 | HTTP | Rust CLI, Matrix bot, web clients | Yes (systemd) |
| **MCP Server** | - | STDIO | Claude Desktop integration | No (spawned by Claude) |

### REST API Server (port 8095)

The main server for all programmatic access:
- **Rust CLI** (`osgeo-library chat`, `osgeo-library search`)
- **Matrix bot** (osgeo-llmagent) - runs on same server, accesses via localhost
- **Web clients** - if exposed via reverse proxy

Must be kept running as a persistent service (systemd or cron).

### MCP Server (STDIO)

For local Claude Desktop integration only:
- Spawned by Claude Desktop as a subprocess
- Uses STDIO transport (not network)
- Configured in `claude_desktop_config.json`
- Not a persistent daemon - Claude manages its lifecycle

```json
{
  "mcpServers": {
    "doclibrary": {
      "command": "python",
      "args": ["-m", "doclibrary.servers.mcp"],
      "cwd": "/path/to/osgeo-library"
    }
  }
}
```

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
uv pip install -r requirements.txt
uv pip install -e .
```

### 5. Start API Server

```bash
.venv/bin/python -m doclibrary.servers.api
# Or in background:
nohup .venv/bin/python -m doclibrary.servers.api >> ~/logs/osgeo-library.log 2>&1 &
```

### 6. Auto-start on Reboot

The REST API server must persist across reboots. The MCP server does NOT need
this - Claude Desktop spawns it on demand.

**Option A: crontab (no admin needed)**
```bash
crontab -e
# Add:
@reboot ~/github/osgeo-library/servers/start-server.sh >> ~/logs/osgeo-library.log 2>&1
```

**Option B: systemd (recommended for production)**
```bash
sudo cp servers/osgeo-library.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable osgeo-library
sudo systemctl start osgeo-library
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

# 3. Update dependencies and reinstall package
uv pip install -r requirements.txt
uv pip install -e .

# 4. Restart the API server
pkill -f "port 8095" || true
sleep 2
nohup .venv/bin/python -m doclibrary.servers.api >> ~/logs/osgeo-library.log 2>&1 &

# 5. Verify
curl -s http://localhost:8095/health | python3 -m json.tool
```

**One-liner from minto:**
```bash
ssh osgeo7-gallery "cd ~/github/osgeo-library && git pull && uv pip install -e . && pkill -f 'port 8095' || true; sleep 2 && nohup .venv/bin/python -m doclibrary.servers.api >> ~/logs/osgeo-library.log 2>&1 &"
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

| Component | Port | Status |
|-----------|------|--------|
| Embedding server | 8094 | Running (bge-m3-Q8_0.gguf) |
| REST API server | 8095 | Running |
| Database | 5432 | PostgreSQL + pgvector |
| Matrix bot (llmagent) | - | Accesses API via localhost:8095 |

### Service Checks

```bash
# Check API server
curl http://localhost:8095/health

# Check embedding server
curl http://localhost:8094/health
```

---

## REST API Endpoints

The API server exposes these endpoints for the Matrix bot and CLI:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server status and dependency checks |
| `/documents` | GET | List documents (paginated) |
| `/documents/{slug}` | GET | Document details with summary/keywords |
| `/documents/{slug}/elements` | GET | List elements with filtering |
| `/page/{slug}/{page_number}` | GET | Page image (base64) with metadata |
| `/search` | POST | Semantic search over documents |
| `/chat` | POST | LLM-powered Q&A with citations |
| `/element/{element_id}` | GET | Element details |
| `/image/{slug}/{path}` | GET | Serve element images |

### Element Listing Endpoint

The `/documents/{slug}/elements` endpoint supports fast browsing without LLM:

```bash
# List all figures from a document
curl "http://localhost:8095/documents/aibench/elements?element_type=figure"

# List tables on page 10
curl "http://localhost:8095/documents/usgs_snyder/elements?element_type=table&page=10"

# List all elements on page 5
curl "http://localhost:8095/documents/aibench/elements?page=5"
```

Query parameters:
- `element_type`: figure, table, equation, chart, diagram
- `page`: filter to specific page (1-indexed)
- `limit`: max results (default: 50, max: 100)
- `offset`: pagination offset

---

## Matrix Bot Integration (llmagent)

The osgeo-llmagent runs on the same server and accesses the library API locally.

### How It Works

```
Matrix User  -->  Matrix Server  -->  llmagent  -->  REST API (localhost:8095)
                                          |
                                          v
                                    Embedding Server (localhost:8094)
                                          |
                                          v
                                    PostgreSQL + pgvector
```

### llmagent Configuration

The bot connects to the library API via environment or config:

```bash
# In llmagent config or environment
OSGEO_LIBRARY_URL=http://localhost:8095
```

### Commands Supported

The bot can use these library features:

| Bot Command | API Endpoint | Description |
|-------------|--------------|-------------|
| Ask question | `POST /chat` | LLM-powered answer with citations |
| `!l <query>` | `POST /search` | Direct semantic search |
| `docs` | `GET /documents` | List available documents |
| `doc <slug>` | `GET /documents/{slug}` | Document details |
| `figures` | `GET /documents/{slug}/elements?element_type=figure` | List figures |
| `tables` | `GET /documents/{slug}/elements?element_type=table` | List tables |
| `page <N>` | `GET /page/{slug}/{N}` | View page image |
| `sources` | (from last /chat response) | Show citations |

### Keeping Services Alive

Both the API server and embedding server must be running for the bot to work.

**Systemd service (recommended):**

```bash
# /etc/systemd/system/osgeo-library.service
[Unit]
Description=OSGeo Library API Server
After=network.target postgresql.service

[Service]
Type=simple
User=your-user
WorkingDirectory=/home/your-user/github/osgeo-library
Environment=PATH=/home/your-user/github/osgeo-library/.venv/bin
ExecStart=/home/your-user/github/osgeo-library/.venv/bin/python -m doclibrary.servers.api
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable osgeo-library
sudo systemctl start osgeo-library
sudo systemctl status osgeo-library
```

**Check both services are healthy:**
```bash
curl -s http://localhost:8095/health | python3 -m json.tool
```

Expected response:
```json
{
    "status": "healthy",
    "embedding_server": true,
    "llm_server": true,
    "database": true,
    "version": "1.0.0"
}
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
pkill -f "port 8095" || true
nohup .venv/bin/python -m doclibrary.servers.api >> ~/logs/osgeo-library.log 2>&1 &
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
