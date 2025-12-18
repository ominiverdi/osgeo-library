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
    chunk_index: Option<i32>,
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

// -----------------------------------------------------------------------------
// CLI Definition
// -----------------------------------------------------------------------------

#[derive(Parser)]
#[command(name = "osgeo-library")]
#[command(about = "Search and chat with the OSGeo Library", long_about = None)]
#[command(version)]
struct Cli {
    /// Server URL (default: http://127.0.0.1:8095)
    #[arg(short, long, env = "OSGEO_SERVER_URL")]
    server: Option<String>,

    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Search documents
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

        /// Filter by element type (figure, table, equation, chart, diagram)
        #[arg(short, long)]
        r#type: Option<String>,

        /// Show images: --show (first), --show 1, --show 1,3,5
        #[arg(long, value_name = "N", num_args = 0..=1, default_missing_value = "1")]
        show: Option<String>,
    },

    /// Ask a question (one-shot)
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

    /// Interactive chat mode (default)
    Chat,

    /// Check server health
    Health,
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

    fn fetch_and_display_image(&self, url: &str, element_type: Option<&str>) -> Result<()> {
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

        // Write to temp file
        let temp_path = std::env::temp_dir().join("osgeo-library-image.png");
        std::fs::write(&temp_path, &bytes).context("Failed to write temp file")?;

        // Choose size based on element type
        let size = match element_type {
            Some("equation") => "100x15",   // Wide and short for equations
            Some("table") => "100x50",      // Large for tables
            Some("chart") => "90x40",       // Medium-large for charts
            Some("diagram") => "90x40",     // Medium-large for diagrams
            Some("figure") => "80x35",      // Standard for figures
            _ => "80x35",                   // Default
        };

        // Display with chafa if available
        if Command::new("which")
            .arg("chafa")
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
        {
            let status = Command::new("chafa")
                .args(["--size", size, temp_path.to_str().unwrap()])
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
    let tag = get_source_tag(result);
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
            "[{}:{}] {} {}",
            tag.cyan(),
            i.to_string().cyan(),
            elem_type.yellow(),
            label
        ));
        lines.push(format!(
            "       {} p.{} | {:.0}%",
            result.document_title.dimmed(),
            result.page_number,
            result.score_pct
        ));
    } else {
        let chunk_idx = result.chunk_index.unwrap_or(0);
        lines.push(format!(
            "[{}:{}] TEXT chunk {}",
            tag.cyan(),
            i.to_string().cyan(),
            chunk_idx
        ));
        lines.push(format!(
            "       {} p.{} | {:.0}%",
            result.document_title.dimmed(),
            result.page_number,
            result.score_pct
        ));
    }

    if verbose && !result.content.is_empty() {
        let preview: String = result.content.chars().take(200).collect();
        lines.push(format!("       {}", preview.dimmed()));
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

fn cmd_search(
    client: &OsgeoClient,
    query: String,
    limit: i32,
    document: Option<String>,
    elements_only: bool,
    chunks_only: bool,
    element_type: Option<String>,
    show: Option<String>,
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

            if let Some(crop_path) = &result.crop_path {
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
                    client.base_url, result.document_slug, crop_path
                );

                if let Err(e) = client.fetch_and_display_image(&image_url, result.element_type.as_deref()) {
                    println!("{}: {}", "Failed to display image".red(), e);
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

    loop {
        let readline = rl.readline(&format!("{} ", "You:".green().bold()));

        match readline {
            Ok(line) => {
                let input = line.trim();
                if input.is_empty() {
                    continue;
                }

                rl.add_history_entry(input)?;

                // Handle commands
                let lower = input.to_lowercase();

                if lower == "quit" || lower == "exit" || lower == "q" {
                    println!("Goodbye!");
                    break;
                }

                if lower == "help" || lower == "?" {
                    println!("\n{}", "Commands:".bold());
                    println!("  show <n>     Display element image (e.g., 'show 1' or 'show 1,2,3')");
                    println!("  sources      Show sources from last answer");
                    println!("  clear        Clear conversation (not implemented yet)");
                    println!("  help         Show this help");
                    println!("  quit/exit    Exit\n");
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
                    let arg = &input[5..].trim();
                    handle_show_command(client, arg, &last_sources);
                    continue;
                }

                // Regular question
                println!("{}", "Searching...".dimmed());

                let req = ChatRequest {
                    question: input.to_string(),
                    limit: 8,
                    document_slug: None,
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

                        if !last_sources.is_empty() {
                            let elem_count = last_sources
                                .iter()
                                .filter(|s| s.source_type == "element")
                                .count();
                            if elem_count > 0 {
                                println!(
                                    "(Type 'sources' for references, 'show N' for images)\n"
                                );
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

        if let Some(crop_path) = &result.crop_path {
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
                client.base_url, result.document_slug, crop_path
            );

            match client.fetch_and_display_image(&image_url, result.element_type.as_deref()) {
                Ok(_) => {}
                Err(e) => {
                    println!("{}: {}", "Failed to display image".red(), e);
                    println!(
                        "{}: {}/{}",
                        "Image path".dimmed(),
                        result.document_slug,
                        crop_path
                    );
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
        Some(Commands::Search {
            query,
            limit,
            document,
            elements_only,
            chunks_only,
            r#type,
            show,
        }) => {
            check_connection(&client)?;
            cmd_search(&client, query, limit, document, elements_only, chunks_only, r#type, show)
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
