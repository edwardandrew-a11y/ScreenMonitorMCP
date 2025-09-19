import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from src.screenmonitormcp.core.system_tools import register_system_tools


@pytest.fixture
def mcp_server():
    return FastMCP("test-server")

def test_get_system_status(mcp_server):
    """Tests the get_system_status tool."""
    # Mock the dependencies
    ai_service_mock = MagicMock()
    ai_service_mock.is_available.return_value = True

    screen_capture_mock = MagicMock()
    screen_capture_mock.is_available.return_value = True

    performance_monitor_mock = MagicMock()
    performance_monitor_mock.is_running.return_value = True

    stream_manager_mock = MagicMock()
    stream_manager_mock.is_running.return_value = True

    with patch("src.screenmonitormcp.core.system_tools.ai_service", ai_service_mock), \
         patch("src.screenmonitormcp.core.system_tools.screen_capture", screen_capture_mock), \
         patch("src.screenmonitormcp.core.system_tools.performance_monitor", performance_monitor_mock), \
         patch("src.screenmonitormcp.core.system_tools.stream_manager", stream_manager_mock):

        # Register the tools
        register_system_tools(mcp_server)

        # Get the tool function
        get_system_status_tool = mcp_server.tools["get_system_status"]

        # Run the tool
        result_str = asyncio.run(get_system_status_tool.coro())
        result = json.loads(result_str)

        # Assert the result
        assert result["success"] is True
        assert result["data"]["ai_service"] is True
        assert result["data"]["screen_capture"] is True
        assert result["data"]["performance_monitor"] is True
        assert result["data"]["stream_manager"] is True
