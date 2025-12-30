"""Server components for doclibrary (FastAPI, MCP)."""


def create_app():
    """Create and configure the FastAPI application."""
    from .api import app

    return app


def run_mcp_server():
    """Run the MCP server with STDIO transport."""
    from .mcp import main

    main()


__all__ = ["create_app", "run_mcp_server"]
