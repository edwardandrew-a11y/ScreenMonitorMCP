"""
Command handler for MCP v3 WebSocket protocol implementing a dual-channel architecture.

This module is responsible for processing WebSocket commands, managing client connections,
and handling different communication channels for JSON control messages and binary data streams.
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional
import structlog
from fastapi import WebSocket, WebSocketDisconnect

from ..models.requests import WebSocketCommand, CommandType
from ..models.responses import WebSocketResponse, ResponseType
from .connection import connection_manager
from .streaming import screen_streamer
from .screen_capture import ScreenCapture

logger = structlog.get_logger()


class CommandHandler:
    """
    Handles MCP v3 WebSocket commands with a dual-channel architecture.

    This class processes incoming commands from WebSocket clients, manages active
    preview streams, and coordinates responses. It separates control messages
    (JSON) from high-throughput data streams (binary), optimizing performance
    for real-time screen monitoring.

    Attributes:
        _active_preview_tasks (Dict[str, asyncio.Task]): A dictionary mapping
            connection IDs to their active preview streaming tasks.
        _connection_streams (Dict[str, str]): A dictionary mapping connection
            IDs to their associated stream IDs.
        screen_capture (ScreenCapture): An instance of the screen capture service.
    """
    
    def __init__(self):
        """Initializes the CommandHandler."""
        self._active_preview_tasks: Dict[str, asyncio.Task] = {}
        self._connection_streams: Dict[str, str] = {}  # connection_id -> stream_id
        self.screen_capture = ScreenCapture()
        
    async def handle_command(
        self, 
        websocket: WebSocket, 
        connection_id: str, 
        command: WebSocketCommand
    ) -> Optional[WebSocketResponse]:
        """
        Handle an incoming WebSocket command.

        This method acts as the main entry point for processing commands received
        from a WebSocket client. It routes commands to the appropriate handler
        based on their type and ensures proper error handling and logging.

        Args:
            websocket: The WebSocket connection instance.
            connection_id: The unique identifier for the WebSocket connection.
            command: The command received from the client.

        Returns:
            An optional WebSocketResponse to be sent back to the client. Returns
            None if no JSON response is required (e.g., for binary data requests).
        """
        start_time = time.time()
        
        try:
            logger.info(
                "Processing command",
                connection_id=connection_id,
                command=command.command,
                stream_id=command.stream_id
            )
            
            if command.command == CommandType.SUBSCRIBE_PREVIEW:
                return await self._handle_subscribe_preview(websocket, connection_id, command)
            
            elif command.command == CommandType.REQUEST_HQ_FRAME:
                # Handle HQ frame request asynchronously (no JSON response needed)
                asyncio.create_task(
                    self._handle_request_hq_frame(websocket, connection_id, command)
                )
                return None
            
            elif command.command == CommandType.UNSUBSCRIBE:
                return await self._handle_unsubscribe(websocket, connection_id, command)
            
            elif command.command == CommandType.PING:
                return WebSocketResponse(
                    type=ResponseType.PONG,
                    command=command.command,
                    success=True,
                    message="pong",
                    request_id=command.request_id
                )
            
            else:
                return WebSocketResponse(
                    type=ResponseType.ERROR,
                    command=command.command,
                    success=False,
                    message=f"Unknown command: {command.command}",
                    request_id=command.request_id
                )
                
        except Exception as e:
            logger.error(
                "Command handling failed",
                connection_id=connection_id,
                command=command.command,
                error=str(e),
                exc_info=True
            )
            
            return WebSocketResponse(
                type=ResponseType.ERROR,
                command=command.command,
                success=False,
                message=f"Command execution failed: {str(e)}",
                request_id=command.request_id
            )
        
        finally:
            duration = (time.time() - start_time) * 1000
            logger.info(
                "Command processed",
                connection_id=connection_id,
                command=command.command,
                duration_ms=duration
            )
    
    async def _handle_subscribe_preview(
        self, 
        websocket: WebSocket, 
        connection_id: str, 
        command: WebSocketCommand
    ) -> WebSocketResponse:
        """
        Handle the 'subscribe_preview' command.

        This method starts a continuous, low-quality preview stream over the
        WebSocket's binary channel. It cancels any existing preview task for the
        connection before starting a new one.

        Args:
            websocket: The WebSocket connection instance.
            connection_id: The unique identifier for the WebSocket connection.
            command: The 'subscribe_preview' command from the client.

        Returns:
            A WebSocketResponse acknowledging the subscription.
        """
        try:
            stream_id = command.stream_id or f"preview_{connection_id}"
            
            # Stop existing preview task if any
            if connection_id in self._active_preview_tasks:
                self._active_preview_tasks[connection_id].cancel()
                try:
                    await self._active_preview_tasks[connection_id]
                except asyncio.CancelledError:
                    pass
                del self._active_preview_tasks[connection_id]
                
            # Store stream mapping
            self._connection_streams[connection_id] = stream_id
                
            # Start new preview stream task
            task = asyncio.create_task(
                self._stream_preview_frames(websocket, connection_id, stream_id)
            )
            self._active_preview_tasks[connection_id] = task
            
            logger.info(
                "Preview stream started",
                connection_id=connection_id,
                stream_id=stream_id
            )
            
            return WebSocketResponse(
                type=ResponseType.ACK,
                command=command.command,
                success=True,
                message=f"Preview stream started",
                stream_id=stream_id,
                request_id=command.request_id
            )
            
        except Exception as e:
            logger.error("Subscribe preview failed", error=str(e), exc_info=True)
            return WebSocketResponse(
                type=ResponseType.ERROR,
                command=command.command,
                success=False,
                message=f"Failed to start preview: {str(e)}",
                request_id=command.request_id
            )
    
    async def _handle_request_hq_frame(
        self, 
        websocket: WebSocket, 
        connection_id: str, 
        command: WebSocketCommand
    ) -> None:
        """
        Handle the 'request_hq_frame' command.

        This method captures a single high-quality PNG frame and sends it over
        the WebSocket's binary channel. No JSON response is sent on success.

        Args:
            websocket: The WebSocket connection instance.
            connection_id: The unique identifier for the WebSocket connection.
            command: The 'request_hq_frame' command from the client.
        """
        try:
            logger.info(
                "Processing HQ frame request",
                connection_id=connection_id,
                request_id=command.request_id
            )
            
            # Capture high-quality frame using unified screen capture service
            capture_result = await self.screen_capture.capture_hq_frame(format="png")
            
            if capture_result["success"]:
                # Send binary data directly via websocket.send_bytes()
                await websocket.send_bytes(capture_result["image_bytes"])
                
                logger.info(
                    "HQ frame sent",
                    connection_id=connection_id,
                    request_id=command.request_id,
                    file_size=capture_result["file_size"],
                    format=capture_result["format"]
                )
            else:
                # Send error response as JSON
                error_response = WebSocketResponse(
                    type=ResponseType.ERROR,
                    command=command.command,
                    success=False,
                    message=capture_result.get("error", "HQ frame capture failed"),
                    request_id=command.request_id
                )
                await websocket.send_text(error_response.model_dump_json())
                
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected during HQ frame request", connection_id=connection_id)
        except Exception as e:
            logger.error(
                "HQ frame request failed",
                connection_id=connection_id,
                request_id=command.request_id,
                error=str(e),
                exc_info=True
            )
            
            # Send error response
            try:
                error_response = WebSocketResponse(
                    type=ResponseType.ERROR,
                    command=command.command,
                    success=False,
                    message=f"HQ frame capture failed: {str(e)}",
                    request_id=command.request_id
                )
                await websocket.send_text(error_response.model_dump_json())
            except Exception as send_error:
                logger.error("Failed to send error response", error=str(send_error))
    

    
    async def _handle_unsubscribe(
        self, 
        websocket: WebSocket, 
        connection_id: str, 
        command: WebSocketCommand
    ) -> WebSocketResponse:
        """
        Handle the 'unsubscribe' command.

        This method stops the active preview stream for the given connection.

        Args:
            websocket: The WebSocket connection instance.
            connection_id: The unique identifier for the WebSocket connection.
            command: The 'unsubscribe' command from the client.

        Returns:
            A WebSocketResponse acknowledging the unsubscription.
        """
        try:
            # Cancel preview task if exists
            if connection_id in self._active_preview_tasks:
                self._active_preview_tasks[connection_id].cancel()
                try:
                    await self._active_preview_tasks[connection_id]
                except asyncio.CancelledError:
                    pass
                del self._active_preview_tasks[connection_id]
                
            # Remove stream mapping
            if connection_id in self._connection_streams:
                stream_id = self._connection_streams[connection_id]
                del self._connection_streams[connection_id]
            else:
                stream_id = command.stream_id
            
            logger.info(
                "Unsubscribed from preview",
                connection_id=connection_id,
                stream_id=stream_id
            )
            
            return WebSocketResponse(
                type=ResponseType.ACK,
                command=command.command,
                success=True,
                message="Unsubscribed from preview stream",
                stream_id=stream_id,
                request_id=command.request_id
            )
            
        except Exception as e:
            logger.error("Unsubscribe failed", error=str(e), exc_info=True)
            return WebSocketResponse(
                type=ResponseType.ERROR,
                command=command.command,
                success=False,
                message=f"Unsubscribe failed: {str(e)}",
                request_id=command.request_id
            )
    
    async def _stream_preview_frames(
        self, 
        websocket: WebSocket, 
        connection_id: str, 
        stream_id: str
    ) -> None:
        """
        Stream low-quality preview frames continuously.

        This method runs in a loop, capturing low-quality JPEG frames and
        sending them over the WebSocket's binary channel to provide a real-time
        preview of the screen.

        Args:
            websocket: The WebSocket connection instance.
            connection_id: The unique identifier for the WebSocket connection.
            stream_id: The identifier for the preview stream.
        """
        frame_count = 0
        fps = 2  # Low FPS for preview (configurable)
        frame_interval = 1.0 / fps
        
        # Preview stream settings: low quality, low resolution
        preview_quality = 40  # ~40% JPEG quality
        preview_resolution = (800, 450)  # Low resolution
        
        logger.info(
            "Starting preview stream",
            connection_id=connection_id,
            stream_id=stream_id,
            fps=fps,
            quality=preview_quality,
            resolution=preview_resolution
        )
        
        try:
            while True:
                start_time = time.time()
                
                try:
                    # Capture low-quality frame using unified screen capture service
                    frame_data = await self.screen_capture.capture_preview_frame(
                        quality=preview_quality,
                        resolution=preview_resolution
                    )
                    
                    if frame_data.get("success"):
                        # Send binary data directly via websocket.send_bytes()
                        await websocket.send_bytes(frame_data["image_bytes"])
                        
                        frame_count += 1
                        
                        if frame_count % 30 == 0:  # Log every 30 frames
                            logger.debug(
                                "Preview frames sent",
                                connection_id=connection_id,
                                stream_id=stream_id,
                                frame_count=frame_count,
                                frame_size=frame_data["file_size"]
                            )
                    else:
                        logger.warning(
                            "Preview frame capture failed",
                            connection_id=connection_id,
                            error=frame_data.get("error", "Unknown error")
                        )
                    
                    # Maintain FPS
                    elapsed = time.time() - start_time
                    sleep_time = max(0, frame_interval - elapsed)
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                        
                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected during preview stream", connection_id=connection_id)
                    break
                except Exception as frame_error:
                    logger.error(
                        "Frame capture error",
                        connection_id=connection_id,
                        stream_id=stream_id,
                        error=str(frame_error)
                    )
                    await asyncio.sleep(1)  # Wait before retry
                    
        except asyncio.CancelledError:
            logger.info(
                "Preview stream cancelled",
                connection_id=connection_id,
                stream_id=stream_id,
                frames_sent=frame_count
            )
            raise
        except Exception as e:
            logger.error(
                "Preview stream error",
                connection_id=connection_id,
                stream_id=stream_id,
                error=str(e),
                exc_info=True
            )
        finally:
            logger.info(
                "Preview stream ended",
                connection_id=connection_id,
                stream_id=stream_id,
                total_frames=frame_count
            )
    

    
    async def cleanup_connection(self, connection_id: str) -> None:
        """
        Clean up resources for a disconnected connection.

        This method is called when a WebSocket connection is closed. It ensures
        that any active tasks for the connection are cancelled and that any
        associated resources are released.

        Args:
            connection_id: The unique identifier of the disconnected connection.
        """
        # Cancel and remove preview task if exists
        if connection_id in self._active_preview_tasks:
            task = self._active_preview_tasks[connection_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self._active_preview_tasks[connection_id]
        
        # Remove connection stream mapping
        if connection_id in self._connection_streams:
            del self._connection_streams[connection_id]
        
        # Connection cleanup completed
        
        logger.info("Connection cleanup completed", connection_id=connection_id)


# Global command handler instance
command_handler = CommandHandler()