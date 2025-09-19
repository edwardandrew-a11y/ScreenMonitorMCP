"""Memory-related tools for ScreenMonitorMCP."""

import json
from typing import Optional
from mcp.server.fastmcp import FastMCP
import logging
from .ai_service import ai_service
from .streaming import stream_manager
from .memory_system import memory_system

logger = logging.getLogger(__name__)

def register_memory_tools(mcp: FastMCP):
    @mcp.tool()
    async def analyze_scene_from_memory(
        query: str,
        stream_id: Optional[str] = None,
        time_range_minutes: int = 30,
        limit: int = 10
    ) -> str:
        """Analyze scene based on stored memory data"""
        try:
            result = await ai_service.analyze_scene_from_memory(
                query=query,
                stream_id=stream_id,
                time_range_minutes=time_range_minutes,
                limit=limit
            )
            return json.dumps({
                "success": True,
                "data": result
            })
        except Exception as e:
            logger.error(f"Failed to analyze scene from memory: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "analyze_scene_from_memory_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def query_memory(
        query: str,
        stream_id: Optional[str] = None,
        time_range_minutes: int = 60,
        limit: int = 20
    ) -> str:
        """Query the memory system for stored analysis data"""
        try:
            result = await ai_service.query_memory_direct(
                query=query,
                stream_id=stream_id,
                time_range_minutes=time_range_minutes,
                limit=limit
            )
            return json.dumps({
                "success": True,
                "data": result
            })
        except Exception as e:
            logger.error(f"Failed to query memory: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "query_memory_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def get_memory_statistics() -> str:
        """Get memory system statistics and health information"""
        try:
            stats = await ai_service.get_memory_statistics()
            return json.dumps({
                "success": True,
                "data": stats
            })
        except Exception as e:
            logger.error(f"Failed to get memory statistics: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "get_memory_statistics_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    def get_stream_memory_stats() -> str:
        """Get memory system statistics for streaming"""
        try:
            stats = stream_manager.get_memory_stats()
            return json.dumps({
                "success": True,
                "data": stats
            })
        except Exception as e:
            logger.error(f"Failed to get stream memory stats: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "get_stream_memory_stats_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    def configure_stream_memory(
        enabled: bool = True,
        analysis_interval: int = 5
    ) -> str:
        """Configure memory system for streaming"""
        try:
            stream_manager.enable_memory_system(enabled)
            if analysis_interval > 0:
                stream_manager.set_analysis_interval(analysis_interval)

            return json.dumps({
                "success": True,
                "data": {
                    "enabled": enabled,
                    "analysis_interval": analysis_interval
                }
            })
        except Exception as e:
            logger.error(f"Failed to configure stream memory: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "configure_stream_memory_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def get_memory_usage() -> str:
        """Get detailed memory usage and performance metrics"""
        try:
            usage_stats = await memory_system.get_memory_usage()

            if "error" in usage_stats:
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "get_memory_usage_failed",
                        "message": usage_stats['error']
                    }
                })

            return json.dumps({
                "success": True,
                "data": usage_stats
            })
        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "get_memory_usage_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def configure_auto_cleanup(
        enabled: bool,
        max_age_days: int = 7
    ) -> str:
        """Configure automatic memory cleanup settings"""
        try:
            result = await memory_system.configure_auto_cleanup(enabled, max_age_days)

            if result.get("success"):
                return json.dumps({
                    "success": True,
                    "data": result
                })
            else:
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "configure_auto_cleanup_failed",
                        "message": result.get('error', 'Unknown error occurred')
                    }
                })

        except Exception as e:
             logger.error(f"Failed to configure auto cleanup: {e}")
             return json.dumps({
                 "success": False,
                 "error": {
                     "code": "configure_auto_cleanup_failed",
                     "message": str(e)
                 }
             })

    @mcp.tool()
    def get_stream_resource_stats() -> str:
        """Get streaming resource usage statistics"""
        try:
            stats = stream_manager.get_resource_stats()
            return json.dumps({
                "success": True,
                "data": stats
            })
        except Exception as e:
            logger.error(f"Failed to get stream resource stats: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "get_stream_resource_stats_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    def configure_stream_resources(
        max_memory_mb: Optional[int] = None,
        max_streams: Optional[int] = None,
        frame_buffer_size: Optional[int] = None,
        cleanup_interval: Optional[int] = None
    ) -> str:
        """Configure streaming resource limits"""
        try:
            stream_manager.configure_resource_limits(
                max_memory_mb=max_memory_mb,
                max_streams=max_streams,
                frame_buffer_size=frame_buffer_size,
                cleanup_interval=cleanup_interval
            )

            config_items = {}
            if max_memory_mb is not None:
                config_items["max_memory_mb"] = max_memory_mb
            if max_streams is not None:
                config_items["max_streams"] = max_streams
            if frame_buffer_size is not None:
                config_items["frame_buffer_size"] = frame_buffer_size
            if cleanup_interval is not None:
                config_items["cleanup_interval"] = cleanup_interval

            return json.dumps({
                "success": True,
                "data": config_items
            })
        except Exception as e:
            logger.error(f"Failed to configure stream resources: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "configure_stream_resources_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def get_database_pool_stats() -> str:
        """Get database connection pool statistics"""
        try:
            if not memory_system._db_pool:
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "db_pool_not_initialized",
                        "message": "Database pool not initialized"
                    }
                })

            stats = await memory_system._db_pool.get_stats()

            return json.dumps({
                "success": True,
                "data": {
                    "total_connections": stats.total_connections,
                    "active_connections": stats.active_connections,
                    "idle_connections": stats.idle_connections,
                    "total_queries": stats.total_queries,
                    "failed_queries": stats.failed_queries,
                    "average_query_time": f"{stats.average_query_time:.4f}s",
                    "pool_created": stats.pool_created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    "last_cleanup": stats.last_cleanup.strftime('%Y-%m-%d %H:%M:%S') if stats.last_cleanup else "Never"
                }
            })
        except Exception as e:
            logger.error(f"Failed to get database pool stats: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "get_database_pool_stats_failed",
                    "message": str(e)
                }
            })

    @mcp.tool()
    async def database_pool_health_check() -> str:
        """Perform database pool health check"""
        try:
            if not memory_system._db_pool:
                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "db_pool_not_initialized",
                        "message": "Database pool not initialized"
                    }
                })

            health = await memory_system._db_pool.health_check()

            return json.dumps({
                "success": True,
                "data": health
            })
        except Exception as e:
            logger.error(f"Failed to perform database health check: {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "code": "database_pool_health_check_failed",
                    "message": str(e)
                }
            })
