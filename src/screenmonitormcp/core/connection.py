"""
Connection Management for ScreenMonitorMCP v2.

This module provides a robust ConnectionManager for handling client connections,
managing subscriptions to data streams, and broadcasting messages. It is designed
to be thread-safe and scalable for managing multiple concurrent WebSocket connections.
"""

import asyncio
import uuid
from typing import Dict, Set, Optional, Any
from datetime import datetime, timedelta
import structlog
from dataclasses import dataclass, field

logger = structlog.get_logger()


@dataclass
class ConnectionInfo:
    """
    Represents information about an active client connection.

    This data class stores details about each connected client, including their
    IP address, user agent, connection time, and activity status.

    Attributes:
        connection_id (str): A unique identifier for the connection.
        client_ip (str): The client's IP address.
        user_agent (Optional[str]): The client's user agent string.
        connected_at (datetime): The timestamp when the connection was established.
        last_activity (datetime): The timestamp of the last known activity.
        stream_types (Set[str]): A set of stream IDs the client is subscribed to.
        metadata (Dict[str, Any]): A dictionary for storing custom connection metadata.
        websocket (Any): The WebSocket object for real-time communication.
    """
    
    connection_id: str
    client_ip: str
    user_agent: Optional[str]
    connected_at: datetime
    last_activity: datetime
    stream_types: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    websocket: Any = None  # WebSocket object for real-time communication
    
    @property
    def duration(self) -> timedelta:
        """Calculates the total duration of the connection."""
        return datetime.now() - self.connected_at
    
    @property
    def idle_time(self) -> timedelta:
        """Calculates the time since the last activity."""
        return datetime.now() - self.last_activity


