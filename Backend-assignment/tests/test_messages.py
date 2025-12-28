import pytest
import asyncio
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.models import Message, MessageType, WebhookPayload
from app.storage import StorageManager
from app.config import Settings


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def test_settings():
    """Create test settings"""
    return Settings(
        debug=True,
        database_url="sqlite:///:memory:",
        log_level="DEBUG"
    )


@pytest.fixture
def sample_messages():
    """Sample messages for testing"""
    return [
        Message(
            id="msg-1",
            event="user.signup",
            data={"user_id": "123", "email": "test1@example.com"},
            timestamp=datetime.utcnow() - timedelta(hours=2),
            source="auth-service",
            severity=MessageType.INFO
        ),
        Message(
            id="msg-2",
            event="user.login",
            data={"user_id": "456", "ip": "192.168.1.1"},
            timestamp=datetime.utcnow() - timedelta(hours=1),
            source="auth-service",
            severity=MessageType.INFO
        ),
        Message(
            id="msg-3",
            event="payment.failed",
            data={"order_id": "ord-123", "amount": 99.99},
            timestamp=datetime.utcnow() - timedelta(minutes=30),
            source="payment-service",
            severity=MessageType.ERROR
        )
    ]


@pytest.fixture
def mock_storage():
    """Mock storage manager"""
    storage = AsyncMock()
    storage.initialize = AsyncMock()
    storage.save_message = AsyncMock(return_value=True)
    storage.get_messages = AsyncMock(return_value=[])
    storage.get_stats = AsyncMock(return_value={
        "total_messages": 0,
        "messages_by_type": {},
        "messages_by_source": {},
        "latest_message": None,
        "oldest_message": None,
        "average_messages_per_hour": 0.0
    })
    return storage


class TestMessagesEndpoint:
    """Test messages endpoint functionality"""
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_get_messages_empty(self, mock_metrics_collector, mock_storage_manager, client):
        """Test getting messages when none exist"""
        # Setup mocks
        mock_storage_manager.get_messages = AsyncMock(return_value=[])
        mock_metrics_collector.increment_messages_requested = MagicMock()
        
        response = client.get("/messages")
        
        assert response.status_code == 200
        assert response.json() == []
        mock_metrics_collector.increment_messages_requested.assert_called_once()
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_get_messages_with_data(self, mock_metrics_collector, mock_storage_manager, client, sample_messages):
        """Test getting messages with data"""
        # Setup mocks
        mock_storage_manager.get_messages = AsyncMock(return_value=sample_messages)
        mock_metrics_collector.increment_messages_requested = MagicMock()
        
        response = client.get("/messages")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["event"] == "user.signup"
        assert data[1]["event"] == "user.login"
        assert data[2]["event"] == "payment.failed"
        mock_metrics_collector.increment_messages_requested.assert_called_once()
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_get_messages_with_pagination(self, mock_metrics_collector, mock_storage_manager, client, sample_messages):
        """Test getting messages with pagination"""
        # Setup mocks
        mock_storage_manager.get_messages = AsyncMock(return_value=sample_messages[:2])
        mock_metrics_collector.increment_messages_requested = MagicMock()
        
        response = client.get("/messages?limit=2&offset=1")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        mock_storage_manager.get_messages.assert_called_once_with(limit=2, offset=1)
        mock_metrics_collector.increment_messages_requested.assert_called_once()
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_get_messages_storage_error(self, mock_metrics_collector, mock_storage_manager, client):
        """Test getting messages when storage fails"""
        # Setup mocks
        mock_storage_manager.get_messages = AsyncMock(side_effect=Exception("Storage error"))
        mock_metrics_collector.increment_messages_requested = MagicMock()
        mock_metrics_collector.increment_errors = MagicMock()
        
        response = client.get("/messages")
        
        assert response.status_code == 500
        mock_metrics_collector.increment_errors.assert_called_once()
    
    def test_get_messages_invalid_pagination(self, client):
        """Test getting messages with invalid pagination parameters"""
        response = client.get("/messages?limit=-1")
        # Should still work as FastAPI handles validation
        assert response.status_code in [422, 200]
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_get_messages_large_limit(self, mock_metrics_collector, mock_storage_manager, client):
        """Test getting messages with large limit"""
        # Setup mocks
        mock_storage_manager.get_messages = AsyncMock(return_value=[])
        mock_metrics_collector.increment_messages_requested = MagicMock()
        
        response = client.get("/messages?limit=1000")
        
        assert response.status_code == 200
        mock_storage_manager.get_messages.assert_called_once_with(limit=1000, offset=0)
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_get_messages_with_offset(self, mock_metrics_collector, mock_storage_manager, client):
        """Test getting messages with offset"""
        # Setup mocks
        mock_storage_manager.get_messages = AsyncMock(return_value=[])
        mock_metrics_collector.increment_messages_requested = MagicMock()
        
        response = client.get("/messages?offset=50")
        
        assert response.status_code == 200
        mock_storage_manager.get_messages.assert_called_once_with(limit=100, offset=50)


