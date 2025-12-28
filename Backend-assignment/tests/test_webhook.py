import pytest
import asyncio
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.models import WebhookPayload, MessageType
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
def sample_webhook_payload():
    """Sample webhook payload for testing"""
    return {
        "event": "user.signup",
        "data": {
            "user_id": "12345",
            "email": "test@example.com",
            "timestamp": "2023-01-01T00:00:00Z"
        },
        "source": "auth-service",
        "severity": "info"
    }


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


@pytest.fixture
def mock_metrics():
    """Mock metrics collector"""
    metrics = MagicMock()
    metrics.increment_messages_received = MagicMock()
    metrics.increment_messages_requested = MagicMock()
    metrics.increment_stats_requested = MagicMock()
    metrics.increment_errors = MagicMock()
    metrics.get_all_metrics = MagicMock(return_value={})
    return metrics


class TestWebhookEndpoint:
    """Test webhook endpoint functionality"""
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_webhook_success(self, mock_metrics_collector, mock_storage_manager, client, sample_webhook_payload):
        """Test successful webhook processing"""
        # Setup mocks
        mock_storage_manager.save_message = AsyncMock(return_value=True)
        mock_metrics_collector.increment_messages_received = MagicMock()
        
        response = client.post("/webhook", json=sample_webhook_payload)
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert "message_id" in response.json()
        mock_metrics_collector.increment_messages_received.assert_called_once()
    
    def test_webhook_invalid_payload(self, client):
        """Test webhook with invalid payload"""
        invalid_payload = {"invalid": "data"}
        
        response = client.post("/webhook", json=invalid_payload)
        
        assert response.status_code == 422  # Validation error
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_webhook_storage_error(self, mock_metrics_collector, mock_storage_manager, client, sample_webhook_payload):
        """Test webhook when storage fails"""
        # Setup mocks
        mock_storage_manager.save_message = AsyncMock(side_effect=Exception("Storage error"))
        mock_metrics_collector.increment_messages_received = MagicMock()
        mock_metrics_collector.increment_errors = MagicMock()
        
        response = client.post("/webhook", json=sample_webhook_payload)
        
        assert response.status_code == 500
        mock_metrics_collector.increment_errors.assert_called_once()
    
    def test_webhook_missing_required_fields(self, client):
        """Test webhook with missing required fields"""
        incomplete_payload = {
            "event": "test.event"
            # Missing 'data' field
        }
        
        response = client.post("/webhook", json=incomplete_payload)
        
        assert response.status_code == 422
    
    def test_webhook_with_all_fields(self, client):
        """Test webhook with all optional fields included"""
        complete_payload = {
            "event": "user.login",
            "data": {
                "user_id": "12345",
                "ip_address": "192.168.1.1"
            },
            "timestamp": "2023-01-01T12:00:00Z",
            "source": "auth-service",
            "severity": "warning"
        }
        
        response = client.post("/webhook", json=complete_payload)
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    def test_webhook_invalid_severity(self, client):
        """Test webhook with invalid severity value"""
        payload = {
            "event": "test.event",
            "data": {"test": "data"},
            "severity": "invalid_severity"
        }
        
        response = client.post("/webhook", json=payload)
        
        assert response.status_code == 422
    
    def test_webhook_empty_data(self, client):
        """Test webhook with empty data object"""
        payload = {
            "event": "test.event",
            "data": {}
        }
        
        response = client.post("/webhook", json=payload)
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    def test_webhook_complex_data(self, client):
        """Test webhook with complex nested data"""
        complex_payload = {
            "event": "order.created",
            "data": {
                "order_id": "ORD-12345",
                "customer": {
                    "id": "CUST-67890",
                    "name": "John Doe",
                    "address": {
                        "street": "123 Main St",
                        "city": "New York",
                        "country": "USA"
                    }
                },
                "items": [
                    {"id": "ITEM-1", "quantity": 2, "price": 29.99},
                    {"id": "ITEM-2", "quantity": 1, "price": 49.99}
                ],
                "total": 109.97,
                "metadata": {
                    "source": "web",
                    "campaign": "summer_sale"
                }
            },
            "source": "order-service",
            "severity": "info"
        }
        
        response = client.post("/webhook", json=complex_payload)
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_webhook_concurrent_requests(self, mock_metrics_collector, mock_storage_manager, client, sample_webhook_payload):
        """Test handling concurrent webhook requests"""
        import threading
        import time
        
        # Setup mocks
        mock_storage_manager.save_message = AsyncMock(return_value=True)
        mock_metrics_collector.increment_messages_received = MagicMock()
        
        results = []
        
        def send_request():
            response = client.post("/webhook", json=sample_webhook_payload)
            results.append(response.status_code)
        
        # Create multiple threads to simulate concurrent requests
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=send_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 10
        assert mock_metrics_collector.increment_messages_received.call_count == 10


class TestWebhookPayloadValidation:
    """Test webhook payload validation"""
    
    def test_webhook_payload_model_validation(self):
        """Test WebhookPayload model validation"""
        # Valid payload
        valid_data = {
            "event": "test.event",
            "data": {"key": "value"}
        }
        payload = WebhookPayload(**valid_data)
        assert payload.event == "test.event"
        assert payload.data == {"key": "value"}
        assert payload.severity == MessageType.INFO  # Default value
    
    def test_webhook_payload_with_timestamp(self):
        """Test WebhookPayload with custom timestamp"""
        timestamp = datetime.utcnow()
        valid_data = {
            "event": "test.event",
            "data": {"key": "value"},
            "timestamp": timestamp
        }
        payload = WebhookPayload(**valid_data)
        assert payload.timestamp == timestamp
    
    def test_webhook_payload_with_source(self):
        """Test WebhookPayload with source"""
        valid_data = {
            "event": "test.event",
            "data": {"key": "value"},
            "source": "test-service"
        }
        payload = WebhookPayload(**valid_data)
        assert payload.source == "test-service"
    
    def test_webhook_payload_with_severity(self):
        """Test WebhookPayload with severity"""
        valid_data = {
            "event": "test.event",
            "data": {"key": "value"},
            "severity": MessageType.ERROR
        }
        payload = WebhookPayload(**valid_data)
        assert payload.severity == MessageType.ERROR
    
    def test_webhook_payload_invalid_event(self):
        """Test WebhookPayload with invalid event type"""
        invalid_data = {
            "event": "",  # Empty event
            "data": {"key": "value"}
        }
        with pytest.raises(ValueError):
            WebhookPayload(**invalid_data)
    
    def test_webhook_payload_missing_data(self):
        """Test WebhookPayload missing data field"""
        invalid_data = {
            "event": "test.event"
            # Missing data
        }
        with pytest.raises(ValueError):
            WebhookPayload(**invalid_data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
