# ScreenMonitorMCP - MCP Client Setup Guide

This guide will help you set up ScreenMonitorMCP with various MCP clients including Claude Desktop.

## Installation

### 1. Install the Package

```bash
# Install from PyPI
pip install screenmonitormcp

# Or install from source
pip install -e .
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

### Environment Variables

Create a `.env` file in your project directory:

```env
# AI Service Configuration
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

# Alternative: Use OpenRouter
# OPENAI_BASE_URL=https://openrouter.ai/api/v1
# OPENAI_MODEL=qwen/qwen2.5-vl-32b-instruct:free

# Server Configuration
SERVER_HOST=localhost
SERVER_PORT=8000
DEBUG=false
```

## Claude Desktop Setup

### 1. Locate Claude Desktop Config

Find your Claude Desktop configuration file:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### 2. Add MCP Server Configuration

Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "screenmonitormcp": {
      "command": "python",
      "args": ["-m", "src.screenmonitormcp.mcp_main"],
      "env": {
        "OPENAI_API_KEY": "your-openai-api-key-here",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "OPENAI_MODEL": "gpt-4o"
      }
    }
  }
}
```

### 3. Alternative: Using Installed Package

If you installed via pip, you can use:

```json
{
  "mcpServers": {
    "screenmonitormcp": {
      "command": "screenmonitormcp-mcp",
      "env": {
        "OPENAI_API_KEY": "your-openai-api-key-here",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "OPENAI_MODEL": "gpt-4o"
      }
    }
  }
}
```

### 4. Restart Claude Desktop

After updating the configuration, restart Claude Desktop to load the MCP server.

## Other MCP Clients

### Generic MCP Client

For other MCP clients, use the following command:

```bash
python -m src.screenmonitormcp.mcp_main
```

Or if installed via pip:

```bash
screenmonitormcp-mcp
```

### MCP Inspector (for testing)

```bash
npx @modelcontextprotocol/inspector python -m src.screenmonitormcp.mcp_main
```

## Available Tools

Once configured, you'll have access to these tools. All tools return a JSON string. On success, the JSON will have a `success` field set to `true` and a `data` field with the result. On failure, `success` will be `false` and there will be an `error` object with `code` and `message` fields.

### Core Tools

- `capture_screen(monitor: int = 0, format: str = "png")`: Captures the screen and returns a base64 encoded image.
- `analyze_screen(query: str, monitor: int = 0)`: Analyzes the screen content with an AI model.
- `analyze_image(image_base64: str, query: str)`: Analyzes a base64 encoded image.
- `chat_completion(messages: list, model: str = None, max_tokens: int = 1000, temperature: float = 0.7)`: Generates a chat completion.

### Streaming Tools

- `create_stream(monitor: int = 0, fps: int = 10, quality: int = 80, format: str = "jpeg")`: Creates a screen streaming session.
- `list_streams()`: Lists active streams.
- `get_stream_info(stream_id: str)`: Gets information about a stream.
- `stop_stream(stream_id: str)`: Stops a stream.

### Memory Tools

- `analyze_scene_from_memory(query: str, stream_id: str = None, time_range_minutes: int = 30, limit: int = 10)`: Analyzes a scene from memory.
- `query_memory(query: str, stream_id: str = None, time_range_minutes: int = 60, limit: int = 20)`: Queries the memory system.
- `get_memory_statistics()`: Gets memory system statistics.

### System Tools

- `get_performance_metrics()`: Gets performance metrics.
- `get_system_status()`: Gets system status.

## Usage Examples

### In Claude Desktop

Once configured, you can ask Claude:

- "Can you take a screenshot of my screen?"
- "What's currently displayed on my screen?"
- "Analyze my screen and tell me what applications are open"
- "Take a screenshot of the top-left corner of my screen"

### Testing the Setup

To test if everything is working:

1. Open Claude Desktop
2. Start a new conversation
3. Ask: "Can you take a screenshot?"
4. Claude should be able to capture and analyze your screen

## Troubleshooting

### Common Issues

1. **"Tool not found" error**:
   - Check that the MCP server is properly configured in `claude_desktop_config.json`
   - Restart Claude Desktop after configuration changes

2. **"Permission denied" error**:
   - Ensure Python has screen capture permissions on macOS
   - Run as administrator on Windows if needed

3. **"AI service error"**:
   - Check your API key is valid
   - Verify the base URL and model are correct
   - Check your internet connection

### Debug Mode

To enable debug logging, set `DEBUG=true` in your `.env` file or environment variables.

### Logs

Check the Claude Desktop logs for MCP server errors:
- **Windows**: `%APPDATA%\Claude\logs\`
- **macOS**: `~/Library/Logs/Claude/`
- **Linux**: `~/.local/share/Claude/logs/`

## Advanced Configuration

### Custom AI Models

You can use different AI models by updating the environment variables:

```json
{
  "mcpServers": {
    "screenmonitormcp": {
      "command": "python",
      "args": ["-m", "src.screenmonitormcp.mcp_main"],
      "env": {
        "OPENAI_API_KEY": "your-api-key",
        "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
        "OPENAI_MODEL": "anthropic/claude-3.5-sonnet"
      }
    }
  }
}
```

### Multiple Monitors

The server supports multiple monitors. Use the `monitor` parameter to specify which monitor to capture (0 for primary, 1 for secondary, etc.).

### Region Capture

You can capture specific regions of the screen:

```json
{
  "region": {
    "x": 100,
    "y": 100,
    "width": 800,
    "height": 600
  }
}
```

## Support

For issues and support:
- GitHub Issues: https://github.com/inkbytefo/ScreenMonitorMCP/issues
- Documentation: https://github.com/inkbytefo/ScreenMonitorMCP#readme