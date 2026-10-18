"""Entry point for the MCP process: `uvicorn backend.mcp_main:app --port 8001`."""

from backend.gridiron.config import get_settings
from backend.gridiron.mcp_server import create_app

app = create_app(get_settings().gridiron_mcp_token)
