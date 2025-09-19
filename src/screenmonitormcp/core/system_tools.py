"""System-related tools for ScreenMonitorMCP."""

import json
from mcp.server.fastmcp import FastMCP
import logging
from datetime import datetime
from .ai_service import ai_service
from .screen_capture import screen_capture
from .performance_monitor import performance_monitor
from .streaming import stream_manager

logger = logging.getLogger(__name__)

def register_system_tools(mcp: FastMCP):
    @mcp.tool()
    async def capture_screen(
        monitor: int = 0,
        format: str = "png"
    ) -> str:
        """Capture the screen and return the image as a base64 string."""
        try:
            result = await screen_capture.capture_screen(monitor=monitor, format=format)
            if result["success"]:
                return json.dumps({
                    "success": True,
                    "data": result["image_data"]
                })
            else:
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "capture_screen_failed",
                        "message": result["message"]
                    }
                })
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "capture_screen_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    def get_performance_metrics() -> str:
        """Get detailed performance metrics and system health"""
        try:
            metrics = performance_monitor.get_metrics()
            return json.dumps({
                "success": True,
                "data": metrics
            })
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "get_performance_metrics_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    def get_system_status() -> str:
        """Get overall system status and health information"""
        try:
            status = {
                "timestamp": datetime.now().isoformat(),
                "ai_service": ai_service.is_available(),
                "screen_capture": screen_capture.is_available(),
                "performance_monitor": performance_monitor.is_running(),
                "stream_manager": stream_manager.is_running()
            }
            return json.dumps({
                "success": True,
                "data": status
            })
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "get_system_status_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def detect_ui_elements(
        monitor: int = 0
    ) -> str:
        """Detect and classify UI elements in the current screen"""
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
            result = await ai_service.detect_ui_elements(image_base64)

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
            logger.error(f"UI elements detection failed: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "unexpected_error",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def assess_system_performance(
        monitor: int = 0
    ) -> str:
        """Assess system performance indicators visible on screen"""
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
            result = await ai_service.assess_system_performance(image_base64)

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
            logger.error(f"System performance assessment failed: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "unexpected_error",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def detect_anomalies(
        monitor: int = 0,
        baseline_description: str = ""
    ) -> str:
        """Detect visual anomalies and unusual patterns in the screen"""
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
            result = await ai_service.detect_anomalies(image_base64, baseline_description)

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
            logger.error(f"Anomaly detection failed: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "unexpected_error",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def generate_monitoring_report(
        monitor: int = 0,
        context: str = ""
    ) -> str:
        """Generate comprehensive monitoring report from screen analysis"""
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
            result = await ai_service.generate_monitoring_report(image_base64, context)

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
            logger.error(f"Monitoring report generation failed: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "unexpected_error",
                    "message": str(e)
                }
            })