class TestMessageModel:
    """Test Message model functionality"""
    
    def test_message_creation(self):
        """Test creating a message"""
        timestamp = datetime.utcnow()
        message = Message(
            id="test-123",
            event="test.event",
            data={"key": "value"},
            timestamp=timestamp,
            source="test-service",
            severity=MessageType.WARNING
        )
        
        assert message.id == "test-123"
        assert message.event == "test.event"
        assert message.data == {"key": "value"}
        assert message.timestamp == timestamp
        assert message.source == "test-service"
        assert message.severity == MessageType.WARNING
    
    def test_message_defaults(self):
        """Test message default values"""
        message = Message(
            event="test.event",
            data={"key": "value"}
        )
        
        assert message.id is not None  # Generated UUID
        assert message.event == "test.event"
        assert message.data == {"key": "value"}
        assert message.timestamp is not None  # Current timestamp
        assert message.source is None
        assert message.severity == MessageType.INFO  # Default
        assert message.processed_at is not None  # Current timestamp
    
    def test_message_from_webhook_payload(self):
        """Test creating message from webhook payload"""
        webhook_payload = WebhookPayload(
            event="user.created",
            data={"user_id": "123", "email": "test@example.com"},
            source="auth-service",
            severity=MessageType.SUCCESS
        )
        
        message = Message.from_webhook_payload(webhook_payload)
        
        assert message.event == "user.created"
        assert message.data == {"user_id": "123", "email": "test@example.com"}
        assert message.source == "auth-service"
        assert message.severity == MessageType.SUCCESS
        assert message.processed_at is not None
    
    def test_message_serialization(self):
        """Test message serialization to dict"""
        message = Message(
            event="test.event",
            data={"key": "value"},
            source="test-service"
        )
        
        message_dict = message.dict()
        
        assert "id" in message_dict
        assert message_dict["event"] == "test.event"
        assert message_dict["data"] == {"key": "value"}
        assert message_dict["source"] == "test-service"
        assert "timestamp" in message_dict
        assert "processed_at" in message_dict
    
    def test_message_json_serialization(self):
        """Test message JSON serialization"""
        message = Message(
            event="test.event",
            data={"key": "value"}
        )
        
        json_str = message.json()
        
        assert isinstance(json_str, str)
        assert "test.event" in json_str
        assert "key" in json_str


