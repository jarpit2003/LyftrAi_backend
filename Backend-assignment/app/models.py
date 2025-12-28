from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
from enum import Enum
import uuid
import sqlite3
import os
import re

from .config import get_settings
from .logging_utils import get_logger


class MessageType(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class WebhookPayload(BaseModel):
    event: str
    data: Dict[str, Any]
    timestamp: Optional[datetime] = None
    source: Optional[str] = None
    severity: Optional[MessageType] = MessageType.INFO


class Message(BaseModel):
    message_id: str
    from_msisdn: str = Field(alias="from")
    to_msisdn: str = Field(alias="to")
    ts: str
    text: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().replace(microsecond=0).isoformat() + "Z")

    class Config:
        allow_population_by_field_name = True

    @validator('message_id')
    def validate_message_id(cls, v):
        if not v or not v.strip():
            raise ValueError('message_id must be a non-empty string')
        return v.strip()
    
    @validator('from_msisdn')
    def validate_from_msisdn(cls, v):
        if not v or not re.match(r'^\+\d+$', v):
            raise ValueError('from_msisdn must start with + followed by digits only')
        return v
    
    @validator('to_msisdn')
    def validate_to_msisdn(cls, v):
        if not v or not re.match(r'^\+\d+$', v):
            raise ValueError('to_msisdn must start with + followed by digits only')
        return v
    
    @validator('ts')
    def validate_ts(cls, v):
        if not v or not re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z$', v):
            raise ValueError('ts must be ISO-8601 UTC ending with Z')
        return v
    
    @validator('text')
    def validate_text(cls, v):
        if v is not None and len(v) > 4096:
            raise ValueError('text must be at most 4096 characters')
        return v
    
    @classmethod
    def from_webhook_payload(cls, payload: WebhookPayload) -> "Message":
        # Extract phone numbers and text from webhook data
        data = payload.data or {}
        return cls(
            message_id=data.get("message_id", ""),
            from_msisdn=data.get("from") or data.get("from_msisdn", ""),
            to_msisdn=data.get("to") or data.get("to_msisdn", ""),
            ts=data.get("ts", ""),
            text=data.get("text")
        )


class SenderCount(BaseModel):
    sender: str
    count: int


class StatsResponse(BaseModel):
    total_messages: int
    senders_count: int
    messages_per_sender: List[SenderCount]
    first_message_ts: Optional[str]
    last_message_ts: Optional[str]


class MessagesResponse(BaseModel):
    data: list[Message]
    total: int
    limit: int
    offset: int


class HealthCheck(BaseModel):
    status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    error: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[Dict[str, Any]] = None


def initialize_database():
    """Initialize SQLite database with the required schema"""
    settings = get_settings()
    db_url = settings.database_url
    
    # Extract file path from DATABASE_URL
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        # Ensure it uses /data/app.db
        if not db_path.startswith("/data/"):
            db_path = "/data/app.db"
    else:
        raise ValueError("Only SQLite database is supported")
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    logger = get_logger(__name__)
    logger.info(f"Initializing database at {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create messages table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                from_msisdn TEXT NOT NULL,
                to_msisdn TEXT NOT NULL,
                ts TEXT NOT NULL,
                text TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("Database schema initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise
