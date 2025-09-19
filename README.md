# ScreenMonitorMCP

[![Version](https://img.shields.io/badge/version-3.0.0-blue.svg)](https://github.com/inkbytefo/ScreenMonitorMCP/releases/tag/v3.0.0)
[![PyPI](https://img.shields.io/pypi/v/screenmonitormcp.svg)](https://pypi.org/project/screenmonitormcp/)
[![Python](https://img.shields.io/pypi/pyversions/screenmonitormcp.svg)](https://pypi.org/project/screenmonitormcp/)
[![Verified on MseeP](https://mseep.ai/badge.svg)](https://mseep.ai/app/a2dbda0f-f46d-40e1-9c13-0b47eff9df3a)
[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/inkbytefo-screenmonitormcp-badge.png)](https://mseep.ai/app/inkbytefo-screenmonitormcp)

A powerful Model Context Protocol (MCP) server that gives AI real-time vision capabilities and enhanced UI intelligence. Transform your AI assistant into a visual powerhouse that can see, analyze, and interact with your screen content.

## What is ScreenMonitorMCP?

ScreenMonitorMCP is a revolutionary MCP server that bridges the gap between AI and visual computing. It enables AI assistants to capture screenshots, analyze screen content, and provide intelligent insights about what's happening on your display.

## Key Features

- **Real-time Screen Capture**: Instant screenshot capabilities across multiple monitors.
- **AI-Powered Analysis**: Advanced screen content analysis using state-of-the-art vision models.
- **Streaming Support**: Live screen streaming for continuous monitoring.
- **Performance Monitoring**: Built-in system health and performance metrics.
- **Modular and Extensible**: A clean, modular architecture that is easy to extend.
- **Robust Error Handling**: Structured JSON error responses for programmatic error handling.
- **Multi-Platform**: Works seamlessly on Windows, macOS, and Linux.
- **Easy Integration**: Simple setup with Claude Desktop and other MCP clients.

## Quick Start

### Installation

```bash
# Install from PyPI
pip install screenmonitormcp

# Or install from source
git clone https://github.com/inkbytefo/screenmonitormcp.git
cd screenmonitormcp
pip install -e .
```

### Configuration

1. Create a `.env` file with your AI service credentials:

```env
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL=gpt-4o
```

2. Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "screenmonitormcp": {
      "command": "python",
      "args": ["-m", "src.screenmonitormcp.mcp_main"],
      "env": {
        "OPENAI_API_KEY": "your-openai-api-key-here",
        "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
        "OPENAI_MODEL": "qwen/qwen2.5-vl-32b-instruct:free"
      }
    }
  }
}
```

3. Restart Claude Desktop and start capturing!

## Available Tools

This refactored version of ScreenMonitorMCP provides a rich set of tools for screen analysis and interaction.

### Core Tools

- `capture_screen`: Captures the screen of a specified monitor and returns the image as a base64 string.
- `analyze_screen`: Performs AI-powered analysis of the screen content.
- `analyze_image`: Analyzes a given base64 encoded image with an AI vision model.
- `chat_completion`: Generates a chat completion using the configured AI model.

### Streaming Tools

- `create_stream`: Creates a new screen streaming session.
- `list_streams`: Lists all active streaming sessions.
- `get_stream_info`: Retrieves information about a specific stream.
- `stop_stream`: Stops a running stream.

### Memory Tools

- `analyze_scene_from_memory`: Analyzes a scene based on data stored in the memory system.
- `query_memory`: Queries the memory system for stored analysis data.
- `get_memory_statistics`: Retrieves statistics about the memory system.

### System Tools

- `get_performance_metrics`: Retrieves detailed performance metrics and system health.
- `get_system_status`: Gets the overall system status and health information.

**Note on Error Handling:** All tools now return a JSON string with a `success` field. If `success` is `false`, the JSON will contain an `error` object with a `code` and a `message`.

## Use Cases

- **UI/UX Analysis**: Get AI insights on interface design and usability.
- **Debugging Assistance**: Visual debugging with AI-powered error detection.
- **Content Creation**: Automated screenshot documentation and analysis.
- **Accessibility Testing**: Screen reader and accessibility compliance checking.
- **System Monitoring**: Visual system health and performance tracking.

## Documentation

For detailed setup instructions and advanced configuration, see our [MCP Setup Guide](MCP_SETUP_GUIDE.md).

## Requirements

- Python 3.8+
- OpenAI API key (or compatible service)
- MCP-compatible client (Claude Desktop, etc.)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Previous Version

Looking for v1 or v2? Check the [v1 branch](https://github.com/inkbytefo/ScreenMonitorMCP/tree/v1) or the commit history for previous versions.

---

**Built with ❤️ by [inkbytefo](https://github.com/inkbytefo)**
