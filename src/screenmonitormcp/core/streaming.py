"""
Streaming Management for ScreenMonitorMCP v2 with Memory Integration.

This module provides a comprehensive `StreamManager` for handling real-time
streaming operations. It includes features for creating, starting, and stopping
streams, as well as memory integration for periodic analysis of stream data.
"""

import asyncio
import base64
import uuid
from typing import AsyncGenerator, Dict, Any, Optional, Callable
from datetime import datetime
import structlog
from .screen_capture import ScreenCapture

try:
    from .memory_system import memory_system
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from ai.memory_system import memory_system

try:
    from .ai_service import ai_service
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from ai.ai_service import ai_service

try:
    from ..models.responses import StreamingEvent
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from models.responses import StreamingEvent
try:
    from ..server.config import config
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from server.config import config
from .connection import connection_manager

logger = structlog.get_logger()


class StreamManager:
    """
    Manages real-time streaming operations with memory integration.

    This class handles the lifecycle of data streams, including creation,
    starting, stopping, and pausing. It also integrates with the memory
    system to periodically analyze and store stream data.

    Attributes:
        _active_streams (Dict[str, Dict[str, Any]]): A dictionary of active streams.
        _stream_tasks (Dict[str, asyncio.Task]): A dictionary of running stream tasks.
        _lock (asyncio.Lock): A lock for thread-safe operations.
        _memory_enabled (bool): A flag to enable or disable memory integration.
        _analysis_interval (int): The interval for analyzing stream frames.
    """
    
    def __init__(self):
        """Initializes the StreamManager."""
        self._active_streams: Dict[str, Dict[str, Any]] = {}
        self._stream_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._memory_enabled = True
        self._analysis_interval = 5  # Analyze every 5 frames
        self._frame_counter = {}  # Track frames per stream
        self._resource_monitor = {
            "max_memory_mb": 512,  # Maximum memory usage in MB
            "max_streams": 5,      # Maximum concurrent streams
            "frame_buffer_size": 10,  # Maximum frames to buffer
            "cleanup_interval": 300,  # Cleanup interval in seconds
            "last_cleanup": datetime.now()
        }
        self._frame_buffers: Dict[str, list] = {}  # Frame buffers per stream
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_resource_monitor()
        
    async def create_stream(
        self,
        stream_type: str,
        fps: int = None,
        quality: int = None,
        format: str = "jpeg",
        filters: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Creates a new data stream.

        Args:
            stream_type: The type of the stream (e.g., 'screen', 'analysis').
            fps: The frames per second for the stream.
            quality: The quality of the stream data (e.g., image quality).
            format: The format of the stream data (e.g., 'jpeg', 'png').
            filters: Optional filters to apply to the stream data.

        Returns:
            The unique ID of the newly created stream.
        """
        stream_id = str(uuid.uuid4())
        
        # Apply defaults from config
        fps = fps or config.default_stream_fps
        quality = quality or config.default_stream_quality
        
        # Validate limits
        fps = min(fps, config.max_stream_fps)
        quality = min(quality, config.max_stream_quality)
        
        # Store original quality for adaptive adjustment
        original_quality = quality
        
        async with self._lock:
            # Check concurrent stream limit
            if len(self._active_streams) >= config.max_concurrent_streams:
                raise ValueError(f"Maximum concurrent streams limit reached: {config.max_concurrent_streams}")
            
            stream_config = {
                "stream_id": stream_id,
                "stream_type": stream_type,
                "fps": fps,
                "quality": quality,
                "original_quality": original_quality,
                "format": format,
                "filters": filters or {},
                "created_at": datetime.now(),
                "status": "created",
                "sequence": 0,
                "performance_stats": {
                    "avg_broadcast_time": 0.0,
                    "failed_sends": 0,
                    "quality_adjustments": 0
                },
                "memory_config": {
                    "enabled": self._memory_enabled,
                    "analysis_interval": self._analysis_interval,
                    "last_analysis_sequence": 0,
                    "total_analyses": 0
                }
            }
            
            self._active_streams[stream_id] = stream_config
            self._frame_counter[stream_id] = 0
            
            logger.info(
                "Stream created with safety controls and memory integration",
                stream_id=stream_id,
                stream_type=stream_type,
                fps=fps,
                quality=quality,
                max_concurrent=config.max_concurrent_streams,
                memory_enabled=self._memory_enabled
            )
            
            return stream_id
    
    async def start_stream(
        self,
        stream_id: str,
        data_generator: Callable[[str], AsyncGenerator[Dict[str, Any], None]]
    ) -> bool:
        """
        Starts a stream with a given data generator.

        Args:
            stream_id: The ID of the stream to start.
            data_generator: An async generator function that yields stream data.

        Returns:
            True if the stream was started successfully, False otherwise.
        """
        async with self._lock:
            if stream_id not in self._active_streams:
                return False
            
            if stream_id in self._stream_tasks:
                logger.warning("Stream already running", stream_id=stream_id)
                return False
            
            task = asyncio.create_task(
                self._run_stream(stream_id, data_generator)
            )
            self._stream_tasks[stream_id] = task
            
            logger.info("Stream started", stream_id=stream_id)
            return True
    
    async def stop_stream(self, stream_id: str) -> bool:
        """
        Stops a running stream.

        Args:
            stream_id: The ID of the stream to stop.

        Returns:
            True if the stream was stopped successfully, False otherwise.
        """
        async with self._lock:
            if stream_id not in self._active_streams:
                return False
            
            # Cancel the stream task
            if stream_id in self._stream_tasks:
                task = self._stream_tasks.pop(stream_id)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Update stream status
            self._active_streams[stream_id]["status"] = "stopped"
            
            logger.info("Stream stopped", stream_id=stream_id)
            return True
    
    async def pause_stream(self, stream_id: str) -> bool:
        """
        Pauses a running stream.

        Args:
            stream_id: The ID of the stream to pause.

        Returns:
            True if the stream was paused successfully, False otherwise.
        """
        async with self._lock:
            if stream_id not in self._active_streams:
                return False
            
            self._active_streams[stream_id]["status"] = "paused"
            logger.info("Stream paused", stream_id=stream_id)
            return True
    
    async def resume_stream(self, stream_id: str) -> bool:
        """
        Resumes a paused stream.

        Args:
            stream_id: The ID of the stream to resume.

        Returns:
            True if the stream was resumed successfully, False otherwise.
        """
        async with self._lock:
            if stream_id not in self._active_streams:
                return False
            
            self._active_streams[stream_id]["status"] = "active"
            logger.info("Stream resumed", stream_id=stream_id)
            return True
    
    async def _run_stream(
        self,
        stream_id: str,
        data_generator: Callable[[str], AsyncGenerator[Dict[str, Any], None]]
    ):
        """
        The main loop for running a stream.

        This method iterates over the data generator, processes each frame for
        memory analysis, and broadcasts the data to subscribed clients.

        Args:
            stream_id: The ID of the stream to run.
            data_generator: The async generator that provides stream data.
        """
        try:
            stream_config = self._active_streams[stream_id]
            fps = stream_config["fps"]
            interval = 1.0 / fps
            failed_sends = 0
            adaptive_quality = stream_config["quality"]
            
            async for data in data_generator(stream_id):
                if stream_config["status"] != "active":
                    break
                
                # Check frame size and apply limits
                frame_size = len(data.get("image_data", "")) if "image_data" in data else 0
                if frame_size > config.max_frame_size:
                    logger.warning(
                        "Frame size exceeds limit, skipping",
                        stream_id=stream_id,
                        frame_size=frame_size,
                        limit=config.max_frame_size
                    )
                    continue
                
                # Create streaming event
                event = StreamingEvent(
                    event_type="data",
                    data=data,
                    stream_id=stream_id,
                    sequence=stream_config["sequence"]
                )
                
                # Memory system integration - analyze frames periodically
                await self._process_frame_for_memory(
                    stream_id, data, stream_config
                )
                
                # Broadcast to all WebSocket connections
                broadcast_data = {
                    "type": "stream_data",
                    "stream_id": stream_id,
                    "sequence": event.sequence,
                    "timestamp": event.timestamp.isoformat(),
                    "data": data,
                    "adaptive_quality": adaptive_quality
                }
                
                # Measure broadcast time for backpressure detection
                start_time = asyncio.get_event_loop().time()
                sent_count = await connection_manager.broadcast_to_stream(
                    stream_id, broadcast_data
                )
                broadcast_time = asyncio.get_event_loop().time() - start_time
                
                # Adaptive quality control based on performance
                if broadcast_time > 0.5:  # If broadcast takes more than 500ms
                    failed_sends += 1
                    if failed_sends > 3 and adaptive_quality > 30:
                        adaptive_quality = max(30, adaptive_quality - 10)
                        logger.info(
                            "Reducing quality due to slow broadcast",
                            stream_id=stream_id,
                            new_quality=adaptive_quality
                        )
                        # Update stream config
                        stream_config["quality"] = adaptive_quality
                else:
                    failed_sends = max(0, failed_sends - 1)
                    # Gradually increase quality if performance is good
                    if failed_sends == 0 and adaptive_quality < stream_config.get("original_quality", 80):
                        adaptive_quality = min(stream_config.get("original_quality", 80), adaptive_quality + 5)
                        stream_config["quality"] = adaptive_quality
                
                logger.debug(
                    "Broadcasted stream data",
                    stream_id=stream_id,
                    sequence=event.sequence,
                    connections_sent=sent_count,
                    broadcast_time=broadcast_time,
                    adaptive_quality=adaptive_quality
                )
                
                stream_config["sequence"] += 1
                
                # Dynamic interval adjustment based on performance
                adjusted_interval = interval
                if broadcast_time > interval:
                    adjusted_interval = max(interval, broadcast_time * 1.2)
                
                await asyncio.sleep(adjusted_interval)
                
        except asyncio.CancelledError:
            logger.info("Stream cancelled", stream_id=stream_id)
        except Exception as e:
            logger.error(
                "Stream error",
                stream_id=stream_id,
                error=str(e),
                exc_info=True
            )
        finally:
            # Clean up
            if stream_id in self._active_streams:
                self._active_streams[stream_id]["status"] = "stopped"
            if stream_id in self._frame_counter:
                del self._frame_counter[stream_id]
    
    async def _process_frame_for_memory(
        self, 
        stream_id: str, 
        data: Dict[str, Any], 
        stream_config: Dict[str, Any]
    ):
        """
        Processes a stream frame for memory integration.

        This method checks if it's time to analyze a frame based on the
        configured interval and schedules an asynchronous analysis task.

        Args:
            stream_id: The ID of the stream.
            data: The stream data for the frame.
            stream_config: The configuration of the stream.
        """
        try:
            if not stream_config.get("memory_config", {}).get("enabled", False):
                return
            
            # Increment frame counter
            self._frame_counter[stream_id] = self._frame_counter.get(stream_id, 0) + 1
            current_frame = self._frame_counter[stream_id]
            
            memory_config = stream_config["memory_config"]
            analysis_interval = memory_config["analysis_interval"]
            
            # Check if it's time to analyze
            if current_frame % analysis_interval == 0:
                # Extract image data
                image_data = data.get("image_data")
                if not image_data:
                    return
                
                # Prepare analysis prompt
                analysis_prompt = f"Analyze this screen capture from stream {stream_id} at sequence {stream_config['sequence']}. Describe what you see, any changes from previous frames, and notable activities."
                
                # Perform AI analysis asynchronously (don't block streaming)
                asyncio.create_task(self._analyze_and_store(
                    stream_id=stream_id,
                    image_data=image_data,
                    prompt=analysis_prompt,
                    sequence=stream_config["sequence"],
                    frame_number=current_frame
                ))
                
                # Update memory config
                memory_config["last_analysis_sequence"] = stream_config["sequence"]
                memory_config["total_analyses"] += 1
                
                logger.debug(
                    "Scheduled frame analysis for memory",
                    stream_id=stream_id,
                    sequence=stream_config["sequence"],
                    frame_number=current_frame,
                    total_analyses=memory_config["total_analyses"]
                )
                
        except Exception as e:
            logger.error(
                "Error processing frame for memory",
                stream_id=stream_id,
                error=str(e),
                exc_info=True
            )
    
    async def _analyze_and_store(
        self,
        stream_id: str,
        image_data: str,
        prompt: str,
        sequence: int,
        frame_number: int
    ):
        """
        Analyzes a frame with AI and stores the result in the memory system.

        Args:
            stream_id: The ID of the stream.
            image_data: The base64 encoded image data.
            prompt: The prompt for the AI analysis.
            sequence: The sequence number of the frame.
            frame_number: The frame number within the stream.
        """
        try:
            # Perform AI analysis
            analysis_result = await ai_service.analyze_image(
                image_base64=image_data,
                prompt=prompt,
                detail_level="low",  # Use low detail for streaming to save resources
                store_in_memory=True,
                stream_id=stream_id,
                sequence=sequence,
                tags=["streaming", "auto_analysis", f"frame_{frame_number}"]
            )
            
            logger.info(
                "Frame analyzed and stored in memory",
                stream_id=stream_id,
                sequence=sequence,
                frame_number=frame_number,
                analysis_length=len(analysis_result.get("analysis", ""))
            )
            
        except Exception as e:
            logger.error(
                "Error analyzing frame for memory",
                stream_id=stream_id,
                sequence=sequence,
                frame_number=frame_number,
                error=str(e),
                exc_info=True
            )
    
    async def get_stream_info(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves information about a specific stream.

        Args:
            stream_id: The ID of the stream.

        Returns:
            A dictionary with the stream information, or None if not found.
        """
        return self._active_streams.get(stream_id)
    
    async def get_active_streams(self) -> Dict[str, Dict[str, Any]]:
        """
        Retrieves all active streams.

        Returns:
            A dictionary of all active streams.
        """
        return self._active_streams.copy()
    
    def list_streams(self) -> Dict[str, Dict[str, Any]]:
        """
        Retrieves all active streams (synchronous version).

        Returns:
            A dictionary of all active streams.
        """
        return self._active_streams.copy()
    
    def is_running(self) -> bool:
        """
        Checks if the stream manager is running.

        Returns:
            True if there are active streams, False otherwise.
        """
        return len(self._active_streams) > 0

    def enable_memory_system(self, enabled: bool = True):
        """
        Enables or disables memory system integration for streams.

        Args:
            enabled: A flag to enable or disable memory integration.
        """
        self._memory_enabled = enabled
        logger.info(f"Memory system {'enabled' if enabled else 'disabled'} for streaming")
    
    def set_analysis_interval(self, interval: int):
        """
        Sets the analysis interval for the memory system.

        Args:
            interval: The interval for analyzing stream frames.
        """
        if interval < 1:
            raise ValueError("Analysis interval must be at least 1")
        self._analysis_interval = interval
        logger.info(f"Analysis interval set to {interval} frames")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Retrieves memory system statistics for all streams.

        Returns:
            A dictionary with memory system statistics.
        """
        stats = {
            "memory_enabled": self._memory_enabled,
            "analysis_interval": self._analysis_interval,
            "streams": {}
        }
        
        for stream_id, stream_config in self._active_streams.items():
            memory_config = stream_config.get("memory_config", {})
            stats["streams"][stream_id] = {
                "enabled": memory_config.get("enabled", False),
                "total_analyses": memory_config.get("total_analyses", 0),
                "last_analysis_sequence": memory_config.get("last_analysis_sequence", 0),
                "current_frame": self._frame_counter.get(stream_id, 0)
            }
        
        return stats
    
    async def cleanup(self):
        """Cleans up all streams and resources."""
        async with self._lock:
            # Stop resource monitor
            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            
            # Stop all active streams
            for stream_id in list(self._active_streams.keys()):
                await self.stop_stream(stream_id)
            
            # Cancel all tasks
            for task in self._stream_tasks.values():
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Clear frame buffers
            self._frame_buffers.clear()
            
            self._active_streams.clear()
            self._stream_tasks.clear()
            self._frame_counter.clear()
            logger.info("All streams cleaned up")
    
    def _start_resource_monitor(self):
        """Starts the resource monitoring task."""
        try:
            # Check if there's a running event loop
            loop = asyncio.get_running_loop()
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._resource_monitor_loop())
        except RuntimeError:
            # No running event loop, skip for now
            # The task will be started when the event loop is available
            pass
    
    async def _resource_monitor_loop(self):
        """The main resource monitoring loop."""
        try:
            while True:
                await asyncio.sleep(self._resource_monitor["cleanup_interval"])
                await self._perform_resource_cleanup()
        except asyncio.CancelledError:
            logger.info("Resource monitor stopped")
            raise
        except Exception as e:
            logger.error(f"Resource monitor error: {e}")
    
    async def _perform_resource_cleanup(self):
        """Performs resource cleanup operations."""
        try:
            import psutil
            import os
            
            # Get current memory usage
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / (1024 * 1024)
            
            logger.debug(f"Current memory usage: {memory_mb:.2f} MB")
            
            # Check if memory usage is too high
            if memory_mb > self._resource_monitor["max_memory_mb"]:
                logger.warning(f"High memory usage detected: {memory_mb:.2f} MB")
                await self._emergency_cleanup()
            
            # Clean up frame buffers
            await self._cleanup_frame_buffers()
            
            # Update last cleanup time
            self._resource_monitor["last_cleanup"] = datetime.now()
            
        except ImportError:
            # psutil not available, perform basic cleanup
            await self._cleanup_frame_buffers()
        except Exception as e:
            logger.error(f"Resource cleanup failed: {e}")
    
    async def _emergency_cleanup(self):
        """Performs emergency cleanup when memory usage is too high."""
        logger.warning("Performing emergency cleanup due to high memory usage")
        
        async with self._lock:
            # Stop streams with lowest priority (oldest first)
            streams_by_age = sorted(
                self._active_streams.items(),
                key=lambda x: x[1].get("created_at", datetime.now())
            )
            
            # Stop half of the streams
            streams_to_stop = len(streams_by_age) // 2
            for i in range(streams_to_stop):
                stream_id, _ = streams_by_age[i]
                logger.warning(f"Emergency stopping stream: {stream_id}")
                await self.stop_stream(stream_id)
    
    async def _cleanup_frame_buffers(self):
        """Cleans up frame buffers to prevent memory leaks."""
        async with self._lock:
            for stream_id, buffer in self._frame_buffers.items():
                # Keep only the most recent frames
                max_frames = self._resource_monitor["frame_buffer_size"]
                if len(buffer) > max_frames:
                    # Remove oldest frames
                    frames_to_remove = len(buffer) - max_frames
                    del buffer[:frames_to_remove]
                    logger.debug(f"Cleaned {frames_to_remove} frames from buffer for stream {stream_id}")
    
    def get_resource_stats(self) -> Dict[str, Any]:
        """
        Retrieves current resource usage statistics.

        Returns:
            A dictionary with resource usage statistics.
        """
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            return {
                "memory_usage_mb": round(memory_info.rss / (1024 * 1024), 2),
                "memory_limit_mb": self._resource_monitor["max_memory_mb"],
                "active_streams": len(self._active_streams),
                "max_streams": self._resource_monitor["max_streams"],
                "frame_buffers": {stream_id: len(buffer) for stream_id, buffer in self._frame_buffers.items()},
                "last_cleanup": self._resource_monitor["last_cleanup"].isoformat(),
                "cleanup_interval": self._resource_monitor["cleanup_interval"]
            }
        except ImportError:
            return {
                "memory_usage_mb": "unavailable (psutil not installed)",
                "memory_limit_mb": self._resource_monitor["max_memory_mb"],
                "active_streams": len(self._active_streams),
                "max_streams": self._resource_monitor["max_streams"],
                "frame_buffers": {stream_id: len(buffer) for stream_id, buffer in self._frame_buffers.items()},
                "last_cleanup": self._resource_monitor["last_cleanup"].isoformat(),
                "cleanup_interval": self._resource_monitor["cleanup_interval"]
            }
    
    def configure_resource_limits(
        self,
        max_memory_mb: Optional[int] = None,
        max_streams: Optional[int] = None,
        frame_buffer_size: Optional[int] = None,
        cleanup_interval: Optional[int] = None
    ):
        """
        Configures the resource limits for the stream manager.

        Args:
            max_memory_mb: The maximum memory usage in MB.
            max_streams: The maximum number of concurrent streams.
            frame_buffer_size: The maximum number of frames to buffer per stream.
            cleanup_interval: The cleanup interval in seconds.
        """
        if max_memory_mb is not None:
            self._resource_monitor["max_memory_mb"] = max_memory_mb
        if max_streams is not None:
            self._resource_monitor["max_streams"] = max_streams
        if frame_buffer_size is not None:
            self._resource_monitor["frame_buffer_size"] = frame_buffer_size
        if cleanup_interval is not None:
            self._resource_monitor["cleanup_interval"] = cleanup_interval
        
        logger.info(f"Resource limits updated: {self._resource_monitor}")


class ScreenStreamer:
    """
    Handles screen capture and streaming operations with dual-channel support.

    This class provides methods for capturing the screen with different quality
    settings and for generating a continuous stream of screen data.
    """
    
    def __init__(self):
        """Initializes the ScreenStreamer."""
        self.screen_capture = ScreenCapture()
        self._executor = None
        

    
    async def capture_screen(
        self,
        monitor: int = 1,
        region: Optional[Dict[str, int]] = None,
        quality: int = 80,
        format: str = "jpeg",
        resolution: Optional[tuple] = None,
        return_bytes: bool = False
    ) -> Dict[str, Any]:
        """
        Captures the screen and returns the image data.

        This method uses the unified screen capture service to capture the screen
        with the specified quality and format. It can return the image data as
        a base64 encoded string or as raw bytes.

        Args:
            monitor: The monitor to capture.
            region: An optional region to capture.
            quality: The image quality.
            format: The image format.
            resolution: An optional resolution to resize the image to.
            return_bytes: A flag to return raw bytes instead of base64.

        Returns:
            A dictionary with the screen capture data.
        """
        try:
            # Use unified screen capture service based on quality and format requirements
            if quality >= 80 and format.lower() == "png":
                # High quality capture
                capture_result = await self.screen_capture.capture_hq_frame(format=format)
            else:
                # Preview/low quality capture with resolution adjustment
                capture_result = await self.screen_capture.capture_preview_frame(
                    quality=quality, 
                    resolution=resolution
                )
            
            if not capture_result.get("success"):
                return {
                    "success": False,
                    "message": capture_result.get("error", "Screen capture failed")
                }
            
            img_bytes = capture_result["image_bytes"]
            
            # Check if compressed size exceeds limits and re-compress if needed
            max_size_bytes = getattr(config, 'max_frame_size', 2 * 1024 * 1024)
            
            if len(img_bytes) > max_size_bytes:
                # Re-compress with lower quality if size is too large
                reduced_quality = max(20, quality - 20)
                capture_result = await self.screen_capture.capture_preview_frame(
                    quality=reduced_quality,
                    resolution=resolution
                )
                
                if capture_result.get("success"):
                    img_bytes = capture_result["image_bytes"]
                    logger.info(
                        "Reduced image quality due to size limit",
                        original_quality=quality,
                        reduced_quality=reduced_quality,
                        final_size=len(img_bytes)
                    )
            
            result = {
                "success": True,
                "width": capture_result["width"],
                "height": capture_result["height"],
                "format": capture_result["format"].upper(),
                "size": capture_result["file_size"],
                "monitor": monitor,
                "timestamp": datetime.now().isoformat()
            }
            
            if return_bytes:
                result["image_bytes"] = img_bytes
            else:
                # Encode to base64 for backward compatibility
                img_base64 = base64.b64encode(img_bytes).decode()
                result["image_data"] = img_base64
            
            return result
            
        except Exception as e:
            logger.error("Screen capture failed", error=str(e), exc_info=True)
            return {"success": False, "message": str(e)}
    
    async def stream_screen(
        self,
        stream_id: str,
        fps: int = 2,
        quality: int = 80,
        monitor: int = 1,
        region: Optional[Dict[str, int]] = None,
        resolution: Optional[tuple] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generates a continuous stream of screen data.

        Args:
            stream_id: The ID of the stream.
            fps: The frames per second for the stream.
            quality: The image quality.
            monitor: The monitor to capture.
            region: An optional region to capture.
            resolution: An optional resolution to resize the image to.

        Yields:
            A dictionary with the screen capture data for each frame.
        """
        try:
            while True:
                # Capture screen
                screen_data = await self.capture_screen(
                    monitor=monitor,
                    region=region,
                    quality=quality,
                    resolution=resolution
                )
                
                yield screen_data
                
                # Control FPS
                await asyncio.sleep(1.0 / fps)
                
        except asyncio.CancelledError:
            logger.info("Screen stream cancelled", stream_id=stream_id)
            raise
        except Exception as e:
            logger.error("Screen stream error", error=str(e), exc_info=True)
            raise


# Stream analysis generator moved from ai_vision.py
async def stream_analysis_generator(
    stream_id: str,
    interval_seconds: int = 10,
    prompt: str = "Analyze this screen content and provide a detailed summary of what's happening.",
    model: str = None,
    max_tokens: int = 300
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generates a continuous AI analysis of screen content.
    
    Args:
        stream_id: The unique identifier for the stream.
        interval_seconds: The analysis interval in seconds.
        prompt: The prompt for the AI analysis.
        model: The AI model to use.
        max_tokens: The maximum number of tokens in the response.
        
    Yields:
        A dictionary with the analysis results for each interval.
    """
    if not ai_service.is_configured():
        yield {
            "type": "error",
            "data": {"error": "AI service not configured"},
            "timestamp": datetime.now().isoformat(),
            "stream_id": stream_id
        }
        return
    
    sequence = 0
    
    try:
        while True:
            try:
                # Capture screen using unified screen streamer
                capture_result = await screen_streamer.capture_screen(
                    monitor=1,
                    quality=80,
                    format="jpeg"
                )
                
                if not capture_result.get("success") or not capture_result.get("image_data"):
                    yield {
                        "type": "error",
                        "data": {"error": "Failed to capture screen - no image data"},
                        "timestamp": datetime.now().isoformat(),
                        "stream_id": stream_id,
                        "sequence": sequence
                    }
                    await asyncio.sleep(interval_seconds)
                    continue
                
                # Analyze with unified AI service
                image_base64 = capture_result["image_data"]
                analysis_result = await ai_service.analyze_image(
                    image_base64=image_base64,
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    store_in_memory=True,
                    stream_id=stream_id,
                    sequence=sequence,
                    tags=["stream_analysis", "continuous_monitoring"]
                )
                
                if analysis_result.get("success"):
                    # Create response data
                    response_data = {
                        "analysis": analysis_result["response"],
                        "model": analysis_result["model"],
                        "prompt": prompt,
                        "capture_info": {
                            "timestamp": capture_result["timestamp"],
                            "monitor": capture_result["monitor"],
                            "width": capture_result["width"],
                            "height": capture_result["height"],
                            "format": capture_result["format"],
                            "size": capture_result["size"]
                        },
                        "usage": analysis_result.get("usage", {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0
                        }),
                        "memory_id": analysis_result.get("memory_id")
                    }
                    
                    yield {
                        "type": "analysis",
                        "data": response_data,
                        "timestamp": datetime.now().isoformat(),
                        "stream_id": stream_id,
                        "sequence": sequence
                    }
                else:
                    yield {
                        "type": "error",
                        "data": {"error": analysis_result.get("error", "Analysis failed")},
                        "timestamp": datetime.now().isoformat(),
                        "stream_id": stream_id,
                        "sequence": sequence
                    }
                
                sequence += 1
                
            except Exception as e:
                logger.error(f"Error in stream analysis: {e}")
                yield {
                    "type": "error",
                    "data": {"error": str(e)},
                    "timestamp": datetime.now().isoformat(),
                    "stream_id": stream_id,
                    "sequence": sequence
                }
            
            await asyncio.sleep(interval_seconds)
            
    except asyncio.CancelledError:
        logger.info(f"Stream analysis cancelled for stream: {stream_id}")
        yield {
            "type": "status",
            "data": {"status": "stopped"},
            "timestamp": datetime.now().isoformat(),
            "stream_id": stream_id,
            "sequence": sequence
        }
    except Exception as e:
        logger.error(f"Fatal error in stream analysis: {e}")
        yield {
            "type": "error",
            "data": {"error": f"Fatal error: {str(e)}"},
            "timestamp": datetime.now().isoformat(),
            "stream_id": stream_id,
            "sequence": sequence
        }


# Global instances
stream_manager = StreamManager()
screen_streamer = ScreenStreamer()
