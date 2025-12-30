#!/usr/bin/env python3
"""
Command-line interface for doclibrary.

Provides unified access to all doclibrary functionality through subcommands.

Usage:
    doclibrary extract document.pdf --pages 1,2,3 --output-dir output/
    doclibrary enrich sam3 --skip-existing
    doclibrary ingest sam3 --delete-first
    doclibrary search "oblique mercator projection"
    doclibrary chat
    doclibrary serve
    doclibrary config

Available commands:
    extract     - Extract elements from PDF documents
    enrich      - Generate search_text for extracted elements
    ingest      - Ingest extracted documents into the database
    search      - Search the document library
    chat        - Interactive chat with the library
    serve       - Start the API server
    config      - Show current configuration
"""

import argparse
import sys
from pathlib import Path


def cmd_extract(args):
    """Extract elements from PDF documents."""
    import fitz  # PyMuPDF

    from doclibrary.extraction import extract_document

    if not args.pdf_path.exists():
        print(f"Error: File not found: {args.pdf_path}", file=sys.stderr)
        return 1

    # Handle "all" or range syntax for pages
    if args.pages.lower() == "all":
        doc = fitz.open(str(args.pdf_path))
        pages = list(range(1, len(doc) + 1))
        doc.close()
    elif "-" in args.pages and "," not in args.pages:
        # Range like "1-10"
        start, end = args.pages.split("-", 1)
        pages = list(range(int(start), int(end) + 1))
    else:
        # Comma-separated like "1,2,3"
        pages = [int(p.strip()) for p in args.pages.split(",")]

    extract_document(
        pdf_path=args.pdf_path,
        output_dir=args.output_dir,
        pages=pages,
        dpi=args.dpi,
        skip_existing=args.skip_existing,
    )
    return 0


def cmd_enrich(args):
    """Generate search_text for extracted elements."""
    from doclibrary.extraction import enrich_document, list_documents

    if args.list:
        docs = list_documents()
        if docs:
            print("\nAvailable documents:")
            print("-" * 60)
            for doc in docs:
                status = f"{doc['enriched']}/{doc['elements']} enriched"
                if doc["enriched"] == doc["elements"] and doc["elements"] > 0:
                    status += " [complete]"
                elif doc["enriched"] > 0:
                    status += " [partial]"
                print(f"  {doc['name']:20} {status}")
        else:
            print("No documents found in db/data/")
        return 0

    if args.all:
        docs = list_documents()
        for doc in docs:
            enrich_document(doc["name"], dry_run=args.dry_run, skip_existing=args.skip_existing)
    elif args.document:
        enrich_document(args.document, dry_run=args.dry_run, skip_existing=args.skip_existing)
    else:
        print("Error: Specify a document name, --all, or --list", file=sys.stderr)
        return 1

    return 0


def cmd_ingest(args):
    """Ingest extracted documents into the database."""
    from doclibrary.db.ingest import ingest_all, ingest_document, list_available_documents

    if args.list:
        docs = list_available_documents()
        if docs:
            print("\nDocument Ingestion Status")
            print("=" * 70)
            for doc in docs:
                status = f"[in DB, id={doc['db_id']}]" if doc["in_db"] else "[not ingested]"
                print(
                    f"  {doc['name']:30} {doc['pages']:3} pages, "
                    f"{doc['elements']:3} elements  {status}"
                )
        else:
            print("No documents found in data directory")
        return 0

    embed = not args.no_embed

    if args.all:
        ingest_all(
            dry_run=args.dry_run,
            skip_existing=args.skip_existing,
            delete_first=args.delete_first,
            embed_content=embed,
        )
    elif args.document:
        success = ingest_document(
            args.document,
            dry_run=args.dry_run,
            skip_existing=args.skip_existing,
            delete_first=args.delete_first,
            embed_content=embed,
        )
        if not success:
            return 1
    else:
        print("Error: Specify a document name, --all, or --list", file=sys.stderr)
        return 1

    return 0


