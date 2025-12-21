"""Streaming management for ScreenMonitorMCP v2 with memory integration."""

import asyncio
import base64
import uuid
from typing import AsyncGenerator, Dict, Any, Optional, Callable
from datetime import datetime
import structlog
import logging
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

# Configure logging for debugging stream issues
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = structlog.get_logger()


class StreamManager:
    """Manages real-time streaming operations with memory integration."""
    
    def __init__(self):
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
        self.screen_capture = ScreenCapture()  # Initialize screen capture instance
        self._screen_streamer = None  # Will be initialized lazily
        self._pending_analyses: Dict[str, set] = {}  # Track pending analysis tasks per stream
        self._analysis_metadata: Dict[str, Dict[str, Any]] = {}  # Track analysis timing per stream
        self._stream_debug: Dict[str, list] = {}  # Debug log for each stream
        self._start_resource_monitor()
        
    async def create_stream(
        self,
        stream_type: str,
        fps: int = None,
        quality: int = None,
        format: str = "jpeg",
        filters: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new stream with enhanced safety controls."""
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
            self._pending_analyses[stream_id] = set()  # Initialize pending analysis tracking
            self._analysis_metadata[stream_id] = {
                "last_analyzed_sequence": 0,
                "last_analysis_time": None,
                "total_analyses_completed": 0,
                "total_analyses_failed": 0
            }
            self._stream_debug[stream_id] = []  # Initialize debug log

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
        """Start a stream with a data generator."""
        async with self._lock:
            if stream_id not in self._active_streams:
                logger.error(f"Cannot start stream {stream_id}: stream not found in active_streams")
                return False

            if stream_id in self._stream_tasks:
                logger.warning("Stream already running", stream_id=stream_id)
                return False

            # Set status to active so the stream loop will run
            self._active_streams[stream_id]["status"] = "active"
            logger.info(f"Set stream {stream_id} status to 'active'")

            task = asyncio.create_task(
                self._run_stream(stream_id, data_generator)
            )
            self._stream_tasks[stream_id] = task

            # Add callback to log if task fails
            def log_task_exception(t):
                try:
                    exception = t.exception()
                    if exception:
                        logger.error(f"Stream task failed for {stream_id}: {exception}", exc_info=exception)
                except asyncio.CancelledError:
                    pass
            task.add_done_callback(log_task_exception)

            logger.info("Stream started", stream_id=stream_id)
            return True

    def _debug_log(self, stream_id: str, message: str):
        """Add a debug message to the stream's debug log."""
        if stream_id in self._stream_debug:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._stream_debug[stream_id].append(f"{timestamp}: {message}")
            # Keep only last 50 messages
            if len(self._stream_debug[stream_id]) > 50:
                self._stream_debug[stream_id] = self._stream_debug[stream_id][-50:]

    async def start_stream_direct(
        self,
        stream_id: str,
        quality: int = 80,
        monitor: int = 0
    ) -> bool:
        """Start a stream directly with built-in screen capture generator.

        This is a simpler alternative to start_stream that doesn't require
        passing a custom generator function.
        """
        self._debug_log(stream_id, f"start_stream_direct called with quality={quality}, monitor={monitor}")

        # Initialize ScreenStreamer if needed
        if self._screen_streamer is None:
            self._screen_streamer = ScreenStreamer()
            self._debug_log(stream_id, "start_stream_direct: initialized ScreenStreamer")

        async def direct_generator(sid: str):
            """Direct screen capture generator."""
            self._debug_log(sid, "direct_generator: function called")
            logger.info(f"direct_generator starting for stream {sid}, monitor={monitor}, quality={quality}")
            frame_count = 0
            try:
                self._debug_log(sid, "direct_generator: entering while loop")
                while True:
                    # Capture screen using ScreenStreamer
                    self._debug_log(sid, f"direct_generator: about to capture frame {frame_count + 1}")
                    screen_data = await self._screen_streamer.capture_screen(
                        monitor=monitor,
                        region=None,
                        quality=quality,
                        resolution=None
                    )
                    self._debug_log(sid, f"direct_generator: captured frame {frame_count + 1}, success={screen_data.get('success')}")

                    frame_count += 1
                    if frame_count % 10 == 0:
                        logger.info(f"direct_generator: captured {frame_count} frames for {sid}")

                    yield screen_data

            except asyncio.CancelledError:
                self._debug_log(sid, f"direct_generator: cancelled after {frame_count} frames")
                logger.info(f"direct_generator cancelled after {frame_count} frames for {sid}")
                raise
            except Exception as e:
                self._debug_log(sid, f"direct_generator: exception after {frame_count} frames: {type(e).__name__}: {str(e)}")
                logger.error(f"direct_generator error after {frame_count} frames for {sid}: {e}", exc_info=True)
                raise

        self._debug_log(stream_id, "start_stream_direct: about to call start_stream")
        result = await self.start_stream(stream_id, direct_generator)
        self._debug_log(stream_id, f"start_stream_direct: start_stream returned {result}")
        return result

    async def stop_stream(self, stream_id: str) -> bool:
        """Stop a stream."""
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
        """Pause a stream."""
        async with self._lock:
            if stream_id not in self._active_streams:
                return False
            
            self._active_streams[stream_id]["status"] = "paused"
            logger.info("Stream paused", stream_id=stream_id)
            return True
    
    async def resume_stream(self, stream_id: str) -> bool:
        """Resume a paused stream."""
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
        """Run the stream loop with adaptive quality and backpressure control."""
        self._debug_log(stream_id, "_run_stream: task started")
        logger.info(f"_run_stream starting for {stream_id}")
        try:
            stream_config = self._active_streams[stream_id]
            fps = stream_config["fps"]
            interval = 1.0 / fps
            failed_sends = 0
            adaptive_quality = stream_config["quality"]

            self._debug_log(stream_id, f"_run_stream: calling data_generator, status={stream_config['status']}")
            logger.info(f"_run_stream: calling data_generator for {stream_id}")
            frame_num = 0
            async for data in data_generator(stream_id):
                frame_num += 1
                self._debug_log(stream_id, f"_run_stream: received frame {frame_num} from generator")
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
                
                # Broadcast to all WebSocket connections (skip if no connections to save resources)
                sent_count = 0
                broadcast_time = 0.0

                # Only broadcast if there are active WebSocket connections
                if connection_manager and hasattr(connection_manager, '_active_streams'):
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
        """Process frame for memory system integration."""
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
                task = asyncio.create_task(self._analyze_and_store(
                    stream_id=stream_id,
                    image_data=image_data,
                    prompt=analysis_prompt,
                    sequence=stream_config["sequence"],
                    frame_number=current_frame
                ))

                # Track pending analysis
                if stream_id in self._pending_analyses:
                    self._pending_analyses[stream_id].add(task)
                    # Auto-cleanup when task completes
                    task.add_done_callback(lambda t: self._pending_analyses.get(stream_id, set()).discard(t))

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
        """Analyze frame with AI and store in memory system."""
        try:
            # Check if AI service is configured before attempting analysis
            if not ai_service or not ai_service.is_configured():
                logger.debug(
                    "Skipping frame analysis - AI service not configured",
                    stream_id=stream_id,
                    sequence=sequence
                )
                return

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

            # Update analysis metadata on success
            if stream_id in self._analysis_metadata:
                self._analysis_metadata[stream_id]["last_analyzed_sequence"] = sequence
                self._analysis_metadata[stream_id]["last_analysis_time"] = datetime.now()
                self._analysis_metadata[stream_id]["total_analyses_completed"] += 1

            logger.info(
                "Frame analyzed and stored in memory",
                stream_id=stream_id,
                sequence=sequence,
                frame_number=frame_number,
                analysis_length=len(analysis_result.get("analysis", ""))
            )

        except Exception as e:
            # Update analysis metadata on failure
            if stream_id in self._analysis_metadata:
                self._analysis_metadata[stream_id]["total_analyses_failed"] += 1

            logger.error(
                "Error analyzing frame for memory",
                stream_id=stream_id,
                sequence=sequence,
                frame_number=frame_number,
                error=str(e),
                exc_info=True
            )
    
    async def get_stream_info(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """Get stream information."""
        return self._active_streams.get(stream_id)

    def get_stream_diagnostics(self, stream_id: str) -> Dict[str, Any]:
        """Get detailed diagnostics for a stream including why it might have stopped."""
        if stream_id not in self._active_streams:
            return {"error": "Stream not found"}

        stream_config = self._active_streams[stream_id]

        # Check if task exists and its state
        task_info = "no task"
        if stream_id in self._stream_tasks:
            task = self._stream_tasks[stream_id]
            if task.done():
                try:
                    exception = task.exception()
                    if exception:
                        task_info = f"task failed with exception: {type(exception).__name__}: {str(exception)}"
                    else:
                        task_info = "task completed normally (shouldn't happen - has while True loop)"
                except asyncio.CancelledError:
                    task_info = "task was cancelled"
            else:
                task_info = "task is running"

        # Get debug log
        debug_log = self._stream_debug.get(stream_id, [])

        return {
            "stream_id": stream_id,
            "status": stream_config.get("status", "unknown"),
            "sequence": stream_config.get("sequence", 0),
            "task_state": task_info,
            "fps": stream_config.get("fps"),
            "created_at": stream_config.get("created_at"),
            "memory_enabled": stream_config.get("memory_config", {}).get("enabled"),
            "frame_counter": self._frame_counter.get(stream_id, 0),
            "debug_log": debug_log
        }

    def get_analysis_metadata(self, stream_id: str) -> Dict[str, Any]:
        """Get analysis status metadata for a stream.

        Returns information about analysis lag, pending analyses, and data freshness.
        """
        if stream_id not in self._active_streams:
            return {"error": "Stream not found"}

        stream_config = self._active_streams[stream_id]
        metadata = self._analysis_metadata.get(stream_id, {})
        pending_count = len(self._pending_analyses.get(stream_id, set()))

        current_sequence = stream_config.get("sequence", 0)
        last_analyzed = metadata.get("last_analyzed_sequence", 0)
        last_analysis_time = metadata.get("last_analysis_time")

        # Calculate analysis lag
        sequence_lag = current_sequence - last_analyzed
        fps = stream_config.get("fps", 10)
        time_lag_seconds = sequence_lag / fps if fps > 0 else 0

        return {
            "stream_id": stream_id,
            "current_sequence": current_sequence,
            "last_analyzed_sequence": last_analyzed,
            "pending_analyses": pending_count,
            "sequence_lag": sequence_lag,
            "time_lag_seconds": round(time_lag_seconds, 2),
            "last_analysis_time": last_analysis_time.isoformat() if last_analysis_time else None,
            "analyses_completed": metadata.get("total_analyses_completed", 0),
            "analyses_failed": metadata.get("total_analyses_failed", 0),
            "data_freshness": "fresh" if time_lag_seconds < 1.0 else "stale" if time_lag_seconds < 3.0 else "very_stale"
        }
    
    async def get_active_streams(self) -> Dict[str, Dict[str, Any]]:
        """Get all active streams."""
        return self._active_streams.copy()
    
    def list_streams(self) -> Dict[str, Dict[str, Any]]:
        """Get all active streams (sync version)."""
        return self._active_streams.copy()
    
    def is_running(self) -> bool:
        """Check if stream manager is running."""
        return len(self._active_streams) > 0

    def enable_memory_system(self, enabled: bool = True):
        """Enable or disable memory system integration."""
        self._memory_enabled = enabled
        logger.info(f"Memory system {'enabled' if enabled else 'disabled'} for streaming")
    
    def set_analysis_interval(self, interval: int):
        """Set the analysis interval for memory system."""
        if interval < 1:
            raise ValueError("Analysis interval must be at least 1")
        self._analysis_interval = interval
        logger.info(f"Analysis interval set to {interval} frames")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory system statistics for all streams."""
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
        """Clean up all streams and resources."""
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
        """Start the resource monitoring task."""
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
        """Resource monitoring loop."""
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
        """Perform resource cleanup operations."""
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
        """Emergency cleanup when memory usage is too high."""
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
        """Clean up frame buffers to prevent memory leaks."""
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
        """Get current resource usage statistics."""
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
        """Configure resource limits."""
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
    """Handles screen capture and streaming operations with dual-channel support."""
    
    def __init__(self):
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
        """Capture screen and return as base64 using unified screen capture service."""
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
        quality: int = 80,
        monitor: int = 1,
        region: Optional[Dict[str, int]] = None,
        resolution: Optional[tuple] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Generate screen stream data.

        Note: FPS is controlled by _run_stream(), not here. This just generates
        frames as fast as requested.
        """
        logger.info(f"stream_screen generator starting for {stream_id}, monitor={monitor}, quality={quality}")
        try:
            frame_count = 0
            while True:
                # Capture screen
                screen_data = await self.capture_screen(
                    monitor=monitor,
                    region=region,
                    quality=quality,
                    resolution=resolution
                )

                frame_count += 1
                if frame_count % 10 == 0:
                    logger.info(f"stream_screen: captured {frame_count} frames for {stream_id}")

                yield screen_data

                # FPS control is handled by _run_stream(), not here

        except asyncio.CancelledError:
            logger.info(f"Screen stream cancelled after {frame_count} frames", stream_id=stream_id)
            raise
        except Exception as e:
            logger.error(f"Screen stream error after {frame_count} frames: {str(e)}", error=str(e), exc_info=True)
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
    Generate continuous AI analysis of screen content.
    
    Args:
        stream_id: Unique stream identifier
        interval_seconds: Analysis interval in seconds
        prompt: Analysis prompt for AI
        model: AI model to use
        max_tokens: Maximum tokens in response
        
    Yields:
        Analysis results as dictionaries
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
