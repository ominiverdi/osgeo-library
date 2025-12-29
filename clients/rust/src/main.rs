//! OSGeo Library CLI Client
//!
//! A lightweight client for searching and querying the OSGeo Library API.
//! Connects to the local FastAPI server for semantic search and LLM-powered chat.

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use colored::*;
use reqwest::blocking::Client;
use rustyline::error::ReadlineError;
use rustyline::DefaultEditor;
use serde::{Deserialize, Serialize};
use std::io::IsTerminal;
use std::process::Command;
use std::time::Duration;

// Default server URL (localhost only)
const DEFAULT_SERVER_URL: &str = "http://127.0.0.1:8095";

// -----------------------------------------------------------------------------
// API Types
// -----------------------------------------------------------------------------

#[derive(Debug, Serialize)]
struct SearchRequest {
    query: String,
    limit: i32,
    #[serde(skip_serializing_if = "Option::is_none")]
    document_slug: Option<String>,
    include_chunks: bool,
    include_elements: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    element_type: Option<String>,
}

#[derive(Debug, Serialize)]
struct ChatRequest {
    question: String,
    limit: i32,
    #[serde(skip_serializing_if = "Option::is_none")]
    document_slug: Option<String>,
}

#[derive(Debug, Deserialize)]
struct SearchResult {
    id: i64,
    score_pct: f64,
    content: String,
    source_type: String,
    document_slug: String,
    document_title: String,
    page_number: i32,
    element_type: Option<String>,
    element_label: Option<String>,
    crop_path: Option<String>,
    rendered_path: Option<String>,  // For equations: LaTeX-rendered image
    image_width: Option<i32>,       // Image dimensions for proportional display
    image_height: Option<i32>,
    chunk_index: Option<i32>,
}

impl SearchResult {
    /// Get the best image path for display.
    /// For equations, prefer rendered_path (clean LaTeX) over crop_path (raw crop).
    fn best_image_path(&self) -> Option<&str> {
        // For equations, prefer rendered version if available
        if self.element_type.as_deref() == Some("equation") {
            if let Some(ref rendered) = self.rendered_path {
                return Some(rendered.as_str());
            }
        }
        // Fall back to crop_path for all other types or if rendered not available
        self.crop_path.as_deref()
    }
    
    /// Calculate chafa size string based on actual image dimensions and terminal size.
    /// Scales to fit within terminal while preserving aspect ratio.
    fn chafa_size(&self) -> String {
        // Get actual terminal size, with sensible defaults
        let (term_width, term_height) = terminal_size::terminal_size()
            .map(|(w, h)| (w.0 as i32, h.0 as i32))
            .unwrap_or((120, 40));
        
        // Leave some margin for borders and text
        let max_width = (term_width - 4).max(40);
        let max_height = (term_height - 8).max(20);  // Leave room for header/footer
        
        match (self.image_width, self.image_height) {
            (Some(w), Some(h)) if w > 0 && h > 0 => {
                // Terminal chars are roughly 2:1 aspect ratio (taller than wide)
                // So we need to adjust: effective_height = height / 2
                let aspect = w as f64 / h as f64;
                
                // Scale to fit max width first
                let mut cols = max_width;
                let mut rows = (cols as f64 / aspect / 2.0).ceil() as i32;
                
                // If too tall, scale down by height
                if rows > max_height {
                    rows = max_height;
                    cols = (rows as f64 * aspect * 2.0).ceil() as i32;
                }
                
                // Minimum sizes - tables need more height for readability
                cols = cols.max(20);
                let min_rows = match self.element_type.as_deref() {
                    Some("table") => 15,    // Tables need more vertical space
                    Some("equation") => 6,  // Equations are typically short
                    _ => 8,                 // Default minimum
                };
                rows = rows.max(min_rows);
                
                format!("{}x{}", cols, rows)
            }
            _ => {
                // Fallback based on element type
                let fallback_width = max_width.min(100);
                match self.element_type.as_deref() {
                    Some("equation") => format!("{}x12", fallback_width),
                    Some("table") => format!("{}x{}", fallback_width, max_height.min(40)),
                    _ => format!("{}x{}", fallback_width.min(80), max_height.min(35)),
                }
            }
        }
    }
}

#[derive(Debug, Deserialize)]
struct SearchResponse {
    query: String,
    results: Vec<SearchResult>,
    total: i32,
}

#[derive(Debug, Deserialize)]
struct ChatResponse {
    answer: String,
    sources: Vec<SearchResult>,
    query_used: String,
}

#[derive(Debug, Deserialize)]
struct HealthResponse {
    status: String,
    embedding_server: bool,
    llm_server: bool,
    database: bool,
    version: String,
}

#[derive(Debug, Deserialize)]
struct DocumentListItem {
    slug: String,
    title: String,
    source_file: Option<String>,
    total_pages: i32,
    summary: Option<String>,
    keywords: Option<Vec<String>>,
    license: Option<String>,
}

#[derive(Debug, Deserialize)]
struct DocumentListResponse {
    documents: Vec<DocumentListItem>,
    page: i32,
    page_size: i32,
    total_pages: i32,
    total_documents: i32,
}

#[derive(Debug, Deserialize)]
struct DocumentDetailResponse {
    slug: String,
    title: String,
    source_file: Option<String>,
    total_pages: i32,
    summary: Option<String>,
    keywords: Option<Vec<String>>,
    license: Option<String>,
    extraction_date: Option<String>,
    element_counts: std::collections::HashMap<String, i32>,
}

#[derive(Debug, Deserialize)]
struct PageResponse {
    document_slug: String,
    document_title: String,
    page_number: i32,
    total_pages: i32,
    image_base64: String,
    image_width: i32,
    image_height: i32,
    mime_type: String,
    has_annotated: bool,
    summary: Option<String>,
    keywords: Option<Vec<String>>,
}

// -----------------------------------------------------------------------------
// CLI Definition
// -----------------------------------------------------------------------------

#[derive(Parser)]
#[command(name = "osgeo-library")]
#[command(about = "Search and chat with the OSGeo Library")]
#[command(version)]
#[command(after_help = "EXAMPLES:
    osgeo-library                              Start interactive chat
    osgeo-library docs                         List all documents
    osgeo-library doc usgs_snyder              Show document details
    osgeo-library search \"mercator projection\" Search all content
    osgeo-library search \"area\" -t equation    Search only equations
    osgeo-library search \"habitat\" -t table --show   Search tables, display image
    osgeo-library ask \"What is SAM?\"           One-shot question

ELEMENT TYPES (-t):
    figure, table, equation, chart, diagram")]
struct Cli {
    /// Server URL (default: http://127.0.0.1:8095)
    #[arg(short, long, env = "OSGEO_SERVER_URL")]
    server: Option<String>,

    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Search documents (text chunks and elements)
    Search {
        /// Search query
        query: String,

        /// Maximum number of results
        #[arg(short = 'n', long, default_value = "10")]
        limit: i32,

        /// Filter by document slug
        #[arg(short, long)]
        document: Option<String>,

        /// Show only elements (figures, tables, equations)
        #[arg(long)]
        elements_only: bool,

        /// Show only text chunks
        #[arg(long)]
        chunks_only: bool,

        /// Filter by element type: figure, table, equation, chart, diagram
        #[arg(short, long, value_name = "TYPE")]
        r#type: Option<String>,

        /// Display images in terminal: --show (first), --show 1, --show 1,3,5
        #[arg(long, value_name = "N", num_args = 0..=1, default_missing_value = "1")]
        show: Option<String>,

        /// Open images in GUI viewer: --open (first), --open 1, --open 1,3,5
        /// Requires X11 forwarding for remote access (ssh -X)
        #[arg(long, value_name = "N", num_args = 0..=1, default_missing_value = "1")]
        open: Option<String>,
    },

