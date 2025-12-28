import os
import sqlite3
import aiosqlite
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from contextlib import asynccontextmanager

from .models import Message, StatsResponse, SenderCount
from .config import get_settings
from .logging_utils import get_logger


logger = get_logger(__name__)


class StorageManager:
    def __init__(self):
        self.settings = get_settings()
        db_url = self.settings.database_url
        # Ensure we use /data/app.db
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
            if not db_path.startswith("/data/"):
                db_path = "/data/app.db"
        else:
            raise ValueError("Only SQLite database is supported")
        self.db_path = db_path
        
    async def initialize(self):
        """Initialize database connection (schema is created in models.py)"""
        try:
            # Test database connection
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("SELECT 1")
            logger.info(f"Database connection established at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            raise

    async def check_ready(self) -> Tuple[bool, str]:
        """Check DB reachability + schema presence for readiness probe."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                # DB reachable
                await db.execute("SELECT 1")

                # Table exists
                cursor = await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
                )
                row = await cursor.fetchone()
                if not row:
                    return False, "schema_missing"

                # Schema applied: required columns + message_id is PK
                cursor = await db.execute("PRAGMA table_info(messages)")
                cols = await cursor.fetchall()
                col_by_name = {c["name"]: c for c in cols}

                required = ["message_id", "from_msisdn", "to_msisdn", "ts", "text", "created_at"]
                for name in required:
                    if name not in col_by_name:
                        return False, "schema_missing"

                # PRAGMA table_info pk field is at index/column 'pk'
                if col_by_name["message_id"]["pk"] != 1:
                    return False, "schema_missing"

                return True, "ok"
        except Exception:
            return False, "db_unreachable"
    
    async def save_message(self, message: Message) -> bool:
        """Save a message to the database with idempotent insert logic"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Try to insert the message
                cursor = await db.execute("""
                    INSERT INTO messages (message_id, from_msisdn, to_msisdn, ts, text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    message.message_id,
                    message.from_msisdn,
                    message.to_msisdn,
                    message.ts,
                    message.text,
                    message.created_at
                ))
                
                await db.commit()
                logger.debug(f"Saved message {message.message_id}")
                return True
                
        except aiosqlite.IntegrityError as e:
            # Handle duplicate message_id (PRIMARY KEY constraint)
            if "UNIQUE constraint failed" in str(e) or "PRIMARY KEY" in str(e):
                logger.info(f"Duplicate message_id ignored: {message.message_id}", extra={'extra_fields': {"dup": "true"}})
                return True  # Still return success for idempotency
            else:
                logger.error(f"Database integrity error: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to save message: {str(e)}")
            return False
    
    async def get_messages(
        self,
        limit: int = 50,
        offset: int = 0,
        from_msisdn: Optional[str] = None,
        since: Optional[str] = None,
        q: Optional[str] = None,
    ) -> tuple[List[Message], int]:
        """Retrieve messages with pagination + combinable filters."""
        try:
            where_clauses: list[str] = []
            params: list[Any] = []

            if from_msisdn:
                where_clauses.append("from_msisdn = ?")
                params.append(from_msisdn)

            if since:
                where_clauses.append("ts >= ?")
                params.append(since)

            if q:
                where_clauses.append("text IS NOT NULL AND LOWER(text) LIKE ?")
                params.append(f"%{q.lower()}%")

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                count_cursor = await db.execute(
                    f"SELECT COUNT(*) as count FROM messages {where_sql}",
                    params,
                )
                total = (await count_cursor.fetchone())["count"]

                select_params = list(params) + [limit, offset]
                cursor = await db.execute(
                    f"""
                    SELECT message_id, from_msisdn, to_msisdn, ts, text, created_at
                    FROM messages
                    {where_sql}
                    ORDER BY ts ASC, message_id ASC
                    LIMIT ? OFFSET ?
                    """,
                    select_params,
                )

                rows = await cursor.fetchall()
                messages: List[Message] = []

                for row in rows:
                    messages.append(
                        Message(
                            message_id=row["message_id"],
                            from_msisdn=row["from_msisdn"],
                            to_msisdn=row["to_msisdn"],
                            ts=row["ts"],
                            text=row["text"],
                            created_at=row["created_at"],
                        )
                    )

                logger.debug(f"Retrieved {len(messages)} messages (total={total})")
                return messages, total

        except Exception as e:
            logger.error(f"Failed to get messages: {str(e)}")
            return [], 0
    
    async def get_stats(self) -> StatsResponse:
        """Generate analytics stats from stored messages."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                cursor = await db.execute("SELECT COUNT(*) as count FROM messages")
                total_messages = (await cursor.fetchone())["count"]

                cursor = await db.execute(
                    "SELECT COUNT(DISTINCT from_msisdn) as count FROM messages"
                )
                senders_count = (await cursor.fetchone())["count"]

                cursor = await db.execute(
                    """
                    SELECT from_msisdn as sender, COUNT(*) as count
                    FROM messages
                    GROUP BY from_msisdn
                    ORDER BY count DESC, sender ASC
                    LIMIT 10
                    """
                )
                rows = await cursor.fetchall()
                messages_per_sender = [
                    SenderCount(sender=row["sender"], count=row["count"]) for row in rows
                ]

                cursor = await db.execute(
                    "SELECT MIN(ts) as first_ts, MAX(ts) as last_ts FROM messages"
                )
                ts_row = await cursor.fetchone()
                first_message_ts = ts_row["first_ts"] if ts_row and ts_row["first_ts"] else None
                last_message_ts = ts_row["last_ts"] if ts_row and ts_row["last_ts"] else None

                return StatsResponse(
                    total_messages=total_messages,
                    senders_count=senders_count,
                    messages_per_sender=messages_per_sender,
                    first_message_ts=first_message_ts,
                    last_message_ts=last_message_ts,
                )

        except Exception as e:
            logger.error(f"Failed to get stats: {str(e)}")
            return StatsResponse(
                total_messages=0,
                senders_count=0,
                messages_per_sender=[],
                first_message_ts=None,
                last_message_ts=None,
            )
    
    async def cleanup_old_messages(self, days: int = 30) -> int:
        """Remove messages older than specified days"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    DELETE FROM messages 
                    WHERE created_at < ?
                """, (cutoff_date.isoformat(),))
                
                deleted_count = cursor.rowcount
                await db.commit()
                
                logger.info(f"Cleaned up {deleted_count} old messages")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old messages: {str(e)}")
            return 0