class ConnectionManager:
    """
    Manages active WebSocket connections and their stream subscriptions.

    This class provides a centralized way to handle client connections, including
    adding, removing, and tracking activity. It also manages subscriptions to
    different data streams, allowing for targeted message broadcasting.

    Attributes:
        _connections (Dict[str, ConnectionInfo]): A dictionary of active connections.
        _active_streams (Dict[str, Set[str]]): A dictionary mapping stream IDs
            to sets of connection IDs.
        _lock (asyncio.Lock): A lock to ensure thread-safe operations.
    """
    
    def __init__(self):
        """Initializes the ConnectionManager."""
        self._connections: Dict[str, ConnectionInfo] = {}
        self._active_streams: Dict[str, Set[str]] = {}  # stream_id -> connection_ids
        self._lock = asyncio.Lock()
        
    async def add_connection(
        self,
        client_ip: str,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Adds a new client connection to the manager.

        Args:
            client_ip: The IP address of the client.
            user_agent: The user agent string of the client.
            metadata: Custom metadata to associate with the connection.

        Returns:
            The unique ID of the newly created connection.
        """
        async with self._lock:
            connection_id = str(uuid.uuid4())
            connection = ConnectionInfo(
                connection_id=connection_id,
                client_ip=client_ip,
                user_agent=user_agent,
                connected_at=datetime.now(),
                last_activity=datetime.now(),
                metadata=metadata or {}
            )
            self._connections[connection_id] = connection
            logger.info(
                "Connection added",
                connection_id=connection_id,
                client_ip=client_ip,
                total_connections=len(self._connections)
            )
            return connection_id
    
    async def remove_connection(self, connection_id: str) -> bool:
        """
        Removes a client connection from the manager.

        Args:
            connection_id: The ID of the connection to remove.

        Returns:
            True if the connection was removed successfully, False otherwise.
        """
        async with self._lock:
            if connection_id in self._connections:
                connection = self._connections.pop(connection_id)
                
                # Remove from all streams
                for stream_id, connections in self._active_streams.items():
                    connections.discard(connection_id)
                
                logger.info(
                    "Connection removed",
                    connection_id=connection_id,
                    duration=connection.duration,
                    total_connections=len(self._connections)
                )
                return True
            return False
    
    async def update_activity(self, connection_id: str) -> bool:
        """
        Updates the last activity time for a connection.

        Args:
            connection_id: The ID of the connection to update.

        Returns:
            True if the activity time was updated, False otherwise.
        """
        async with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id].last_activity = datetime.now()
                return True
            return False
    
    async def add_to_stream(self, connection_id: str, stream_id: str) -> bool:
        """
        Subscribes a connection to a data stream.

        Args:
            connection_id: The ID of the connection.
            stream_id: The ID of the stream to subscribe to.

        Returns:
            True if the subscription was successful, False otherwise.
        """
        async with self._lock:
            if connection_id not in self._connections:
                return False
            
            if stream_id not in self._active_streams:
                self._active_streams[stream_id] = set()
            
            self._active_streams[stream_id].add(connection_id)
            self._connections[connection_id].stream_types.add(stream_id)
            
            logger.info(
                "Connection added to stream",
                connection_id=connection_id,
                stream_id=stream_id,
                stream_connections=len(self._active_streams[stream_id])
            )
            return True
    
    async def remove_from_stream(self, connection_id: str, stream_id: str) -> bool:
        """
        Unsubscribes a connection from a data stream.

        Args:
            connection_id: The ID of the connection.
            stream_id: The ID of the stream to unsubscribe from.

        Returns:
            True if the unsubscription was successful, False otherwise.
        """
        async with self._lock:
            if stream_id in self._active_streams:
                self._active_streams[stream_id].discard(connection_id)
                
                if connection_id in self._connections:
                    self._connections[connection_id].stream_types.discard(stream_id)
                
                # Clean up empty streams
                if not self._active_streams[stream_id]:
                    del self._active_streams[stream_id]
                
                logger.info(
                    "Connection removed from stream",
                    connection_id=connection_id,
                    stream_id=stream_id
                )
                return True
            return False
    
    async def get_connection(self, connection_id: str) -> Optional[ConnectionInfo]:
        """
        Retrieves information about a specific connection.

        Args:
            connection_id: The ID of the connection to retrieve.

        Returns:
            A ConnectionInfo object if the connection exists, None otherwise.
        """
        return self._connections.get(connection_id)
    
    async def get_active_connections(self) -> Dict[str, ConnectionInfo]:
        """
        Retrieves all active connections.

        Returns:
            A dictionary of all active connections.
        """
        return self._connections.copy()
    
    async def get_stream_connections(self, stream_id: str) -> Set[str]:
        """
        Retrieves all connections subscribed to a specific stream.

        Args:
            stream_id: The ID of the stream.

        Returns:
            A set of connection IDs subscribed to the stream.
        """
        return self._active_streams.get(stream_id, set()).copy()
    
    async def get_active_streams(self) -> Dict[str, int]:
        """
        Retrieves active streams and their connection counts.

        Returns:
            A dictionary mapping stream IDs to the number of connections.
        """
        return {
            stream_id: len(connections)
            for stream_id, connections in self._active_streams.items()
        }
    
    async def cleanup_idle_connections(self, max_idle_time: timedelta) -> int:
        """
        Removes connections that have been idle for too long.

        Args:
            max_idle_time: The maximum allowed idle time.

        Returns:
            The number of connections that were removed.
        """
        async with self._lock:
            now = datetime.now()
            to_remove = []
            
            for connection_id, connection in self._connections.items():
                if connection.idle_time > max_idle_time:
                    to_remove.append(connection_id)
            
            for connection_id in to_remove:
                await self.remove_connection(connection_id)
            
            if to_remove:
                logger.info(
                    "Cleaned up idle connections",
                    count=len(to_remove),
                    max_idle_seconds=max_idle_time.total_seconds()
                )
            
            return len(to_remove)
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Retrieves statistics about the connection manager.

        Returns:
            A dictionary containing connection and stream statistics.
        """
        async with self._lock:
            return {
                "total_connections": len(self._connections),
                "active_streams": len(self._active_streams),
                "connections_by_stream": {
                    stream_id: len(connections)
                    for stream_id, connections in self._active_streams.items()
                },
                "connection_details": {
                    conn_id: {
                        "client_ip": conn.client_ip,
                        "duration": conn.duration.total_seconds(),
                        "idle_time": conn.idle_time.total_seconds(),
                        "streams": list(conn.stream_types)
                    }
                    for conn_id, conn in self._connections.items()
                }
            }

    async def broadcast_to_stream(self, stream_id: str, data: Dict[str, Any]) -> int:
        """
        Broadcasts data to all connections subscribed to a stream.

        This method sends a JSON payload to all WebSockets in a given stream,
        with timeouts and error handling for each connection.

        Args:
            stream_id: The ID of the stream to broadcast to.
            data: The JSON-serializable data to send.

        Returns:
            The number of connections the data was successfully sent to.
        """
        sent_count = 0
        failed_connections = []
        
        async with self._lock:
            if stream_id not in self._active_streams:
                return 0
            
            connections = self._active_streams[stream_id].copy()
        
        # Check data size before sending
        try:
            import json
            data_size = len(json.dumps(data).encode('utf-8'))
            if data_size > getattr(config, 'client_buffer_limit', 5 * 1024 * 1024):
                logger.warning(
                    "Data size exceeds client buffer limit",
                    stream_id=stream_id,
                    data_size=data_size,
                    limit=getattr(config, 'client_buffer_limit', 5 * 1024 * 1024)
                )
                return 0
        except Exception as e:
            logger.error("Failed to calculate data size", error=str(e))
        
        # Send to all WebSocket connections for this stream with timeout
        for connection_id in connections:
            connection = self._connections.get(connection_id)
            if connection and hasattr(connection, 'websocket'):
                try:
                    # Add timeout to prevent hanging
                    await asyncio.wait_for(
                        connection.websocket.send_json(data),
                        timeout=3.0  # 3 second timeout
                    )
                    sent_count += 1
                    # Update last activity
                    connection.last_activity = datetime.now()
                except asyncio.TimeoutError:
                    logger.warning(
                        "WebSocket send timeout",
                        connection_id=connection_id,
                        stream_id=stream_id
                    )
                    failed_connections.append(connection_id)
                except Exception as e:
                    logger.error(
                        "Failed to send data to WebSocket",
                        connection_id=connection_id,
                        stream_id=stream_id,
                        error=str(e)
                    )
                    failed_connections.append(connection_id)
        
        # Clean up failed connections
        if failed_connections:
            async with self._lock:
                for connection_id in failed_connections:
                    if connection_id in self._active_streams.get(stream_id, set()):
                        self._active_streams[stream_id].discard(connection_id)
                    # Optionally remove the connection entirely
                    if connection_id in self._connections:
                        logger.info(
                            "Removing failed connection",
                            connection_id=connection_id,
                            stream_id=stream_id
                        )
                        del self._connections[connection_id]
        
        return sent_count

    async def cleanup(self):
        """Removes all connections and clears all streams."""
        async with self._lock:
            self._connections.clear()
            self._active_streams.clear()
            logger.info("All connections and streams cleaned up.")


# Global connection manager instance
connection_manager = ConnectionManager()
