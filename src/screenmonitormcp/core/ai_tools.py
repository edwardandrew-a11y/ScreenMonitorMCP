"""AI-related tools for ScreenMonitorMCP."""

import json
from typing import Optional
from mcp.server.fastmcp import FastMCP
import logging
from .ai_service import ai_service
from .screen_capture import screen_capture

logger = logging.getLogger(__name__)

def register_ai_tools(mcp: FastMCP):
    @mcp.tool()
    async def analyze_screen(
        query: str,
        monitor: int = 0,
        detail_level: str = "high"
    ) -> str:
        """Analyze the current screen content using AI vision"""
        try:
            if not ai_service.is_available():
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "ai_service_unavailable",
                        "message": "AI service is not available. Please configure your AI provider."
                    }
                })

            capture_result = await screen_capture.capture_screen(monitor)
            if not capture_result.get("success"):
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "screen_capture_failed",
                        "message": f"Failed to capture screen - {capture_result.get('message', 'Unknown error')}"
                    }
                })

            image_base64 = capture_result["image_data"]
            result = await ai_service.analyze_image(image_base64, query)

            if result.get("success"):
                return json.dumps({
                    "success": True,
                    "data": result.get("response", "No analysis available")
                })
            else:
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "analysis_failed",
                        "message": result.get('error', 'Unknown error occurred')
                    }
                })
        except Exception as e:
            logger.error(f"Screen analysis failed: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "unexpected_error",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def analyze_image(
        image_base64: str,
        query: str
    ) -> str:
        """Analyze an image using AI vision."""
        try:
            if not ai_service.is_available():
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "ai_service_unavailable",
                        "message": "AI service is not available. Please configure your AI provider."
                    }
                })

            result = await ai_service.analyze_image(image_base64, query)

            if result.get("success"):
                return json.dumps({
                    "success": True,
                    "data": result.get("response", "No analysis available")
                })
            else:
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "analysis_failed",
                        "message": result.get('error', 'Unknown error occurred')
                    }
                })
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "unexpected_error",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def chat_completion(
        messages: list,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """Generate chat completion using AI models"""
        try:
            if not ai_service.is_available():
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "ai_service_unavailable",
                        "message": "AI service is not available. Please configure your AI provider."
                    }
                })

            result = await ai_service.chat_completion(messages, model, max_tokens, temperature)

            if result.get("success"):
                return json.dumps({
                    "success": True,
                    "data": result.get("response", "No response available")
                })
            else:
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "chat_completion_failed",
                        "message": result.get('error', 'Unknown error occurred')
                    }
                })
        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "unexpected_error",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def list_ai_models() -> str:
        """List available AI models from the configured provider"""
        try:
            if not ai_service.is_available():
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "ai_service_unavailable",
                        "message": "AI service is not available. Please configure your AI provider."
                    }
                })

            result = await ai_service.list_models()

            if result.get("success"):
                models = result.get("models", [])
                return json.dumps({
                    "success": True,
                    "data": models
                })
            else:
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "list_models_failed",
                        "message": result.get('error', 'Unknown error occurred')
                    }
                })
        except Exception as e:
            logger.error(f"Failed to list AI models: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "unexpected_error",
                    "message": str(e)
                }
            })

    @mcp.tool()
    def get_ai_status() -> str:
        """Get AI service configuration status"""
        try:
            status = ai_service.get_status()
            return json.dumps({
                "success": True,
                "data": status
            })
        except Exception as e:
            logger.error(f"Failed to get AI status: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "unexpected_error",
                    "message": str(e)
                }
            })