class TestStorageManager:
    """Test StorageManager functionality"""
    
    @pytest.fixture
    def storage_manager(self):
        """Create storage manager with test settings"""
        with patch('app.storage.get_settings') as mock_settings:
            mock_settings.return_value = Settings(
                database_url="sqlite:///:memory:"
            )
            return StorageManager()
    
    @pytest.mark.asyncio
    async def test_storage_initialization(self, storage_manager):
        """Test storage initialization"""
        with patch('aiosqlite.connect') as mock_connect:
            mock_db = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_db
            
            await storage_manager.initialize()
            
            mock_connect.assert_called_once()
            # Verify table creation queries were executed
            assert mock_db.execute.call_count >= 4  # CREATE TABLE + 3 indexes
            mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_save_message(self, storage_manager):
        """Test saving a message"""
        message = Message(
            event="test.event",
            data={"key": "value"}
        )
        
        with patch('aiosqlite.connect') as mock_connect:
            mock_db = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_db
            
            result = await storage_manager.save_message(message)
            
            assert result is True
            mock_db.execute.assert_called_once()
            mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_messages(self, storage_manager):
        """Test retrieving messages"""
        with patch('aiosqlite.connect') as mock_connect:
            mock_db = AsyncMock()
            mock_cursor = AsyncMock()
            
            # Mock database response
            mock_row = AsyncMock()
            mock_row.__getitem__ = lambda self, key: {
                'id': 'test-123',
                'event': 'test.event',
                'data': '{"key": "value"}',
                'timestamp': datetime.utcnow().isoformat(),
                'source': 'test-service',
                'severity': 'info',
                'processed_at': datetime.utcnow().isoformat()
            }[key]
            
            mock_cursor.fetchall.return_value = [mock_row]
            mock_db.execute.return_value.__aenter__.return_value = mock_cursor
            mock_connect.return_value.__aenter__.return_value = mock_db
            
            messages = await storage_manager.get_messages(limit=10, offset=0)
            
            assert len(messages) == 1
            assert messages[0].event == "test.event"
            assert messages[0].data == {"key": "value"}
    
    @pytest.mark.asyncio
    async def test_get_stats(self, storage_manager):
        """Test getting statistics"""
        with patch('aiosqlite.connect') as mock_connect:
            mock_db = AsyncMock()
            mock_cursor = AsyncMock()
            
            # Mock stats queries
            mock_cursor.fetchone.side_effect = [
                {'count': 10},  # Total messages
                {'latest': datetime.utcnow().isoformat(), 'oldest': (datetime.utcnow() - timedelta(days=1)).isoformat()}
            ]
            
            mock_cursor.fetchall.side_effect = [
                [{'severity': 'info', 'count': 8}, {'severity': 'error', 'count': 2}],  # By type
                [{'source': 'auth-service', 'count': 6}, {'source': 'payment-service', 'count': 4}]  # By source
            ]
            
            mock_db.execute.return_value.__aenter__.return_value = mock_cursor
            mock_connect.return_value.__aenter__.return_value = mock_db
            
            stats = await storage_manager.get_stats()
            
            assert stats.total_messages == 10
            assert 'info' in stats.messages_by_type
            assert 'error' in stats.messages_by_type
            assert 'auth-service' in stats.messages_by_source
            assert 'payment-service' in stats.messages_by_source
            assert stats.latest_message is not None
            assert stats.oldest_message is not None
    
    @pytest.mark.asyncio
    async def test_cleanup_old_messages(self, storage_manager):
        """Test cleaning up old messages"""
        with patch('aiosqlite.connect') as mock_connect:
            mock_db = AsyncMock()
            mock_cursor = AsyncMock()
            mock_cursor.rowcount = 5
            mock_db.execute.return_value.__aenter__.return_value = mock_cursor
            mock_connect.return_value.__aenter__.return_value = mock_db
            
            deleted_count = await storage_manager.cleanup_old_messages(days=30)
            
            assert deleted_count == 5
            mock_db.execute.assert_called_once()
            mock_db.commit.assert_called_once()


class TestMessageIntegration:
    """Integration tests for message functionality"""
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_webhook_to_message_flow(self, mock_metrics_collector, mock_storage_manager, client):
        """Test complete flow from webhook to message storage"""
        webhook_payload = {
            "event": "user.registered",
            "data": {
                "user_id": "12345",
                "email": "newuser@example.com",
                "registration_source": "web"
            },
            "source": "auth-service",
            "severity": "success"
        }
        
        # Setup mocks
        mock_storage_manager.save_message = AsyncMock(return_value=True)
        mock_metrics_collector.increment_messages_received = MagicMock()
        
        # Send webhook
        response = client.post("/webhook", json=webhook_payload)
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # Verify storage was called
        mock_storage_manager.save_message.assert_called_once()
        
        # Get the message that was saved
        saved_message = mock_storage_manager.save_message.call_args[0][0]
        assert saved_message.event == "user.registered"
        assert saved_message.data["user_id"] == "12345"
        assert saved_message.source == "auth-service"
        assert saved_message.severity == MessageType.SUCCESS
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_message_retrieval_flow(self, mock_metrics_collector, mock_storage_manager, client, sample_messages):
        """Test message retrieval flow"""
        # Setup mocks
        mock_storage_manager.get_messages = AsyncMock(return_value=sample_messages)
        mock_metrics_collector.increment_messages_requested = MagicMock()
        
        response = client.get("/messages")
        
        assert response.status_code == 200
        messages = response.json()
        
        assert len(messages) == 3
        assert all("id" in msg for msg in messages)
        assert all("event" in msg for msg in messages)
        assert all("data" in msg for msg in messages)
        assert all("timestamp" in msg for msg in messages)
        
        # Verify metrics were updated
        mock_metrics_collector.increment_messages_requested.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
