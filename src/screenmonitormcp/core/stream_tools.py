"""Streaming-related tools for ScreenMonitorMCP."""

import json
from mcp.server.fastmcp import FastMCP
import logging
from .streaming import stream_manager

logger = logging.getLogger(__name__)

def register_stream_tools(mcp: FastMCP):
    @mcp.tool()
    async def create_stream(
        monitor: int = 0,
        fps: int = 10,
        quality: int = 80,
        format: str = "jpeg"
    ) -> str:
        """Create a new screen streaming session"""
        try:
            stream_id = await stream_manager.create_stream("screen", fps, quality, format)
            return json.dumps({
                "success": True,
                "data": {
                    "stream_id": stream_id
                }
            })
        except Exception as e:
            logger.error(f"Failed to create stream: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "create_stream_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    def list_streams() -> str:
        """List all active streaming sessions"""
        try:
            streams = stream_manager.list_streams()
            return json.dumps({
                "success": True,
                "data": streams
            })
        except Exception as e:
            logger.error(f"Failed to list streams: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "list_streams_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def get_stream_info(stream_id: str) -> str:
        """Get information about a specific stream"""
        try:
            info = await stream_manager.get_stream_info(stream_id)
            return json.dumps({
                "success": True,
                "data": info
            })
        except Exception as e:
            logger.error(f"Failed to get stream info: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "get_stream_info_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def stop_stream(stream_id: str) -> str:
        """Stop a specific streaming session"""
        try:
            result = await stream_manager.stop_stream(stream_id)
            return json.dumps({
                "success": True,
                "data": result
            })
        except Exception as e:
            logger.error(f"Failed to stop stream: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "stop_stream_failed",
                    "message": str(e)
                }
            })
