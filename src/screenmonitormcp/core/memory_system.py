"""
Memory System for ScreenMonitorMCP v2.

This module provides a persistent memory system for storing and retrieving
AI analysis results, scene context, and other relevant data. It uses an
asynchronous SQLite database pool for efficient I/O operations.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import hashlib

import aiosqlite
import structlog
from .database_pool import get_db_pool, DatabasePool

logger = structlog.get_logger(__name__)


@dataclass
class MemoryEntry:
    """
    Represents a single entry in the memory system.

    Attributes:
        id (Optional[str]): A unique identifier for the memory entry.
        timestamp (str): The timestamp of the entry in ISO format.
        entry_type (str): The type of the entry (e.g., 'analysis', 'scene').
        content (Dict[str, Any]): The main content of the entry, stored as a JSON object.
        metadata (Dict[str, Any]): Additional metadata, stored as a JSON object.
        tags (List[str]): A list of tags for categorization and searching.
        stream_id (Optional[str]): An optional identifier for the data stream.
        sequence (Optional[int]): An optional sequence number within a stream.
    """
    id: Optional[str] = None
    timestamp: str = ""
    entry_type: str = ""  # 'analysis', 'scene', 'context'
    content: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    tags: List[str] = None
    stream_id: Optional[str] = None
    sequence: Optional[int] = None
    
    def __post_init__(self):
        """Initializes default values for the memory entry."""
        if self.content is None:
            self.content = {}
        if self.metadata is None:
            self.metadata = {}
        if self.tags is None:
            self.tags = []
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.id:
            self.id = self._generate_id()
    
    def _generate_id(self) -> str:
        """Generates a unique ID for the memory entry."""
        content_str = json.dumps(self.content, sort_keys=True)
        hash_input = f"{self.timestamp}{self.entry_type}{content_str}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]


class MemorySystem:
    """
    Manages the storage and retrieval of AI analysis results and other data.

    This class provides an interface to the persistent memory system, handling
    database initialization, data storage, querying, and maintenance tasks
    like automatic cleanup of old entries.

    Attributes:
        db_path (str): The path to the SQLite database file.
        auto_cleanup (bool): A flag to enable or disable automatic cleanup.
    """
    
    def __init__(self, db_path: Optional[str] = None, auto_cleanup: bool = True):
        """
        Initializes the MemorySystem.

        Args:
            db_path: The path to the SQLite database file.
            auto_cleanup: A flag to enable or disable automatic cleanup.
        """
        self.db_path = db_path or "memory_system.db"
        self.db_path = Path(self.db_path).resolve()
        self._initialized = False
        self.auto_cleanup = auto_cleanup
        self._cleanup_task = None
        self._memory_stats = {
            "total_entries": 0,
            "cleanup_runs": 0,
            "last_cleanup": None
        }
        self._db_pool: Optional[DatabasePool] = None
        
    async def initialize(self) -> None:
        """
        Initializes the memory system and its database.

        This method sets up the database connection pool and creates the
        necessary tables and indexes if they don't already exist.
        """
        if self._initialized:
            return
            
        try:
            # Initialize database pool
            self._db_pool = get_db_pool(self.db_path)
            await self._db_pool.initialize()
            
            # Create tables and indexes
            async with self._db_pool.get_connection() as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS memory_entries (
                        id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        entry_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata TEXT,
                        tags TEXT,
                        stream_id TEXT,
                        sequence INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timestamp ON memory_entries(timestamp)
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_entry_type ON memory_entries(entry_type)
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_stream_id ON memory_entries(stream_id)
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tags ON memory_entries(tags)
                """)
                
                await db.commit()
                
            self._initialized = True
            logger.debug(f"Memory system initialized with database: {self.db_path}")
            
            # Start auto cleanup if enabled
            if self.auto_cleanup and self._cleanup_task is None:
                self._cleanup_task = asyncio.create_task(self._auto_cleanup_scheduler())
                logger.info("Auto cleanup scheduler started")
            
        except Exception as e:
            logger.error(f"Failed to initialize memory system: {e}")
            raise
    
    async def store_analysis(self, 
                           analysis_result: Dict[str, Any],
                           stream_id: Optional[str] = None,
                           sequence: Optional[int] = None,
                           tags: Optional[List[str]] = None) -> str:
        """
        Stores an AI analysis result in the memory system.

        Args:
            analysis_result: The analysis result from the AI service.
            stream_id: An optional identifier for the data stream.
            sequence: An optional sequence number within a stream.
            tags: Optional tags for categorization.

        Returns:
            The ID of the newly created memory entry.
        """
        await self.initialize()
        
        entry = MemoryEntry(
            entry_type="analysis",
            content=analysis_result,
            metadata={
                "source": "ai_analysis",
                "model": analysis_result.get("model", "unknown"),
                "prompt": analysis_result.get("prompt", ""),
                "usage": analysis_result.get("usage", {})
            },
            tags=tags or [],
            stream_id=stream_id,
            sequence=sequence
        )
        
        return await self._store_entry(entry)
    
    async def store_scene_context(self,
                                scene_description: str,
                                objects: List[str],
                                activities: List[str],
                                stream_id: Optional[str] = None,
                                sequence: Optional[int] = None) -> str:
        """
        Stores scene context information in the memory system.

        Args:
            scene_description: A description of the scene.
            objects: A list of detected objects in the scene.
            activities: A list of detected activities in the scene.
            stream_id: An optional identifier for the data stream.
            sequence: An optional sequence number within a stream.

        Returns:
            The ID of the newly created memory entry.
        """
        await self.initialize()
        
        entry = MemoryEntry(
            entry_type="scene",
            content={
                "description": scene_description,
                "objects": objects,
                "activities": activities
            },
            metadata={
                "source": "scene_analysis",
                "object_count": len(objects),
                "activity_count": len(activities)
            },
            tags=["scene", "context"],
            stream_id=stream_id,
            sequence=sequence
        )
        
        return await self._store_entry(entry)
    
    async def query_memory(self,
                         query: str,
                         entry_type: Optional[str] = None,
                         stream_id: Optional[str] = None,
                         limit: int = 10,
                         time_range: Optional[timedelta] = None) -> List[MemoryEntry]:
        """
        Queries the memory system for relevant entries.

        Args:
            query: The search query to match against content and metadata.
            entry_type: An optional filter for the entry type.
            stream_id: An optional filter for the stream ID.
            limit: The maximum number of results to return.
            time_range: An optional time range to search within.

        Returns:
            A list of matching memory entries.
        """
        await self.initialize()
        
        conditions = []
        params = []
        
        # Text search in content and metadata
        if query:
            conditions.append("(content LIKE ? OR metadata LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        
        # Filter by entry type
        if entry_type:
            conditions.append("entry_type = ?")
            params.append(entry_type)
        
        # Filter by stream ID
        if stream_id:
            conditions.append("stream_id = ?")
            params.append(stream_id)
        
        # Filter by time range
        if time_range:
            cutoff_time = (datetime.now() - time_range).isoformat()
            conditions.append("timestamp >= ?")
            params.append(cutoff_time)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query_sql = f"""
            SELECT id, timestamp, entry_type, content, metadata, tags, stream_id, sequence
            FROM memory_entries
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)
        
        try:
            async with self._db_pool.get_connection() as db:
                async with db.execute(query_sql, params) as cursor:
                    rows = await cursor.fetchall()
                    
                    entries = []
                    for row in rows:
                        entry = MemoryEntry(
                            id=row[0],
                            timestamp=row[1],
                            entry_type=row[2],
                            content=json.loads(row[3]),
                            metadata=json.loads(row[4]) if row[4] else {},
                            tags=json.loads(row[5]) if row[5] else [],
                            stream_id=row[6],
                            sequence=row[7]
                        )
                        entries.append(entry)
                    
                    return entries
                    
        except Exception as e:
            logger.error(f"Failed to query memory: {e}")
            return []
    
    async def get_recent_context(self,
                               stream_id: Optional[str] = None,
                               limit: int = 5) -> List[MemoryEntry]:
        """
        Retrieves recent context entries from the memory system.

        Args:
            stream_id: An optional filter for the stream ID.
            limit: The maximum number of entries to return.

        Returns:
            A list of recent memory entries.
        """
        return await self.query_memory(
            query="",
            stream_id=stream_id,
            limit=limit,
            time_range=timedelta(hours=1)
        )
    
    async def analyze_scene_changes(self,
                                  stream_id: str,
                                  time_window: timedelta = timedelta(minutes=5)) -> Dict[str, Any]:
        """
        Analyzes scene changes over a given time window.

        Args:
            stream_id: The ID of the stream to analyze.
            time_window: The time window for the analysis.

        Returns:
            A dictionary with the analysis of scene changes.
        """
        entries = await self.query_memory(
            query="",
            entry_type="scene",
            stream_id=stream_id,
            limit=50,
            time_range=time_window
        )
        
        if len(entries) < 2:
            return {
                "changes_detected": False,
                "message": "Insufficient data for change analysis"
            }
        
        # Analyze changes in objects and activities
        first_scene = entries[-1].content  # Oldest
        last_scene = entries[0].content    # Newest
        
        object_changes = {
            "added": list(set(last_scene.get("objects", [])) - set(first_scene.get("objects", []))),
            "removed": list(set(first_scene.get("objects", [])) - set(last_scene.get("objects", [])))
        }
        
        activity_changes = {
            "added": list(set(last_scene.get("activities", [])) - set(first_scene.get("activities", []))),
            "removed": list(set(first_scene.get("activities", [])) - set(last_scene.get("activities", [])))
        }
        
        changes_detected = (
            len(object_changes["added"]) > 0 or
            len(object_changes["removed"]) > 0 or
            len(activity_changes["added"]) > 0 or
            len(activity_changes["removed"]) > 0
        )
        
        return {
            "changes_detected": changes_detected,
            "time_window": str(time_window),
            "entries_analyzed": len(entries),
            "object_changes": object_changes,
            "activity_changes": activity_changes,
            "first_scene_time": first_scene.get("timestamp", ""),
            "last_scene_time": last_scene.get("timestamp", "")
        }
    
    async def _store_entry(self, entry: MemoryEntry) -> str:
        """
        Stores a memory entry in the database.

        Args:
            entry: The MemoryEntry object to store.

        Returns:
            The ID of the stored entry.
        """
        try:
            async with self._db_pool.get_connection() as db:
                await db.execute("""
                    INSERT OR REPLACE INTO memory_entries
                    (id, timestamp, entry_type, content, metadata, tags, stream_id, sequence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.id,
                    entry.timestamp,
                    entry.entry_type,
                    json.dumps(entry.content),
                    json.dumps(entry.metadata),
                    json.dumps(entry.tags),
                    entry.stream_id,
                    entry.sequence
                ))
                await db.commit()
                
            logger.debug(f"Stored memory entry: {entry.id}")
            return entry.id
            
        except Exception as e:
            logger.error(f"Failed to store memory entry: {e}")
            raise
    
    async def cleanup_old_entries(self, max_age: timedelta = timedelta(days=7)) -> int:
        """
        Cleans up old entries from the memory system.

        Args:
            max_age: The maximum age of entries to keep.

        Returns:
            The number of entries that were deleted.
        """
        await self.initialize()
        
        cutoff_time = (datetime.now() - max_age).isoformat()
        
        try:
            async with self._db_pool.get_connection() as db:
                cursor = await db.execute(
                    "DELETE FROM memory_entries WHERE timestamp < ?",
                    (cutoff_time,)
                )
                deleted_count = cursor.rowcount
                await db.commit()
                
            # Update cleanup statistics
            self._memory_stats["cleanup_runs"] += 1
            self._memory_stats["last_cleanup"] = datetime.now().isoformat()
            
            logger.info(f"Cleaned up {deleted_count} old memory entries")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old entries: {e}")
            return 0
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Retrieves statistics about the memory system.

        Returns:
            A dictionary containing memory system statistics.
        """
        await self.initialize()
        
        try:
            async with self._db_pool.get_connection() as db:
                # Total entries
                cursor = await db.execute("SELECT COUNT(*) FROM memory_entries")
                total_entries = (await cursor.fetchone())[0]
                
                # Entries by type
                cursor = await db.execute("""
                    SELECT entry_type, COUNT(*) 
                    FROM memory_entries 
                    GROUP BY entry_type
                """)
                entries_by_type = dict(await cursor.fetchall())
                
                # Recent entries (last 24 hours)
                cutoff_time = (datetime.now() - timedelta(hours=24)).isoformat()
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM memory_entries WHERE timestamp >= ?",
                    (cutoff_time,)
                )
                recent_entries = (await cursor.fetchone())[0]
                
                return {
                    "total_entries": total_entries,
                    "entries_by_type": entries_by_type,
                    "recent_entries_24h": recent_entries,
                    "database_path": str(self.db_path),
                    "initialized": self._initialized
                }
                
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
    
    async def _auto_cleanup_scheduler(self) -> None:
        """Runs the automatic cleanup task periodically."""
        try:
            while True:
                # Wait for 1 hour (3600 seconds)
                await asyncio.sleep(3600)
                
                # Perform cleanup
                deleted_count = await self.cleanup_old_entries(max_age=timedelta(days=7))
                
                # Log cleanup results
                if deleted_count > 0:
                    logger.info(f"Auto cleanup completed: {deleted_count} entries removed")
                else:
                    logger.debug("Auto cleanup completed: no entries to remove")
                    
        except asyncio.CancelledError:
            logger.info("Auto cleanup scheduler stopped")
            raise
        except Exception as e:
            logger.error(f"Auto cleanup scheduler error: {e}")
            # Continue running despite errors
            await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    async def get_memory_usage(self) -> Dict[str, Any]:
        """
        Retrieves current memory usage statistics.

        Returns:
            A dictionary containing memory usage statistics.
        """
        await self.initialize()
        
        try:
            import psutil
            import os
            
            # Get database file size
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
            
            # Get process memory usage
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            # Get entry counts
            async with self._db_pool.get_connection() as db:
                cursor = await db.execute("SELECT COUNT(*) FROM memory_entries")
                total_entries = (await cursor.fetchone())[0]
                
                # Get recent entries (last hour)
                cutoff_time = (datetime.now() - timedelta(hours=1)).isoformat()
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM memory_entries WHERE timestamp >= ?",
                    (cutoff_time,)
                )
                recent_entries = (await cursor.fetchone())[0]
            
            return {
                "database_size_bytes": db_size,
                "database_size_mb": round(db_size / (1024 * 1024), 2),
                "process_memory_mb": round(memory_info.rss / (1024 * 1024), 2),
                "total_entries": total_entries,
                "recent_entries_1h": recent_entries,
                "cleanup_stats": self._memory_stats.copy(),
                "auto_cleanup_enabled": self.auto_cleanup
            }
            
        except ImportError:
            # psutil not available, return basic stats
            return await self.get_statistics()
        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
            return {"error": str(e)}
    
    async def stop_cleanup_scheduler(self) -> None:
        """Stops the automatic cleanup scheduler."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Auto cleanup scheduler stopped")
    
    async def configure_auto_cleanup(self, enabled: bool, max_age_days: int = 7) -> Dict[str, Any]:
        """
        Configures the automatic memory cleanup settings.

        Args:
            enabled: A flag to enable or disable auto cleanup.
            max_age_days: The maximum age for entries in days.

        Returns:
            A dictionary with the configuration result.
        """
        try:
            # Stop current scheduler if running
            if self._cleanup_task and not self._cleanup_task.done():
                await self.stop_cleanup_scheduler()
            
            # Update configuration
            self.auto_cleanup = enabled
            
            # Start new scheduler if enabled
            if enabled:
                self._cleanup_task = asyncio.create_task(
                    self._auto_cleanup_scheduler()
                )
                
                # Perform immediate cleanup with new settings
                deleted_count = await self.cleanup_old_entries(
                    max_age=timedelta(days=max_age_days)
                )
                
                return {
                    "success": True,
                    "enabled": enabled,
                    "max_age_days": max_age_days,
                    "immediate_cleanup_count": deleted_count,
                    "message": f"Auto cleanup configured: enabled={enabled}, max_age={max_age_days} days. Immediate cleanup removed {deleted_count} entries."
                }
            else:
                return {
                    "success": True,
                    "enabled": enabled,
                    "message": "Auto cleanup disabled."
                }
                
        except Exception as e:
            logger.error(f"Failed to configure auto cleanup: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Error configuring auto cleanup: {str(e)}"
            }
    
    async def __aenter__(self):
        """Initializes the memory system when entering an async context."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stops the cleanup scheduler when exiting an async context."""
        await self.stop_cleanup_scheduler()


# Global memory system instance
memory_system = MemorySystem()