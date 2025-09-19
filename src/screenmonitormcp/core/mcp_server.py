"""ScreenMonitorMCP v2 - Model Context Protocol (MCP) Server Implementation

This module implements the MCP server for ScreenMonitorMCP v2, providing
screen capture and analysis capabilities through the Model Context Protocol.

The server operates using the official MCP Python SDK FastMCP API and provides tools for:
- Screen capture
- Screen analysis with AI
- Real-time monitoring

Author: ScreenMonitorMCP Team
Version: 2.0.0
License: MIT
"""

import asyncio
import logging
import base64
import sys
from typing import Any, Optional
from datetime import datetime

# Official MCP Python SDK FastMCP imports
from mcp.server.fastmcp import FastMCP

try:
    from .screen_capture import ScreenCapture
    from .ai_service import ai_service
    from .streaming import stream_manager
    from .performance_monitor import performance_monitor
    from ..server.config import config
    from .ai_tools import register_ai_tools
    from .stream_tools import register_stream_tools
    from .memory_tools import register_memory_tools
    from .system_tools import register_system_tools
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from core.screen_capture import ScreenCapture
    from core.ai_service import ai_service
    from core.streaming import stream_manager
    from core.performance_monitor import performance_monitor
    from server.config import config
    from core.ai_tools import register_ai_tools
    from core.stream_tools import register_stream_tools
    from core.memory_tools import register_memory_tools
    from core.system_tools import register_system_tools

# Configure logger to use stderr for MCP mode
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)  # Only show errors in MCP mode

# Initialize FastMCP server
mcp = FastMCP("screenmonitormcp-v2")

# Initialize components
screen_capture = ScreenCapture()

# Register AI tools
register_ai_tools(mcp)

# Register stream tools
register_stream_tools(mcp)

# Register memory tools
register_memory_tools(mcp)

# Register system tools
register_system_tools(mcp)

def setup_logging():
    """Setup logging configuration for MCP mode."""
    # Disable all loggers except critical errors
    logging.getLogger().setLevel(logging.CRITICAL)

    # Disable specific noisy loggers
    for logger_name in ['httpx', 'openai', 'urllib3', 'requests']:
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)
        logging.getLogger(logger_name).disabled = True

def run_mcp_server():
    """Run the MCP server."""
    setup_logging()

    try:
        # Run the FastMCP server (it handles its own event loop)
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise

if __name__ == "__main__":
    run_mcp_server()