def cmd_search(args):
    """Search the document library."""
    from doclibrary.search import check_server, search, search_chunks, search_elements
    from doclibrary.search.service import format_result

    if not check_server():
        print("ERROR: Embedding server not available", file=sys.stderr)
        return 1

    print(f"Searching: {args.query}")
    print("=" * 60)

    try:
        if args.chunks_only:
            results = search_chunks(args.query, args.limit, args.document)
        elif args.elements_only:
            results = search_elements(args.query, args.limit, args.document, args.type)
        else:
            results = search(args.query, args.limit, args.document)

        if not results:
            print("No results found.")
        else:
            for i, result in enumerate(results, 1):
                print(f"\n{i}. {format_result(result, args.verbose)}")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0


def cmd_chat(args):
    """Interactive chat with the library."""
    from doclibrary.chat import ChatContext, handle_command, process_question
    from doclibrary.config import config
    from doclibrary.core.llm import check_llm_health
    from doclibrary.search import check_server as check_embed_server

    model = args.model or config.llm_model

    # Check servers
    print("doclibrary Chat")
    print("=" * 40)

    if not check_embed_server():
        print(f"ERROR: Embedding server not running at {config.embed_url}", file=sys.stderr)
        return 1
    print("Embedding server: OK")

    if not check_llm_health(config.llm_url):
        print(f"ERROR: LLM server not running at {config.llm_url}", file=sys.stderr)
        return 1
    print(f"LLM server: OK (using {model})")

    print("\nType 'help' for commands, 'quit' to exit.\n")

    ctx = ChatContext()

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Check for commands
        cmd_result = handle_command(ctx, user_input)
        if cmd_result is None:  # Exit
            print("Goodbye!")
            break
        if cmd_result is True:  # Command handled
            continue

        # Process as question
        response = process_question(ctx, user_input, model)
        print(f"Assistant: {response}\n")

        # Show available sources hint
        if ctx.last_results:
            elements = [r for r in ctx.last_results if r.source_type == "element"]
            if elements:
                print("(Type 'sources' for references, 'show N' for images)\n")

    return 0