    /// Ask a question and get an LLM-powered answer with citations
    Ask {
        /// Your question
        question: String,

        /// Maximum context results
        #[arg(short = 'n', long, default_value = "8")]
        limit: i32,

        /// Filter by document slug
        #[arg(short, long)]
        document: Option<String>,
    },

    /// Interactive chat mode (default when no command given)
    Chat,

    /// Check server health and connectivity
    Health,

    /// List all documents in the library
    Docs {
        /// Page number (1-indexed)
        #[arg(short, long, default_value = "1")]
        page: i32,

        /// Results per page
        #[arg(short = 'n', long, default_value = "20")]
        limit: i32,

        /// Sort by: title, date_added, page_count
        #[arg(short, long, default_value = "title")]
        sort: String,
    },

    /// Get detailed info about a specific document
    Doc {
        /// Document slug (e.g., 'usgs_snyder', 'torchgeo')
        slug: String,
    },
}

// -----------------------------------------------------------------------------
// Client Implementation
// -----------------------------------------------------------------------------

struct OsgeoClient {
    client: Client,
    base_url: String,
}

impl OsgeoClient {
    fn new(base_url: &str) -> Result<Self> {
        let client = Client::builder()
            .timeout(Duration::from_secs(120))
            .build()
            .context("Failed to create HTTP client")?;

        Ok(Self {
            client,
            base_url: base_url.trim_end_matches('/').to_string(),
        })
    }

    fn health(&self) -> Result<HealthResponse> {
        let url = format!("{}/health", self.base_url);
        let response = self
            .client
            .get(&url)
            .send()
            .context("Failed to connect to server")?;

        if !response.status().is_success() {
            anyhow::bail!("Server returned error: {}", response.status());
        }

        response.json().context("Failed to parse health response")
    }

    fn search(&self, req: SearchRequest) -> Result<SearchResponse> {
        let url = format!("{}/search", self.base_url);
        let response = self
            .client
            .post(&url)
            .json(&req)
            .send()
            .context("Failed to send search request")?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            anyhow::bail!("Search failed ({}): {}", status, body);
        }

        response.json().context("Failed to parse search response")
    }

    fn chat(&self, req: ChatRequest) -> Result<ChatResponse> {
        let url = format!("{}/chat", self.base_url);
        let response = self
            .client
            .post(&url)
            .json(&req)
            .send()
            .context("Failed to send chat request")?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            anyhow::bail!("Chat failed ({}): {}", status, body);
        }

        response.json().context("Failed to parse chat response")
    }

    fn list_documents(&self, page: i32, page_size: i32, sort_by: &str) -> Result<DocumentListResponse> {
        let url = format!(
            "{}/documents?page={}&page_size={}&sort_by={}",
            self.base_url, page, page_size, sort_by
        );
        let response = self
            .client
            .get(&url)
            .send()
            .context("Failed to fetch documents")?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            anyhow::bail!("Failed to list documents ({}): {}", status, body);
        }

        response.json().context("Failed to parse documents response")
    }

    fn get_document(&self, slug: &str) -> Result<DocumentDetailResponse> {
        let url = format!("{}/documents/{}", self.base_url, slug);
        let response = self
            .client
            .get(&url)
            .send()
            .context("Failed to fetch document")?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            anyhow::bail!("Failed to get document ({}): {}", status, body);
        }

        response.json().context("Failed to parse document response")
    }

    fn get_page(&self, slug: &str, page_number: i32) -> Result<PageResponse> {
        let url = format!("{}/page/{}/{}", self.base_url, slug, page_number);
        let response = self
            .client
            .get(&url)
            .send()
            .context("Failed to fetch page")?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            anyhow::bail!("Failed to get page ({}): {}", status, body);
        }

        response.json().context("Failed to parse page response")
    }

    fn display_base64_image(&self, base64_data: &str, size: &str) -> Result<()> {
        use base64::{Engine as _, engine::general_purpose};
        
        let bytes = general_purpose::STANDARD
            .decode(base64_data)
            .context("Failed to decode base64 image")?;

        // Write to temp file
        #[cfg(unix)]
        let temp_path = {
            let uid = unsafe { libc::getuid() };
            std::env::temp_dir().join(format!("osgeo-library-page-{}.png", uid))
        };
        #[cfg(windows)]
        let temp_path = {
            let pid = std::process::id();
            std::env::temp_dir().join(format!("osgeo-library-page-{}.png", pid))
        };
        std::fs::write(&temp_path, &bytes).context("Failed to write temp file")?;

        // Display with chafa if available
        if Command::new("which")
            .arg("chafa")
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
        {
            let status = Command::new("chafa")
                .args([
                    "--size", size,
                    "--symbols", "all",
                    "-w", "9",
                    "-c", "full",
                    temp_path.to_str().unwrap()
                ])
                .status();

            if let Ok(s) = status {
                if s.success() {
                    println!();
                    return Ok(());
                }
            }
        }

        println!("(Install chafa for terminal preview: sudo apt install chafa)");
        Ok(())
    }

    fn open_base64_image(&self, base64_data: &str) -> Result<()> {
        use base64::{Engine as _, engine::general_purpose};
        
        // Check for graphical display availability
        #[cfg(target_os = "linux")]
        {
            if std::env::var("DISPLAY").is_err() && std::env::var("WAYLAND_DISPLAY").is_err() {
                anyhow::bail!(
                    "open requires a graphical display.\n\
                     Use 'page <slug> <N>' for terminal preview instead."
                );
            }
        }
        
        let bytes = general_purpose::STANDARD
            .decode(base64_data)
            .context("Failed to decode base64 image")?;

        // Write to temp file with unique name
        let temp_path = std::env::temp_dir().join(format!(
            "osgeo-library-page-{}.png",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_millis()
        ));
        std::fs::write(&temp_path, &bytes).context("Failed to write temp file")?;

        // Open with platform-appropriate command
        #[cfg(target_os = "linux")]
        {
            Command::new("xdg-open")
                .arg(&temp_path)
                .spawn()
                .context("Failed to run 'xdg-open'")?;
        }

        #[cfg(target_os = "macos")]
        {
            Command::new("open")
                .arg(&temp_path)
                .spawn()
                .context("Failed to run 'open'")?;
        }

        #[cfg(target_os = "windows")]
        {
            Command::new("cmd")
                .args(["/C", "start", "", temp_path.to_str().unwrap()])
                .spawn()
                .context("Failed to open image")?;
        }

        Ok(())
    }

    fn fetch_and_display_image(&self, url: &str, size: &str) -> Result<()> {
        // Fetch image bytes from server
        let response = self
            .client
            .get(url)
            .send()
            .context("Failed to fetch image")?;

        if !response.status().is_success() {
            anyhow::bail!("Image not found ({})", response.status());
        }

        let bytes = response.bytes().context("Failed to read image bytes")?;

        // Write to temp file (include user/process ID to avoid permission conflicts)
        #[cfg(unix)]
        let temp_path = {
            let uid = unsafe { libc::getuid() };
            std::env::temp_dir().join(format!("osgeo-library-image-{}.png", uid))
        };
        #[cfg(windows)]
        let temp_path = {
            let pid = std::process::id();
            std::env::temp_dir().join(format!("osgeo-library-image-{}.png", pid))
        };
        std::fs::write(&temp_path, &bytes).context("Failed to write temp file")?;

        // Display with chafa if available
        if Command::new("which")
            .arg("chafa")
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
        {
            let status = Command::new("chafa")
                .args([
                    "--size", size,
                    "--symbols", "all",     // Use all symbols for better detail
                    "-w", "9",              // Work hardest for best quality
                    "-c", "full",           // Full 24-bit color
                    temp_path.to_str().unwrap()
                ])
                .status();

            if let Ok(s) = status {
                if s.success() {
                    println!();
                    return Ok(());
                }
            }
        }

        // Fallback: just show path
        println!("(Install chafa for terminal preview: sudo apt install chafa)");
        Ok(())
    }

    /// Fetch image from server and open in GUI viewer.
    /// Uses xdg-open (Linux), open (macOS), or start (Windows).
    /// Requires a graphical display; use --show for terminal preview over SSH.
    fn fetch_and_open_image(&self, url: &str) -> Result<()> {
        // Check for graphical display availability
        #[cfg(target_os = "linux")]
        {
            if std::env::var("DISPLAY").is_err() && std::env::var("WAYLAND_DISPLAY").is_err() {
                anyhow::bail!(
                    "--open requires a graphical display.\n\
                     You appear to be running on a remote server without X11/Wayland forwarding.\n\n\
                     Options:\n\
                       1. Use --show for terminal preview instead\n\
                       2. Connect with X11 forwarding: ssh -X user@server\n\
                       3. Run the CLI on your local machine with SSH tunneling:\n\
                          ssh -L 8095:localhost:8095 user@server\n\
                          osgeo-library --server http://localhost:8095 search \"...\" --open"
                );
            }
        }

        #[cfg(target_os = "macos")]
        {
            // Check if running in SSH session without display
            if std::env::var("SSH_CONNECTION").is_ok() && std::env::var("DISPLAY").is_err() {
                anyhow::bail!(
                    "--open requires a graphical display.\n\
                     You appear to be connected via SSH without display forwarding.\n\n\
                     Options:\n\
                       1. Use --show for terminal preview instead\n\
                       2. Connect with X11 forwarding: ssh -X user@server\n\
                       3. Run the CLI on your local machine with SSH tunneling:\n\
                          ssh -L 8095:localhost:8095 user@server\n\
                          osgeo-library --server http://localhost:8095 search \"...\" --open"
                );
            }
        }

        // Fetch image bytes from server
        let response = self
            .client
            .get(url)
            .send()
            .context("Failed to fetch image")?;

        if !response.status().is_success() {
            anyhow::bail!("Image not found ({})", response.status());
        }

        let bytes = response.bytes().context("Failed to read image bytes")?;

        // Write to temp file with unique name
        let temp_path = std::env::temp_dir().join(format!(
            "osgeo-library-{}.png",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_millis()
        ));
        std::fs::write(&temp_path, &bytes).context("Failed to write temp file")?;

        // Open with platform-appropriate command
        #[cfg(target_os = "macos")]
        {
            let status = Command::new("open")
                .arg(&temp_path)
                .status()
                .context("Failed to run 'open'")?;

            if !status.success() {
                anyhow::bail!("open failed with status: {}", status);
            }
        }

        #[cfg(target_os = "linux")]
        {
            let status = Command::new("xdg-open")
                .arg(&temp_path)
                .status()
                .context("Failed to run 'xdg-open'. Is xdg-utils installed?")?;

            if !status.success() {
                anyhow::bail!("xdg-open failed with status: {}", status);
            }
        }

        #[cfg(target_os = "windows")]
        {
            let status = Command::new("cmd")
                .args(["/c", "start", "", temp_path.to_str().unwrap()])
                .status()
                .context("Failed to run 'start'")?;

            if !status.success() {
                anyhow::bail!("start failed with status: {}", status);
            }
        }

        println!("Opened: {}", temp_path.display());
        Ok(())
    }
}

