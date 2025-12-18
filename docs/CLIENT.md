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

### Interactive Chat (Default)

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
| `help` | Show available commands |
| `sources` | Show sources from the last answer |
| `show N` | Display image for source N (e.g., `show 1` or `show 1,2,3`) |
| `quit` | Exit the chat |

**Example Session:**

```
OSGeo Library Chat
========================================
Server: connected | Type 'help' for commands

You: What projections preserve area?
Searching...
Thinking...