def cmd_serve(args):
    """Start the API server."""
    import uvicorn

    from doclibrary.config import config

    print("Starting doclibrary API server...")
    print(f"Config source: {config.config_source}")
    print(f"Embedding server: {config.embed_url}")
    print(f"LLM: {config.llm_model} @ {config.llm_url}")
    print()

    uvicorn.run(
        "doclibrary.servers.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def cmd_mcp(args):
    """Start MCP server for AI assistants."""
    from doclibrary.servers.mcp import main as mcp_main

    print("Starting doclibrary MCP server...", file=sys.stderr)
    print("This server provides tools for AI assistants like Claude Desktop.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Available tools:", file=sys.stderr)
    print("  - search_documents: Search the document library", file=sys.stderr)
    print("  - search_visual_elements: Search figures, tables, equations", file=sys.stderr)
    print("  - get_element_details: Get details for a specific element", file=sys.stderr)
    print("  - list_documents: List all available documents", file=sys.stderr)
    print("  - get_library_status: Check service status", file=sys.stderr)
    print("", file=sys.stderr)

    mcp_main()
    return 0


def cmd_config(args):
    """Show current configuration."""
    from doclibrary.config import config

    print("doclibrary Configuration")
    print("=" * 50)
    print(f"Config source: {config.config_source}")
    print()

    print("[LLM - Chat/Search]")
    print(f"  url: {config.llm_url}")
    print(f"  model: {config.llm_model}")
    print(f"  api_key: {'***' if config.llm_api_key else '(not set)'}")
    print()

    print("[Vision LLM - Extraction]")
    print(f"  url: {config.vision_llm_url}")
    print(f"  model: {config.vision_llm_model}")
    print()

    print("[Enrichment LLM]")
    print(f"  url: {config.enrichment_llm_url}")
    print(f"  model: {config.enrichment_llm_model}")
    print()

    print("[Embedding]")
    print(f"  url: {config.embed_url}")
    print(f"  dimensions: {config.embed_dimensions}")
    print()

    print("[Database]")
    print(f"  name: {config.db_name}")
    print(f"  host: {config.db_host or '(Unix socket)'}")
    print(f"  port: {config.db_port}")
    print(f"  user: {config.db_user or '(current user)'}")
    print()

    print("[Paths]")
    print(f"  data_dir: {config.data_dir}")

    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="doclibrary",
        description="Extract and search visual elements from scientific PDFs",
    )
    parser.add_argument("--version", action="version", version="doclibrary 1.0.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- extract ---
    p_extract = subparsers.add_parser("extract", help="Extract elements from PDF documents")
    p_extract.add_argument("pdf_path", type=Path, help="Path to PDF file")
    p_extract.add_argument(
        "--pages", type=str, required=True, help="Pages: 'all', '1-10', or '1,2,3'"
    )
    p_extract.add_argument("--output-dir", type=Path, required=True, help="Output directory")
    p_extract.add_argument("--dpi", type=int, default=150, help="Page rendering DPI")
    p_extract.add_argument(
        "--skip-existing", action="store_true", help="Skip pages already extracted"
    )
    p_extract.set_defaults(func=cmd_extract)

    # --- enrich ---
    p_enrich = subparsers.add_parser("enrich", help="Generate search_text for elements")
    p_enrich.add_argument("document", nargs="?", help="Document name to process")
    p_enrich.add_argument("--all", action="store_true", help="Process all documents")
    p_enrich.add_argument("--list", action="store_true", help="List available documents")
    p_enrich.add_argument("--dry-run", action="store_true", help="Preview without changes")
    p_enrich.add_argument(
        "--skip-existing", action="store_true", help="Skip already enriched elements"
    )
    p_enrich.set_defaults(func=cmd_enrich)

    # --- ingest ---
    p_ingest = subparsers.add_parser("ingest", help="Ingest documents into the database")
    p_ingest.add_argument("document", nargs="?", help="Document name to ingest")
    p_ingest.add_argument("--all", action="store_true", help="Ingest all documents")
    p_ingest.add_argument("--list", action="store_true", help="List available documents")
    p_ingest.add_argument("--dry-run", action="store_true", help="Preview without changes")
    p_ingest.add_argument(
        "--skip-existing", action="store_true", help="Skip documents already in database"
    )
    p_ingest.add_argument(
        "--delete-first", action="store_true", help="Delete existing document before re-ingesting"
    )
    p_ingest.add_argument("--no-embed", action="store_true", help="Skip embedding generation")
    p_ingest.set_defaults(func=cmd_ingest)

    # --- search ---
    p_search = subparsers.add_parser("search", help="Search the document library")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("-n", "--limit", type=int, default=10, help="Number of results")
    p_search.add_argument("-d", "--document", help="Filter by document slug")
    p_search.add_argument("-t", "--type", help="Filter elements by type")
    p_search.add_argument("--chunks-only", action="store_true", help="Search only text chunks")
    p_search.add_argument("--elements-only", action="store_true", help="Search only elements")
    p_search.add_argument("-v", "--verbose", action="store_true", help="Show content snippets")
    p_search.set_defaults(func=cmd_search)

    # --- chat ---
    p_chat = subparsers.add_parser("chat", help="Interactive chat with the library")
    p_chat.add_argument("--model", default=None, help="LLM model to use")
    p_chat.set_defaults(func=cmd_chat)

    # --- serve ---
    p_serve = subparsers.add_parser("serve", help="Start the API server")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    p_serve.add_argument("--port", type=int, default=8095, help="Port to bind to")
    p_serve.add_argument("--reload", action="store_true", help="Enable auto-reload")
    p_serve.set_defaults(func=cmd_serve)

    # --- config ---
    p_config = subparsers.add_parser("config", help="Show current configuration")
    p_config.set_defaults(func=cmd_config)

    # --- mcp ---
    p_mcp = subparsers.add_parser("mcp", help="Start MCP server for AI assistants")
    p_mcp.set_defaults(func=cmd_mcp)

    # Parse args
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