// -----------------------------------------------------------------------------
// Display Helpers
// -----------------------------------------------------------------------------

fn get_source_tag(result: &SearchResult) -> &'static str {
    if result.source_type == "element" {
        match result.element_type.as_deref() {
            Some("figure") => "f",
            Some("table") => "tb",
            Some("equation") => "eq",
            Some("chart") => "ch",
            Some("diagram") => "d",
            _ => "e",
        }
    } else {
        "t"
    }
}

fn format_result(i: usize, result: &SearchResult, verbose: bool) -> String {
    let mut lines = Vec::new();

    if result.source_type == "element" {
        let elem_type = result
            .element_type
            .as_ref()
            .map(|s| s.to_uppercase())
            .unwrap_or_else(|| "UNKNOWN".to_string());
        let label = result
            .element_label
            .as_deref()
            .unwrap_or("(unlabeled)");

        lines.push(format!(
            "[{}] {} {}",
            i.to_string().yellow(),
            elem_type.cyan(),
            label
        ));
        lines.push(format!(
            "    {} p.{} | {:.0}%",
            result.document_title.dimmed(),
            result.page_number,
            result.score_pct
        ));
    } else {
        let chunk_idx = result.chunk_index.unwrap_or(0);
        lines.push(format!(
            "[{}] TEXT chunk {}",
            i.to_string().yellow(),
            chunk_idx
        ));
        lines.push(format!(
            "    {} p.{} | {:.0}%",
            result.document_title.dimmed(),
            result.page_number,
            result.score_pct
        ));
    }

    if verbose && !result.content.is_empty() {
        let preview: String = result.content.chars().take(200).collect();
        lines.push(format!("    {}", preview.dimmed()));
    }

    lines.join("\n")
}

