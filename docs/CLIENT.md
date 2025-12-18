# OSGeo Library CLI Client

A lightweight command-line client for searching and chatting with the OSGeo Library.

## Installation

### Download Binary (Recommended)

Download the latest release for your platform:

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

Or download from: https://github.com/ominiverdi/osgeo-library/releases

### Build from Source

Requires [Rust](https://rustup.rs/):

```bash
cd clients/rust
cargo build --release
sudo cp target/release/osgeo-library /usr/local/bin/
```

## Usage

### Interactive Chat (Default)

```bash
osgeo-library
```

This starts an interactive session where you can ask questions:

```
OSGeo Library Chat
========================================
Server: connected | Type 'help' for commands

You: What is the Mercator projection used for?
Searching...
Thinking...