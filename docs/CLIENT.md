# OSGeo Library CLI Client

A lightweight command-line client for searching and chatting with the OSGeo Library.

## Installation

### Download Binary (Recommended)

Download the latest release for your platform from:
https://github.com/ominiverdi/osgeo-library/releases

```bash
# Linux x86_64
wget https://github.com/ominiverdi/osgeo-library/releases/latest/download/osgeo-library-linux-x86_64
chmod +x osgeo-library-linux-x86_64
sudo mv osgeo-library-linux-x86_64 /usr/local/bin/osgeo-library

# macOS x86_64
wget https://github.com/ominiverdi/osgeo-library/releases/latest/download/osgeo-library-macos-x86_64
chmod +x osgeo-library-macos-x86_64
sudo mv osgeo-library-macos-x86_64 /usr/local/bin/osgeo-library

# macOS ARM (Apple Silicon)
wget https://github.com/ominiverdi/osgeo-library/releases/latest/download/osgeo-library-macos-aarch64
chmod +x osgeo-library-macos-aarch64
sudo mv osgeo-library-macos-aarch64 /usr/local/bin/osgeo-library
```

### Build from Source

Requires [Rust](https://rustup.rs/):

```bash
cd clients/rust
cargo build --release
sudo cp target/release/osgeo-library /usr/local/bin/
```

### Image Preview Dependency

For terminal image preview (`--show` flag), install [chafa](https://hpjansson.org/chafa/):

```bash
# Debian/Ubuntu
sudo apt install chafa

# macOS
brew install chafa

# Fedora
sudo dnf install chafa
```

## Connection

The client connects to the OSGeo Library API server at `http://127.0.0.1:8095` by default.

### Local Server

If you're on the server machine, the API should already be running. Check with:

```bash
osgeo-library health
```

### Remote Access (SSH Tunneling)

To access from a remote machine, set up SSH port forwarding:

```bash
ssh -L 8095:localhost:8095 user@osgeo-server
```

Then run the client locally - it will connect through the tunnel.

### Custom Server URL

Override the server URL with the `--server` flag or `OSGEO_SERVER_URL` environment variable:

```bash
osgeo-library --server http://myserver:8095 search "projection"
# or
export OSGEO_SERVER_URL=http://myserver:8095
osgeo-library search "projection"
```

## Commands

### List Documents

Browse the document library:

```bash
# List all documents with summaries
osgeo-library docs

# Paginated list
osgeo-library docs --page 2 --limit 10

# Sort by different fields
osgeo-library docs --sort page_count
osgeo-library docs --sort date_added
```

**Docs options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--page N` | `-p` | Page number (default: 1) |
| `--limit N` | `-n` | Results per page (default: 20) |
| `--sort FIELD` | `-s` | Sort by: title, date_added, page_count |

### Document Details

Get detailed information about a specific document:

```bash
osgeo-library doc usgs_snyder
osgeo-library doc torchgeo
```

Shows: title, page count, summary, keywords, license, and element counts (figures, tables, equations, etc.)

### Search

Search for elements (figures, tables, equations) by semantic similarity:

```bash
# Basic search
osgeo-library search "map projection"

# Filter by element type
osgeo-library search "habitat distribution" --type table
osgeo-library search "coordinate transformation" --type equation

# Limit results
osgeo-library search "segmentation" --num 5

# Show image preview in terminal
osgeo-library search "mercator" --type equation --show

# Open image in GUI viewer
osgeo-library search "alpine vegetation" --type figure --open

# Open multiple images at once
osgeo-library search "change detection" -t table --open 1,2,3,4
osgeo-library search "neural network" -t figure --open 1,2,3,4
osgeo-library search "coordinate system" -t equation --open 1,2,3,4

# Mixed elements (all types)
osgeo-library search "land cover classification" --elements-only --open 1,2,3,4
```

**Element types:** `figure`, `table`, `equation`

**Search options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--type TYPE` | `-t` | Filter by element type |
| `--num N` | `-n` | Number of results (default: 3) |
| `--show` | `-s` | Preview images in terminal (requires chafa) |
| `--open` | `-o` | Open images in GUI viewer |

### Interactive Chat

```bash
osgeo-library
# or explicitly:
osgeo-library chat
```

Starts an interactive session with the LLM. The chat mode supports:

- Natural language questions about the document library
- Citation tracking with tags like `[f:1]`, `[tb:2]`, `[eq:3]`
- Commands within the chat session

**Chat Commands:**

| Command | Description |
|---------|-------------|
| **Browse** | |
| `docs` | List documents in library |
| `doc <N\|slug>` | Select document (e.g., `doc 1` or `doc usgs_snyder`) |
| `page [slug] <N>` | View page (e.g., `page 55` or `page usgs_snyder 55`) |
| `next` / `n` | Navigate to next page (or start docs listing) |
| `prev` / `p` | Navigate to previous page (or start docs listing) |
| **Elements** | |
| `figures` | List figures on current page (or `figures all`) |
| `tables` | List tables on current page (or `tables all`) |
| `equations` | List equations on current page (or `equations all`) |
| **View** | |
| `show <N>` | Display element in terminal (e.g., `show 1` or `show 1,2,3`) |
| `open <N>` | Open element in GUI viewer |
| `open page <N>` | Open page in GUI viewer |
| **Search** | |
| `search <query>` | Semantic search (no LLM) |
| `sources` | Show sources from the last answer |
| `<question>` | Ask a question (uses LLM) |
| **Other** | |
| `health` / `status` / `stats` | Show server status |
| `help` | Show available commands |
| `quit` / `exit` / `q` | Exit the chat |

### Health Check

Check if the server is running and responsive:

```bash
osgeo-library health
```

Returns server status including:
- Overall status (healthy/degraded)
- Embedding server availability
- LLM server availability  
- Database connectivity
- API version

In chat mode, you can also use `health`, `status`, or `stats` commands.

## GUI Image Viewer

When using `--open` or the `open` command in chat mode, images are opened in your system's default image viewer.

```bash
# Open first result in GUI viewer
osgeo-library search "mercator" -t equation --open

# Open specific results
osgeo-library search "habitat" -t figure --open 1,2,3
```

**How it works:** The client downloads the image from the server to a temp file, then opens it with `xdg-open` (Linux), `open` (macOS), or `start` (Windows).

**Requires a graphical display:** The `--open` flag will not work if you're connected to a remote server via plain SSH. You'll see an error like:

```
Failed to open image: --open requires a graphical display.
```

**Options for remote access:**

1. **Use `--show` instead** - Renders images in the terminal using chafa. Works over any SSH connection.

2. **Use X11 forwarding** - Connect with `ssh -X user@server`. This forwards the display but can be slow.

3. **Run the CLI locally with SSH tunneling** (recommended for `--open`):

```bash
# On your local machine:
ssh -L 8095:localhost:8095 user@server

# Then in another terminal (locally):
osgeo-library --server http://localhost:8095 search "habitat" -t table --open 1,2,3,4
```

```
Local machine                      Remote server
┌────────────────┐                ┌────────────────┐
│ osgeo-library  │───HTTP:8095───►│ API server     │
│ (client)       │◄───image data──│                │
│                │                │                │
│ Image viewer   │                │                │
│ (opens here)   │                │                │
└────────────────┘                └────────────────┘
```

## Terminal Image Rendering

When using `--show` or the `show` command in chat mode, images are rendered in your terminal using chafa.

**Proportional sizing:** Images are scaled to fit your terminal while preserving aspect ratio. The client detects terminal dimensions and calculates appropriate sizing:

- Maximum width: 80% of terminal columns
- Height based on aspect ratio with element-type minimums:
  - Tables: 15 rows minimum (need readable text)
  - Equations: 6 rows minimum (typically short)
  - Figures: 8 rows minimum

**Rendered equations:** For equations, the client prefers LaTeX-rendered images (clean white background) over raw PDF crops when available.

**Quality settings:** The client uses high-quality chafa options:
- `--symbols all` - use all available characters
- `-w 9` - high detail work factor
- `-c full` - full color mode

## Troubleshooting

### "Connection refused" error

The API server is not running or not accessible. Check:

1. Server is running: `systemctl status osgeo-library` (if using systemd)
2. Correct port: default is 8095
3. SSH tunnel is active (if remote)

### Images not displaying

1. Verify chafa is installed: `which chafa`
2. Check terminal supports Unicode and colors
3. Try a simpler terminal emulator if issues persist

### Search returns no results

1. Check the database has been populated: `osgeo-library stats`
2. Try broader search terms
3. Remove type filter to search all element types