fn format_sources(sources: &[SearchResult]) -> String {
    if sources.is_empty() {
        return "No sources available.".to_string();
    }

    sources
        .iter()
        .enumerate()
        .map(|(i, r)| {
            let tag = get_source_tag(r);
            if r.source_type == "element" {
                let elem_type = r
                    .element_type
                    .as_ref()
                    .map(|s| s.to_uppercase())
                    .unwrap_or_else(|| "?".to_string());
                let label = r.element_label.as_deref().unwrap_or("");
                format!(
                    "[{}:{}] {} {} | {} p.{} | {:.0}%",
                    tag,
                    i + 1,
                    elem_type,
                    label,
                    r.document_title,
                    r.page_number,
                    r.score_pct
                )
            } else {
                format!(
                    "[{}:{}] TEXT chunk | {} p.{} | {:.0}%",
                    tag,
                    i + 1,
                    r.document_title,
                    r.page_number,
                    r.score_pct
                )
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}


// -----------------------------------------------------------------------------
// Commands
// -----------------------------------------------------------------------------

fn cmd_health(client: &OsgeoClient) -> Result<()> {
    let health = client.health()?;

    println!("{}", "OSGeo Library Server Status".bold());
    println!("{}", "=".repeat(40));

    let status_color = if health.status == "healthy" {
        health.status.green()
    } else {
        health.status.yellow()
    };
    println!("Status:     {}", status_color);
    println!("Version:    {}", health.version);
    println!();

    let check = |ok: bool| if ok { "OK".green() } else { "FAILED".red() };
    println!("Embedding:  {}", check(health.embedding_server));
    println!("LLM:        {}", check(health.llm_server));
    println!("Database:   {}", check(health.database));

    Ok(())
}

fn cmd_docs(client: &OsgeoClient, page: i32, limit: i32, sort: String) -> Result<()> {
    let response = client.list_documents(page, limit, &sort)?;

    println!("{}", "OSGeo Document Library".bold());
    println!("{}", "=".repeat(50));
    println!(
        "Page {} of {} ({} documents total)\n",
        response.page,
        response.total_pages,
        response.total_documents
    );

    for doc in &response.documents {
        println!("{}", doc.title.bold());
        println!("  Slug: {}  |  Pages: {}", doc.slug.cyan(), doc.total_pages);
        
        if let Some(ref keywords) = doc.keywords {
            if !keywords.is_empty() {
                let kw_str: String = keywords.iter().take(5).cloned().collect::<Vec<_>>().join(", ");
                println!("  Keywords: {}", kw_str.dimmed());
            }
        }
        
        if let Some(ref summary) = doc.summary {
            // Truncate long summaries
            let display_summary = if summary.len() > 150 {
                format!("{}...", &summary[..150])
            } else {
                summary.clone()
            };
            println!("  {}", display_summary.dimmed());
        }
        println!();
    }

    if response.total_pages > 1 {
        println!(
            "Use {} to see more pages",
            format!("--page {}", page + 1).cyan()
        );
    }

    Ok(())
}

fn cmd_doc(client: &OsgeoClient, slug: String) -> Result<()> {
    let doc = client.get_document(&slug)?;

    println!("{}", doc.title.bold());
    println!("{}", "=".repeat(50));
    println!("Slug:       {}", doc.slug.cyan());
    println!("Pages:      {}", doc.total_pages);
    
    if let Some(ref source) = doc.source_file {
        println!("Source:     {}", source);
    }
    
    if let Some(ref date) = doc.extraction_date {
        println!("Extracted:  {}", date);
    }
    
    if let Some(ref license) = doc.license {
        println!("License:    {}", license);
    }

    // Element counts
    let total_elements: i32 = doc.element_counts.values().sum();
    if total_elements > 0 {
        println!("\n{}", "Elements:".bold());
        for (elem_type, count) in &doc.element_counts {
            if *count > 0 {
                println!("  {:12} {}", format!("{}:", elem_type), count);
            }
        }
    }

    // Keywords
    if let Some(ref keywords) = doc.keywords {
        if !keywords.is_empty() {
            println!("\n{}", "Keywords:".bold());
            println!("  {}", keywords.join(", "));
        }
    }

    // Summary
    if let Some(ref summary) = doc.summary {
        println!("\n{}", "Summary:".bold());
        println!("{}", summary);
    }

    println!("\n{}", "Usage:".dimmed());
    println!(
        "  Search:  osgeo-library search \"query\" -d {}",
        doc.slug
    );
    println!(
        "  Chat:    osgeo-library ask \"question\" -d {}",
        doc.slug
    );

    Ok(())
}

fn cmd_search(
    client: &OsgeoClient,
    query: String,
    limit: i32,
    document: Option<String>,
    elements_only: bool,
    chunks_only: bool,
    element_type: Option<String>,
    show: Option<String>,
    open: Option<String>,
) -> Result<()> {
    // If element_type is specified, force elements_only
    let elements_only = elements_only || element_type.is_some();
    
    let req = SearchRequest {
        query: query.clone(),
        limit,
        document_slug: document,
        include_chunks: !elements_only,
        include_elements: !chunks_only,
        element_type,
    };

    println!("{}: {}", "Searching".dimmed(), query);

    let response = client.search(req)?;

    if response.results.is_empty() {
        println!("\nNo results found.");
        return Ok(());
    }

    println!(
        "\n{} results:\n",
        response.total.to_string().green().bold()
    );

    for (i, result) in response.results.iter().enumerate() {
        println!("{}", format_result(i + 1, result, true));
        println!();
    }

    // Handle --show flag
    if let Some(show_arg) = show {
        // Parse indices: "1" or "1,3,5"
        let indices: Vec<usize> = show_arg
            .split(',')
            .filter_map(|s| s.trim().parse::<usize>().ok())
            .map(|n| n.saturating_sub(1)) // Convert to 0-indexed
            .collect();

        if indices.is_empty() {
            return Ok(());
        }

        println!("{}", "=".repeat(40));

        for idx in indices {
            if idx >= response.results.len() {
                println!("Invalid index [{}]. Use 1-{}", idx + 1, response.results.len());
                continue;
            }

            let result = &response.results[idx];

            if result.source_type != "element" {
                println!("[{}] is a text chunk, no image available.", idx + 1);
                continue;
            }

            if let Some(image_path) = result.best_image_path() {
                let elem_type = result
                    .element_type
                    .as_ref()
                    .map(|s| s.to_uppercase())
                    .unwrap_or_default();
                let label = result.element_label.as_deref().unwrap_or("");

                println!("\n{}: {}", elem_type.yellow(), label);
                println!(
                    "From: {}, page {}\n",
                    result.document_title, result.page_number
                );

                let image_url = format!(
                    "{}/image/{}/{}",
                    client.base_url, result.document_slug, image_path
                );

                let size = result.chafa_size();
                if let Err(e) = client.fetch_and_display_image(&image_url, &size) {
                    println!("{}: {}", "Failed to display image".red(), e);
                }
            }
        }
    }

    // Handle --open flag
    if let Some(open_arg) = open {
        let indices: Vec<usize> = open_arg
            .split(',')
            .filter_map(|s| s.trim().parse::<usize>().ok())
            .map(|n| n.saturating_sub(1))
            .collect();

        if indices.is_empty() {
            return Ok(());
        }

        for idx in indices {
            if idx >= response.results.len() {
                println!("Invalid index [{}]. Use 1-{}", idx + 1, response.results.len());
                continue;
            }

            let result = &response.results[idx];

            if result.source_type != "element" {
                println!("[{}] is a text chunk, no image available.", idx + 1);
                continue;
            }

            if let Some(image_path) = result.best_image_path() {
                let image_url = format!(
                    "{}/image/{}/{}",
                    client.base_url, result.document_slug, image_path
                );

                if let Err(e) = client.fetch_and_open_image(&image_url) {
                    println!("{}: {}", "Failed to open image".red(), e);
                }
            }
        }
    }

    Ok(())
}

fn cmd_ask(
    client: &OsgeoClient,
    question: String,
    limit: i32,
    document: Option<String>,
) -> Result<()> {
    let req = ChatRequest {
        question: question.clone(),
        limit,
        document_slug: document,
    };

    println!("{}: {}", "Question".dimmed(), question);
    println!("{}", "Thinking...".dimmed());

    let response = client.chat(req)?;

    println!("\n{}\n", response.answer);

    if !response.sources.is_empty() {
        let elem_count = response
            .sources
            .iter()
            .filter(|s| s.source_type == "element")
            .count();
        println!(
            "({} sources, {} elements - type 'sources' in chat mode to see details)\n",
            response.sources.len(),
            elem_count
        );
    }

    Ok(())
}

fn cmd_chat(client: &OsgeoClient) -> Result<()> {
    println!("{}", "OSGeo Library Chat".bold());
    println!("{}", "=".repeat(40));

    // Check server health first
    match client.health() {
        Ok(h) if h.status == "healthy" => {
            println!("Server: {} | Type 'help' for commands\n", "connected".green());
        }
        Ok(h) => {
            println!(
                "Server: {} (some services unavailable)\n",
                "degraded".yellow()
            );
            if !h.embedding_server {
                println!("  {} Embedding server unavailable", "!".red());
            }
            if !h.llm_server {
                println!("  {} LLM server unavailable", "!".red());
            }
            if !h.database {
                println!("  {} Database unavailable", "!".red());
            }
            println!();
        }
        Err(e) => {
            return Err(e);
        }
    }

    let mut rl = DefaultEditor::new()?;
    let mut last_sources: Vec<SearchResult> = Vec::new();
    let mut docs_page: i32 = 0;  // 0 = not viewing docs, >0 = current page
    let mut docs_total_pages: i32 = 0;
    let mut docs_slugs: Vec<String> = Vec::new();  // slugs from current docs page
    let mut current_doc: Option<String> = None;  // current document being viewed
    let mut last_page_view: Option<(String, i32, i32)> = None;  // (slug, page_num, total_pages)
    
    // Detect if stdin is piped (not interactive)
    let is_piped = !std::io::stdin().is_terminal();

    loop {
        let readline = rl.readline(&format!("{} ", "You:".green().bold()));

        match readline {
            Ok(line) => {
                let input = line.trim();
                if input.is_empty() {
                    continue;
                }
                
                // Echo command when piped for test visibility
                if is_piped {
                    println!("{} {}", "You:".green().bold(), input);
                }

                rl.add_history_entry(input)?;

                // Handle commands
                let lower = input.to_lowercase();

                if lower == "quit" || lower == "exit" || lower == "q" {
                    println!("Goodbye!");
                    break;
                }

                if lower == "help" || lower == "?" {
                    println!("\n{}", "Browse:".bold());
                    println!("  docs              List documents in library");
                    println!("  doc <N|slug>      Select document (e.g., 'doc 1' or 'doc usgs_snyder')");
                    println!("  page [slug] <N>   View page (e.g., 'page 55' or 'page usgs_snyder 55')");
                    println!("  next/n, prev/p    Navigate to next/previous page");
                    println!();
                    println!("{}", "Elements:".bold());
                    println!("  figures           List figures on current page (or 'figures all')");
                    println!("  tables            List tables on current page (or 'tables all')");
                    println!("  equations         List equations on current page (or 'equations all')");
                    println!();
                    println!("{}", "View:".bold());
                    println!("  show <N>          Show element in terminal (e.g., 'show 1' or 'show 1,2,3')");
                    println!("  open <N>          Open element in GUI viewer");
                    println!("  open page <N>     Open page in GUI viewer");
                    println!();
                    println!("{}", "Search:".bold());
                    println!("  search <query>    Semantic search (no LLM)");
                    println!("  sources           Show sources from last answer");
                    println!("  <question>        Ask a question (uses LLM)");
                    println!();
                    println!("{}", "Other:".bold());
                    println!("  help              Show this help");
                    println!("  quit/exit/q       Exit\n");
                    continue;
                }

                if lower == "sources" {
                    if last_sources.is_empty() {
                        println!("No sources available. Ask a question first.\n");
                    } else {
                        println!("\n{}", format_sources(&last_sources));
                        println!();
                    }
                    continue;
                }

                if lower.starts_with("show ") {
                    let arg = input[5..].trim();
                    
                    // Check if it's "show page <slug> <N>" or "show page <N>"
                    if arg.to_lowercase().starts_with("page ") {
                        let page_arg = arg[5..].trim();
                        let parts: Vec<&str> = page_arg.split_whitespace().collect();
                        
                        let (doc_slug, page_num) = match parts.len() {
                            1 => {
                                match parts[0].parse::<i32>() {
                                    Ok(n) if n > 0 => {
                                        match &current_doc {
                                            Some(slug) => (slug.clone(), n),
                                            None => {
                                                println!("Use 'doc <slug>' first, or specify: show page <slug> <N>\n");
                                                continue;
                                            }
                                        }
                                    }
                                    _ => {
                                        println!("Usage: show page <N> or show page <slug> <N>\n");
                                        continue;
                                    }
                                }
                            }
                            2 => {
                                let slug = parts[0].to_string();
                                match parts[1].parse::<i32>() {
                                    Ok(n) if n > 0 => (slug, n),
                                    _ => {
                                        println!("Usage: show page <N> or show page <slug> <N>\n");
                                        continue;
                                    }
                                }
                            }
                            _ => {
                                println!("Usage: show page <N> or show page <slug> <N>\n");
                                continue;
                            }
                        };
                        
                        print!("Loading page {}...", page_num);
                        std::io::Write::flush(&mut std::io::stdout()).ok();
                        
                        match client.get_page(&doc_slug, page_num) {
                            Ok(page) => {
                                println!(" done\n");
                                println!("{} p.{}/{}", 
                                    page.document_title.bold(),
                                    page.page_number,
                                    page.total_pages
                                );
                                
                                if let Some(summary) = &page.summary {
                                    println!("{}: {}", "Summary".dimmed(), summary);
                                }
                                
                                if let Some(keywords) = &page.keywords {
                                    if !keywords.is_empty() {
                                        println!("{}: {}", "Keywords".dimmed(), keywords.join(", "));
                                    }
                                }
                                
                                println!();
                                
                                if let Err(e) = client.display_base64_image(&page.image_base64, "80x40") {
                                    println!("{}: {}", "Error displaying image".red(), e);
                                }
                                
                                // Save state for next/prev navigation and set current doc
                                last_page_view = Some((doc_slug.clone(), page.page_number, page.total_pages));
                                current_doc = Some(doc_slug.clone());
                            }
                            Err(e) => {
                                println!("\n{}: {}\n", "Error".red(), e);
                            }
                        }
                    } else {
                        // Original behavior: show source by index
                        handle_show_command(client, &arg, &last_sources);
                    }
                    continue;
                }

                if lower.starts_with("open ") {
                    let arg = input[5..].trim();
                    
                    // Check if it's "open page <slug> <N>" or "open page <N>"
                    if arg.to_lowercase().starts_with("page ") {
                        let page_arg = arg[5..].trim();
                        let parts: Vec<&str> = page_arg.split_whitespace().collect();
                        
                        let (doc_slug, page_num) = match parts.len() {
                            1 => {
                                match parts[0].parse::<i32>() {
                                    Ok(n) if n > 0 => {
                                        match &current_doc {
                                            Some(slug) => (slug.clone(), n),
                                            None => {
                                                println!("Use 'doc <slug>' first, or specify: open page <slug> <N>\n");
                                                continue;
                                            }
                                        }
                                    }
                                    _ => {
                                        println!("Usage: open page <N> or open page <slug> <N>\n");
                                        continue;
                                    }
                                }
                            }
                            2 => {
                                let slug = parts[0].to_string();
                                match parts[1].parse::<i32>() {
                                    Ok(n) if n > 0 => (slug, n),
                                    _ => {
                                        println!("Usage: open page <N> or open page <slug> <N>\n");
                                        continue;
                                    }
                                }
                            }
                            _ => {
                                println!("Usage: open page <N> or open page <slug> <N>\n");
                                continue;
                            }
                        };
                        
                        print!("Loading page {}...", page_num);
                        std::io::Write::flush(&mut std::io::stdout()).ok();
                        
                        match client.get_page(&doc_slug, page_num) {
                            Ok(page) => {
                                println!(" opening");
                                if let Err(e) = client.open_base64_image(&page.image_base64) {
                                    println!("{}: {}\n", "Error".red(), e);
                                }
                                
                                // Update state for next/prev and figures/tables/equations
                                last_page_view = Some((doc_slug.clone(), page.page_number, page.total_pages));
                                current_doc = Some(doc_slug.clone());
                            }
                            Err(e) => {
                                println!("\n{}: {}\n", "Error".red(), e);
                            }
                        }
                    } else {
                        // Original behavior: open source by index
                        handle_open_command(client, &arg, &last_sources);
                    }
                    continue;
                }

                // page <N> or page <slug> <N> - view page N of document
                if lower.starts_with("page ") {
                    let arg = input[5..].trim();
                    let parts: Vec<&str> = arg.split_whitespace().collect();
                    
                    let (doc_slug, page_num) = match parts.len() {
                        1 => {
                            // page <N> - use current document
                            match arg.parse::<i32>() {
                                Ok(n) if n > 0 => {
                                    match &current_doc {
                                        Some(slug) => (slug.clone(), n),
                                        None => {
                                            println!("Use 'doc <slug>' first, or specify: page <slug> <N>\n");
                                            continue;
                                        }
                                    }
                                }
                                _ => {
                                    println!("Usage: page <N> or page <slug> <N>\n");
                                    continue;
                                }
                            }
                        }
                        2 => {
                            // page <slug> <N>
                            let slug = parts[0].to_string();
                            match parts[1].parse::<i32>() {
                                Ok(n) if n > 0 => (slug, n),
                                _ => {
                                    println!("Usage: page <N> or page <slug> <N>\n");
                                    continue;
                                }
                            }
                        }
                        _ => {
                            println!("Usage: page <N> or page <slug> <N>\n");
                            continue;
                        }
                    };
                    
                    // Fetch and display page
                    print!("Loading page {}...", page_num);
                    std::io::Write::flush(&mut std::io::stdout()).ok();
                    
                    match client.get_page(&doc_slug, page_num) {
                        Ok(page) => {
                            println!(" done\n");
                            println!("{} p.{}/{}", 
                                page.document_title.bold(),
                                page.page_number,
                                page.total_pages
                            );
                            
                            // Show summary if available
                            if let Some(summary) = &page.summary {
                                println!("{}: {}", "Summary".dimmed(), summary);
                            }
                            
                            // Show keywords if available
                            if let Some(keywords) = &page.keywords {
                                if !keywords.is_empty() {
                                    println!("{}: {}", "Keywords".dimmed(), keywords.join(", "));
                                }
                            }
                            
                            println!();
                            
                            // Display image
                            if let Err(e) = client.display_base64_image(&page.image_base64, "80x40") {
                                println!("{}: {}", "Error displaying image".red(), e);
                            }
                            
                            // Save state for next/prev navigation and set current doc
                            last_page_view = Some((doc_slug.clone(), page.page_number, page.total_pages));
                            current_doc = Some(doc_slug.clone());
                        }
                        Err(e) => {
                            println!("\n{}: {}\n", "Error".red(), e);
                        }
                    }
                    continue;
                }

                if lower == "docs" || lower == "next" || lower == "n" || lower == "prev" || lower == "p" {
                    // Check if we're navigating pages (after viewing a page)
                    if (lower == "next" || lower == "n" || lower == "prev" || lower == "p") && last_page_view.is_some() {
                        let (slug, current_page, total) = last_page_view.as_ref().unwrap();
                        
                        let new_page = if lower == "next" || lower == "n" {
                            if *current_page >= *total {
                                println!("Already on last page ({}/{}).\n", current_page, total);
                                continue;
                            }
                            current_page + 1
                        } else {
                            if *current_page <= 1 {
                                println!("Already on first page.\n");
                                continue;
                            }
                            current_page - 1
                        };
                        
                        print!("Loading page {}...", new_page);
                        std::io::Write::flush(&mut std::io::stdout()).ok();
                        
                        match client.get_page(slug, new_page) {
                            Ok(page) => {
                                println!(" done\n");
                                println!("{} p.{}/{}", 
                                    page.document_title.bold(),
                                    page.page_number,
                                    page.total_pages
                                );
                                
                                if let Some(summary) = &page.summary {
                                    println!("{}: {}", "Summary".dimmed(), summary);
                                }
                                
                                if let Some(keywords) = &page.keywords {
                                    if !keywords.is_empty() {
                                        println!("{}: {}", "Keywords".dimmed(), keywords.join(", "));
                                    }
                                }
                                
                                println!();
                                
                                if let Err(e) = client.display_base64_image(&page.image_base64, "80x40") {
                                    println!("{}: {}", "Error displaying image".red(), e);
                                }
                                
                                last_page_view = Some((slug.clone(), page.page_number, page.total_pages));
                            }
                            Err(e) => {
                                println!("\n{}: {}\n", "Error".red(), e);
                            }
                        }
                        continue;
                    }
                    
                    // Otherwise, handle document list pagination
                    // Determine which page to fetch
                    let target_page = if lower == "docs" {
                        1
                    } else if lower == "next" || lower == "n" {
                        if docs_page == 0 {
                            println!("Use 'docs' first to list documents.\n");
                            continue;
                        }
                        if docs_page >= docs_total_pages {
                            println!("Already on last page.\n");
                            continue;
                        }
                        docs_page + 1
                    } else {
                        // prev/p
                        if docs_page == 0 {
                            println!("Use 'docs' first to list documents.\n");
                            continue;
                        }
                        if docs_page <= 1 {
                            println!("Already on first page.\n");
                            continue;
                        }
                        docs_page - 1
                    };

                    match client.list_documents(target_page, 5, "title") {
                        Ok(response) => {
                            docs_page = response.page;
                            docs_total_pages = response.total_pages;
                            docs_slugs = response.documents.iter().map(|d| d.slug.clone()).collect();
                            
                            println!("\n{} (page {}/{})", "Documents in library:".bold(), docs_page, docs_total_pages);
                            println!("{}", "=".repeat(50));
                            for (i, doc) in response.documents.iter().enumerate() {
                                println!("[{}] {} - {} pages", 
                                    (i + 1).to_string().yellow(),
                                    doc.slug.cyan(),
                                    doc.total_pages);
                                println!("    {}", doc.title);
                                if let Some(ref keywords) = doc.keywords {
                                    if !keywords.is_empty() {
                                        let kw: String = keywords.iter().take(4).cloned().collect::<Vec<_>>().join(", ");
                                        println!("    {}", kw.dimmed());
                                    }
                                }
                            }
                            let nav_hint = if docs_total_pages > 1 {
                                " | 'n'=next, 'p'=prev"
                            } else {
                                ""
                            };
                            println!("\n'doc N' or 'doc <slug>' for details{}\n", nav_hint);
                        }
                        Err(e) => println!("{}: {}\n", "Error".red(), e),
                    }
                    continue;
                }

                if lower.starts_with("doc ") {
                    let arg = input[4..].trim();
                    if arg.is_empty() {
                        println!("Usage: doc <N> or doc <slug> (e.g., 'doc 1' or 'doc usgs_snyder')\n");
                        continue;
                    }
                    // Check if arg is a number (index into docs_slugs)
                    let slug = if let Ok(n) = arg.parse::<usize>() {
                        if n == 0 || n > docs_slugs.len() {
                            if docs_slugs.is_empty() {
                                println!("Use 'docs' first to list documents.\n");
                            } else {
                                println!("Invalid index. Use 1-{}.\n", docs_slugs.len());
                            }
                            continue;
                        }
                        docs_slugs[n - 1].as_str()
                    } else {
                        arg
                    };
                    match client.get_document(slug) {
                        Ok(doc) => {
                            current_doc = Some(doc.slug.clone());
                            
                            println!("\n{}", doc.title.bold());
                            println!("{}", "=".repeat(50));
                            println!("Slug:    {}", doc.slug.cyan());
                            println!("Pages:   {}", doc.total_pages);
                            if let Some(ref source) = doc.source_file {
                                println!("Source:  {}", source);
                            }
                            
                            // Element counts
                            let total: i32 = doc.element_counts.values().sum();
                            if total > 0 {
                                println!("\n{}", "Elements:".bold());
                                for (t, c) in &doc.element_counts {
                                    if *c > 0 {
                                        println!("  {}: {}", t, c);
                                    }
                                }
                                println!("\nUse 'figures', 'tables', or 'equations' to browse");
                            }
                            
                            if let Some(ref keywords) = doc.keywords {
                                if !keywords.is_empty() {
                                    println!("\n{}", "Keywords:".bold());
                                    println!("  {}", keywords.join(", "));
                                }
                            }
                            
                            if let Some(ref summary) = doc.summary {
                                println!("\n{}", "Summary:".bold());
                                println!("{}", summary);
                            }
                            println!();
                        }
                        Err(e) => println!("{}: {}\n", "Error".red(), e),
                    }
                    continue;
                }

                // Browse elements - from current page if viewing, otherwise from document
                if lower == "figures" || lower == "tables" || lower == "equations" {
                    let (doc_slug, page_filter) = match (&last_page_view, &current_doc) {
                        (Some((slug, page_num, _)), _) => (slug.clone(), Some(*page_num)),
                        (None, Some(slug)) => (slug.clone(), None),
                        (None, None) => {
                            println!("Use 'doc <slug>' or view a page first.\n");
                            continue;
                        }
                    };
                    
                    let element_type = match lower.as_str() {
                        "figures" => "figure",
                        "tables" => "table",
                        "equations" => "equation",
                        _ => unreachable!(),
                    };
                    
                    // Get more results so we can filter by page if needed
                    let req = SearchRequest {
                        query: "*".to_string(),  // Match all
                        limit: if page_filter.is_some() { 50 } else { 20 },
                        document_slug: Some(doc_slug.clone()),
                        include_chunks: false,
                        include_elements: true,
                        element_type: Some(element_type.to_string()),
                    };
                    
                    match client.search(req) {
                        Ok(response) => {
                            // Filter by page if we're viewing a specific page
                            let results: Vec<_> = if let Some(page_num) = page_filter {
                                response.results.into_iter()
                                    .filter(|r| r.page_number == page_num)
                                    .collect()
                            } else {
                                response.results
                            };
                            
                            if results.is_empty() {
                                if let Some(page_num) = page_filter {
                                    println!("No {} on page {} of {}.", lower, page_num, doc_slug);
                                    println!("Use '{} all' to see all {} in document.\n", lower, lower);
                                } else {
                                    println!("No {} found in {}.\n", lower, doc_slug);
                                }
                            } else {
                                let scope = if let Some(page_num) = page_filter {
                                    format!("{} p.{}", doc_slug, page_num)
                                } else {
                                    doc_slug.clone()
                                };
                                
                                println!("\n{} in {} ({} found):", 
                                    lower.to_uppercase().bold(), 
                                    scope.cyan(),
                                    results.len());
                                println!("{}", "=".repeat(50));
                                
                                for (i, result) in results.iter().enumerate() {
                                    let label = result.element_label.as_deref().unwrap_or("(unlabeled)");
                                    let page = result.page_number;
                                    let preview = result.content.chars().take(60).collect::<String>();
                                    let preview = if result.content.len() > 60 {
                                        format!("{}...", preview)
                                    } else {
                                        preview
                                    };
                                    println!("[{}] {} (p.{})", (i + 1).to_string().yellow(), label, page);
                                    println!("    {}", preview.dimmed());
                                }
                                
                                last_sources = results;
                                println!("\nUse 'show N' or 'open N' to view.\n");
                            }
                        }
                        Err(e) => println!("{}: {}\n", "Error".red(), e),
                    }
                    continue;
                }
                
                // Browse ALL elements in document (ignoring page context)
                if lower == "figures all" || lower == "tables all" || lower == "equations all" {
                    let doc_slug = match &current_doc {
                        Some(slug) => slug.clone(),
                        None => {
                            println!("Use 'doc <slug>' first to select a document.\n");
                            continue;
                        }
                    };
                    
                    let element_type = match lower.as_str() {
                        "figures all" => "figure",
                        "tables all" => "table",
                        "equations all" => "equation",
                        _ => unreachable!(),
                    };
                    let type_plural = match lower.as_str() {
                        "figures all" => "figures",
                        "tables all" => "tables",
                        "equations all" => "equations",
                        _ => unreachable!(),
                    };
                    
                    let req = SearchRequest {
                        query: "*".to_string(),
                        limit: 50,  // Show more for "all"
                        document_slug: Some(doc_slug.clone()),
                        include_chunks: false,
                        include_elements: true,
                        element_type: Some(element_type.to_string()),
                    };
                    
                    match client.search(req) {
                        Ok(response) => {
                            if response.results.is_empty() {
                                println!("No {} found in {}.\n", type_plural, doc_slug);
                            } else {
                                println!("\n{} in {} ({} found):", 
                                    type_plural.to_uppercase().bold(), 
                                    doc_slug.cyan(),
                                    response.results.len());
                                println!("{}", "=".repeat(50));
                                
                                for (i, result) in response.results.iter().enumerate() {
                                    let label = result.element_label.as_deref().unwrap_or("(unlabeled)");
                                    let page = result.page_number;
                                    let preview = result.content.chars().take(60).collect::<String>();
                                    let preview = if result.content.len() > 60 {
                                        format!("{}...", preview)
                                    } else {
                                        preview
                                    };
                                    println!("[{}] {} (p.{})", (i + 1).to_string().yellow(), label, page);
                                    println!("    {}", preview.dimmed());
                                }
                                
                                last_sources = response.results;
                                println!("\nUse 'show N' or 'open N' to view.\n");
                            }
                        }
                        Err(e) => println!("{}: {}\n", "Error".red(), e),
                    }
                    continue;
                }

                // Fast search (no LLM)
                if lower.starts_with("search ") {
                    let query = input[7..].trim();
                    if query.is_empty() {
                        println!("Usage: search <query>\n");
                        continue;
                    }
                    
                    let req = SearchRequest {
                        query: query.to_string(),
                        limit: 10,
                        document_slug: current_doc.clone(),
                        include_chunks: true,
                        include_elements: true,
                        element_type: None,
                    };
                    
                    println!("{}", "Searching...".dimmed());
                    
                    match client.search(req) {
                        Ok(response) => {
                            if response.results.is_empty() {
                                println!("No results found.\n");
                            } else {
                                let scope = if current_doc.is_some() {
                                    format!(" in {}", current_doc.as_ref().unwrap().cyan())
                                } else {
                                    String::new()
                                };
                                println!("\n{} results{}:\n", response.results.len().to_string().green(), scope);
                                
                                for (i, result) in response.results.iter().enumerate() {
                                    println!("{}", format_result(i + 1, result, true));
                                    println!();
                                }
                                
                                last_sources = response.results;
                                
                                let has_elements = last_sources.iter().any(|s| s.source_type == "element");
                                if has_elements {
                                    println!("Use 'show N' or 'open N' to view images.\n");
                                }
                            }
                        }
                        Err(e) => println!("{}: {}\n", "Error".red(), e),
                    }
                    continue;
                }

                // Regular question (LLM-powered)
                println!("{}", "Searching...".dimmed());

                let req = ChatRequest {
                    question: input.to_string(),
                    limit: 8,
                    document_slug: current_doc.clone(),
                };

                match client.chat(req) {
                    Ok(response) => {
                        println!("{}", "Thinking...".dimmed());
                        println!(
                            "\n{} {}\n",
                            "Assistant:".blue().bold(),
                            response.answer
                        );

                        last_sources = response.sources;

                        // Show sources in same format as search results
                        if !last_sources.is_empty() {
                            println!("{} ({}):", "Sources".dimmed(), last_sources.len());
                            for (i, result) in last_sources.iter().enumerate() {
                                let (type_str, label) = if result.source_type == "element" {
                                    let t = result.element_type.as_ref()
                                        .map(|t| t.to_uppercase())
                                        .unwrap_or_else(|| "ELEMENT".to_string());
                                    let l = result.element_label.as_deref().unwrap_or("").to_string();
                                    (t, l)
                                } else {
                                    let chunk_num = result.chunk_index.unwrap_or(0) + 1;
                                    ("CHUNK".to_string(), format!("#{}", chunk_num))
                                };
                                println!(
                                    "  [{}] {} {} - {} p.{}",
                                    (i + 1).to_string().yellow(),
                                    type_str.cyan(),
                                    label,
                                    result.document_slug.dimmed(),
                                    result.page_number
                                );
                            }
                            
                            let has_elements = last_sources.iter().any(|s| s.source_type == "element");
                            if has_elements {
                                println!("\nUse 'show N' to view, or 'page <slug> <N>' for full page.\n");
                            } else {
                                println!("\nUse 'page <slug> <N>' to view full page.\n");
                            }
                        }
                    }
                    Err(e) => {
                        println!("{}: {}\n", "Error".red(), e);
                    }
                }
            }
            Err(ReadlineError::Interrupted) => {
                println!("\nGoodbye!");
                break;
            }
            Err(ReadlineError::Eof) => {
                println!("\nGoodbye!");
                break;
            }
            Err(err) => {
                println!("Error: {:?}", err);
                break;
            }
        }
    }

    Ok(())
}

fn handle_show_command(client: &OsgeoClient, arg: &str, sources: &[SearchResult]) {
    if sources.is_empty() {
        println!("No results to show. Ask a question first.\n");
        return;
    }

    // Parse indices: "1,2,3" or "1 2 3"
    let indices: Vec<usize> = arg
        .split(|c: char| c == ',' || c.is_whitespace())
        .filter_map(|s| s.trim().parse::<usize>().ok())
        .map(|n| n.saturating_sub(1)) // Convert to 0-indexed
        .collect();

    if indices.is_empty() {
        println!("Usage: show <number> or show 1,2,3\n");
        return;
    }

    for idx in indices {
        if idx >= sources.len() {
            println!("Invalid index [{}]. Use 1-{}\n", idx + 1, sources.len());
            continue;
        }

        let result = &sources[idx];

        if result.source_type != "element" {
            println!(
                "[{}] is a text chunk, no image available.\n",
                idx + 1
            );
            println!("Content: {}...\n", &result.content[..200.min(result.content.len())]);
            continue;
        }

        if let Some(image_path) = result.best_image_path() {
            let elem_type = result
                .element_type
                .as_ref()
                .map(|s| s.to_uppercase())
                .unwrap_or_default();
            let label = result.element_label.as_deref().unwrap_or("");

            println!("\n{}: {}", elem_type.yellow(), label);
            println!(
                "From: {}, page {}\n",
                result.document_title, result.page_number
            );

            // Fetch image from server and display with chafa
            let image_url = format!(
                "{}/image/{}/{}",
                client.base_url, result.document_slug, image_path
            );

            let size = result.chafa_size();
            match client.fetch_and_display_image(&image_url, &size) {
                Ok(_) => {}
                Err(e) => {
                    println!("{}: {}", "Failed to display image".red(), e);
                    println!(
                        "{}: {}/{}",
                        "Image path".dimmed(),
                        result.document_slug,
                        image_path
                    );
                }
            }
        } else {
            println!("[{}] has no image path.\n", idx + 1);
        }
    }
}

fn handle_open_command(client: &OsgeoClient, arg: &str, sources: &[SearchResult]) {
    if sources.is_empty() {
        println!("No results to open. Ask a question first.\n");
        return;
    }

    // Parse indices: "1,2,3" or "1 2 3"
    let indices: Vec<usize> = arg
        .split(|c: char| c == ',' || c.is_whitespace())
        .filter_map(|s| s.trim().parse::<usize>().ok())
        .map(|n| n.saturating_sub(1))
        .collect();

    if indices.is_empty() {
        println!("Usage: open <number> or open 1,2,3\n");
        return;
    }

    for idx in indices {
        if idx >= sources.len() {
            println!("Invalid index [{}]. Use 1-{}\n", idx + 1, sources.len());
            continue;
        }

        let result = &sources[idx];

        if result.source_type != "element" {
            println!("[{}] is a text chunk, no image available.\n", idx + 1);
            continue;
        }

        if let Some(image_path) = result.best_image_path() {
            let elem_type = result
                .element_type
                .as_ref()
                .map(|s| s.to_uppercase())
                .unwrap_or_default();
            let label = result.element_label.as_deref().unwrap_or("");

            println!("Opening {}: {}", elem_type.yellow(), label);

            let image_url = format!(
                "{}/image/{}/{}",
                client.base_url, result.document_slug, image_path
            );

            match client.fetch_and_open_image(&image_url) {
                Ok(_) => {}
                Err(e) => {
                    println!("{}: {}", "Failed to open image".red(), e);
                }
            }
        } else {
            println!("[{}] has no image path.\n", idx + 1);
        }
    }
}

// -----------------------------------------------------------------------------
// Main
// -----------------------------------------------------------------------------

fn main() -> Result<()> {
    let cli = Cli::parse();

    let server_url = cli.server.unwrap_or_else(|| DEFAULT_SERVER_URL.to_string());

    // Create client and handle connection errors with helpful messages
    let client = match OsgeoClient::new(&server_url) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("{}: {}", "Error".red().bold(), e);
            std::process::exit(1);
        }
    };

    // Check if we can connect to the server
    let check_connection = |client: &OsgeoClient| -> Result<()> {
        match client.health() {
            Ok(_) => Ok(()),
            Err(_) => {
                eprintln!(
                    "{}: Could not connect to server at {}\n",
                    "Error".red().bold(),
                    server_url
                );
                eprintln!("The osgeo-library server is not running or not accessible.\n");
                eprintln!("If you're on the server:");
                eprintln!("  - Check the server log: tail ~/logs/osgeo-library.log");
                eprintln!("  - Start manually: ~/github/osgeo-library/servers/start-server.sh &\n");
                eprintln!("If you're on a remote machine:");
                eprintln!("  - Set up SSH port forwarding:");
                eprintln!("    ssh -L 8095:localhost:8095 osgeo7-gallery\n");
                std::process::exit(1);
            }
        }
    };

    let result = match cli.command {
        Some(Commands::Health) => cmd_health(&client),
        Some(Commands::Docs { page, limit, sort }) => {
            check_connection(&client)?;
            cmd_docs(&client, page, limit, sort)
        }
        Some(Commands::Doc { slug }) => {
            check_connection(&client)?;
            cmd_doc(&client, slug)
        }
        Some(Commands::Search {
            query,
            limit,
            document,
            elements_only,
            chunks_only,
            r#type,
            show,
            open,
        }) => {
            check_connection(&client)?;
            cmd_search(&client, query, limit, document, elements_only, chunks_only, r#type, show, open)
        }
        Some(Commands::Ask {
            question,
            limit,
            document,
        }) => {
            check_connection(&client)?;
            cmd_ask(&client, question, limit, document)
        }
        Some(Commands::Chat) | None => {
            // Chat is default (when no subcommand given)
            check_connection(&client)?;
            cmd_chat(&client)
        }
    };

    if let Err(e) = result {
        eprintln!("{}: {}", "Error".red().bold(), e);
        std::process::exit(1);
    }

    Ok(())
}
