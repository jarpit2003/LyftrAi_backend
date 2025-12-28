import pytest
import asyncio
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.models import StatsResponse, MessageType
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
def sample_stats_response():
    """Sample stats response for testing"""
    return StatsResponse(
        total_messages=150,
        messages_by_type={
            "info": 100,
            "warning": 30,
            "error": 15,
            "success": 5
        },
        messages_by_source={
            "auth-service": 60,
            "payment-service": 40,
            "notification-service": 30,
            "user-service": 20
        },
        latest_message=datetime.utcnow(),
        oldest_message=datetime.utcnow() - timedelta(days=7),
        average_messages_per_hour=2.5
    )


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


class TestStatsEndpoint:
    """Test stats endpoint functionality"""
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_get_stats_empty(self, mock_metrics_collector, mock_storage_manager, client):
        """Test getting stats when no messages exist"""
        # Setup mocks
        empty_stats = StatsResponse(
            total_messages=0,
            messages_by_type={},
            messages_by_source={},
            latest_message=None,
            oldest_message=None,
            average_messages_per_hour=0.0
        )
        mock_storage_manager.get_stats = AsyncMock(return_value=empty_stats)
        mock_metrics_collector.increment_stats_requested = MagicMock()
        
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_messages"] == 0
        assert data["messages_by_type"] == {}
        assert data["messages_by_source"] == {}
        assert data["latest_message"] is None
        assert data["oldest_message"] is None
        assert data["average_messages_per_hour"] == 0.0
        mock_metrics_collector.increment_stats_requested.assert_called_once()
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_get_stats_with_data(self, mock_metrics_collector, mock_storage_manager, client, sample_stats_response):
        """Test getting stats with data"""
        # Setup mocks
        mock_storage_manager.get_stats = AsyncMock(return_value=sample_stats_response)
        mock_metrics_collector.increment_stats_requested = MagicMock()
        
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_messages"] == 150
        assert data["messages_by_type"]["info"] == 100
        assert data["messages_by_type"]["warning"] == 30
        assert data["messages_by_type"]["error"] == 15
        assert data["messages_by_type"]["success"] == 5
        assert data["messages_by_source"]["auth-service"] == 60
        assert data["messages_by_source"]["payment-service"] == 40
        assert data["messages_by_source"]["notification-service"] == 30
        assert data["messages_by_source"]["user-service"] == 20
        assert data["latest_message"] is not None
        assert data["oldest_message"] is not None
        assert data["average_messages_per_hour"] == 2.5
        mock_metrics_collector.increment_stats_requested.assert_called_once()
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_get_stats_storage_error(self, mock_metrics_collector, mock_storage_manager, client):
        """Test getting stats when storage fails"""
        # Setup mocks
        mock_storage_manager.get_stats = AsyncMock(side_effect=Exception("Storage error"))
        mock_metrics_collector.increment_stats_requested = MagicMock()
        mock_metrics_collector.increment_errors = MagicMock()
        
        response = client.get("/stats")
        
        assert response.status_code == 500
        mock_metrics_collector.increment_errors.assert_called_once()
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_get_stats_partial_data(self, mock_metrics_collector, mock_storage_manager, client):
        """Test getting stats with partial data"""
        # Setup mocks with partial stats
        partial_stats = StatsResponse(
            total_messages=50,
            messages_by_type={"info": 30, "error": 20},
            messages_by_source={"auth-service": 50},
            latest_message=datetime.utcnow(),
            oldest_message=None,  # Missing oldest message
            average_messages_per_hour=1.5
        )
        mock_storage_manager.get_stats = AsyncMock(return_value=partial_stats)
        mock_metrics_collector.increment_stats_requested = MagicMock()
        
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_messages"] == 50
        assert len(data["messages_by_type"]) == 2
        assert len(data["messages_by_source"]) == 1
        assert data["latest_message"] is not None
        assert data["oldest_message"] is None
        assert data["average_messages_per_hour"] == 1.5


class TestStatsModel:
    """Test StatsResponse model functionality"""
    
    def test_stats_response_creation(self):
        """Test creating a stats response"""
        latest = datetime.utcnow()
        oldest = latest - timedelta(days=1)
        
        stats = StatsResponse(
            total_messages=100,
            messages_by_type={"info": 80, "error": 20},
            messages_by_source={"service-a": 60, "service-b": 40},
            latest_message=latest,
            oldest_message=oldest,
            average_messages_per_hour=4.2
        )
        
        assert stats.total_messages == 100
        assert stats.messages_by_type == {"info": 80, "error": 20}
        assert stats.messages_by_source == {"service-a": 60, "service-b": 40}
        assert stats.latest_message == latest
        assert stats.oldest_message == oldest
        assert stats.average_messages_per_hour == 4.2
    
    def test_stats_response_empty(self):
        """Test creating an empty stats response"""
        stats = StatsResponse(
            total_messages=0,
            messages_by_type={},
            messages_by_source={},
            latest_message=None,
            oldest_message=None,
            average_messages_per_hour=0.0
        )
        
        assert stats.total_messages == 0
        assert stats.messages_by_type == {}
        assert stats.messages_by_source == {}
        assert stats.latest_message is None
        assert stats.oldest_message is None
        assert stats.average_messages_per_hour == 0.0
    
    def test_stats_response_serialization(self):
        """Test stats response serialization"""
        latest = datetime.utcnow()
        stats = StatsResponse(
            total_messages=25,
            messages_by_type={"info": 20, "warning": 5},
            messages_by_source={"test-service": 25},
            latest_message=latest,
            oldest_message=None,
            average_messages_per_hour=1.5
        )
        
        stats_dict = stats.dict()
        
        assert stats_dict["total_messages"] == 25
        assert stats_dict["messages_by_type"] == {"info": 20, "warning": 5}
        assert stats_dict["messages_by_source"] == {"test-service": 25}
        assert stats_dict["latest_message"] == latest.isoformat()
        assert stats_dict["oldest_message"] is None
        assert stats_dict["average_messages_per_hour"] == 1.5
    
    def test_stats_response_json_serialization(self):
        """Test stats response JSON serialization"""
        stats = StatsResponse(
            total_messages=10,
            messages_by_type={"info": 10},
            messages_by_source={"service": 10},
            latest_message=datetime.utcnow(),
            oldest_message=datetime.utcnow() - timedelta(hours=1),
            average_messages_per_hour=10.0
        )
        
        json_str = stats.json()
        
        assert isinstance(json_str, str)
        assert "total_messages" in json_str
        assert "messages_by_type" in json_str
        assert "average_messages_per_hour" in json_str


class TestStatsCalculation:
    """Test statistics calculation logic"""
    
    @pytest.mark.asyncio
    async def test_calculate_average_messages_per_hour(self):
        """Test average messages per hour calculation"""
        # Test with 24 hour period
        latest = datetime.utcnow()
        oldest = latest - timedelta(hours=24)
        total_messages = 48
        
        hours_diff = (latest - oldest).total_seconds() / 3600
        average = total_messages / max(hours_diff, 1)
        
        assert average == 2.0
    
    @pytest.mark.asyncio
    async def test_calculate_average_messages_with_no_time_diff(self):
        """Test average calculation when time difference is zero"""
        latest = datetime.utcnow()
        oldest = latest  # Same time
        total_messages = 10
        
        hours_diff = (latest - oldest).total_seconds() / 3600
        average = total_messages / max(hours_diff, 1)  # Should avoid division by zero
        
        assert average == 10.0
    
    @pytest.mark.asyncio
    async def test_group_messages_by_type(self):
        """Test grouping messages by type"""
        messages = [
            {"severity": "info"},
            {"severity": "info"},
            {"severity": "error"},
            {"severity": "warning"},
            {"severity": "info"}
        ]
        
        grouped = {}
        for message in messages:
            severity = message["severity"]
            grouped[severity] = grouped.get(severity, 0) + 1
        
        assert grouped == {"info": 3, "error": 1, "warning": 1}
    
    @pytest.mark.asyncio
    async def test_group_messages_by_source(self):
        """Test grouping messages by source"""
        messages = [
            {"source": "auth-service"},
            {"source": "payment-service"},
            {"source": "auth-service"},
            {"source": "notification-service"},
            {"source": "payment-service"},
            {"source": "auth-service"}
        ]
        
        grouped = {}
        for message in messages:
            source = message["source"]
            if source:  # Only count non-null sources
                grouped[source] = grouped.get(source, 0) + 1
        
        assert grouped == {"auth-service": 3, "payment-service": 2, "notification-service": 1}


class TestStatsStorageIntegration:
    """Test stats storage integration"""
    
    @pytest.fixture
    def storage_manager(self):
        """Create storage manager with test settings"""
        with patch('app.storage.get_settings') as mock_settings:
            mock_settings.return_value = Settings(
                database_url="sqlite:///:memory:"
            )
            return StorageManager()
    
    @pytest.mark.asyncio
    async def test_storage_get_stats_query(self, storage_manager):
        """Test storage stats query execution"""
        with patch('aiosqlite.connect') as mock_connect:
            mock_db = AsyncMock()
            mock_cursor = AsyncMock()
            
            # Mock the stats queries
            mock_cursor.fetchone.side_effect = [
                {'count': 100},  # Total messages
                {'latest': datetime.utcnow().isoformat(), 'oldest': (datetime.utcnow() - timedelta(days=1)).isoformat()}
            ]
            
            mock_cursor.fetchall.side_effect = [
                [{'severity': 'info', 'count': 80}, {'severity': 'error', 'count': 20}],  # By type
                [{'source': 'service-a', 'count': 60}, {'source': 'service-b', 'count': 40}]  # By source
            ]
            
            mock_db.execute.return_value.__aenter__.return_value = mock_cursor
            mock_connect.return_value.__aenter__.return_value = mock_db
            
            stats = await storage_manager.get_stats()
            
            assert stats.total_messages == 100
            assert 'info' in stats.messages_by_type
            assert 'error' in stats.messages_by_type
            assert 'service-a' in stats.messages_by_source
            assert 'service-b' in stats.messages_by_source
            assert stats.latest_message is not None
            assert stats.oldest_message is not None
            assert stats.average_messages_per_hour > 0
    
    @pytest.mark.asyncio
    async def test_storage_get_stats_empty_database(self, storage_manager):
        """Test storage stats with empty database"""
        with patch('aiosqlite.connect') as mock_connect:
            mock_db = AsyncMock()
            mock_cursor = AsyncMock()
            
            # Mock empty database response
            mock_cursor.fetchone.side_effect = [
                {'count': 0},
                {'latest': None, 'oldest': None}
            ]
            
            mock_cursor.fetchall.side_effect = [
                [],  # No types
                []   # No sources
            ]
            
            mock_db.execute.return_value.__aenter__.return_value = mock_cursor
            mock_connect.return_value.__aenter__.return_value = mock_db
            
            stats = await storage_manager.get_stats()
            
            assert stats.total_messages == 0
            assert stats.messages_by_type == {}
            assert stats.messages_by_source == {}
            assert stats.latest_message is None
            assert stats.oldest_message is None
            assert stats.average_messages_per_hour == 0.0
    
    @pytest.mark.asyncio
    async def test_storage_get_stats_with_null_sources(self, storage_manager):
        """Test storage stats with null sources"""
        with patch('aiosqlite.connect') as mock_connect:
            mock_db = AsyncMock()
            mock_cursor = AsyncMock()
            
            # Mock database with some null sources
            mock_cursor.fetchone.side_effect = [
                {'count': 50},
                {'latest': datetime.utcnow().isoformat(), 'oldest': (datetime.utcnow() - timedelta(hours=12)).isoformat()}
            ]
            
            mock_cursor.fetchall.side_effect = [
                [{'severity': 'info', 'count': 40}, {'severity': 'warning', 'count': 10}],  # By type
                [{'source': 'service-a', 'count': 30}]  # Only one source (others are null)
            ]
            
            mock_db.execute.return_value.__aenter__.return_value = mock_cursor
            mock_connect.return_value.__aenter__.return_value = mock_db
            
            stats = await storage_manager.get_stats()
            
            assert stats.total_messages == 50
            assert len(stats.messages_by_type) == 2
            assert len(stats.messages_by_source) == 1  # Only non-null sources
            assert stats.average_messages_per_hour > 0


class TestStatsIntegration:
    """Integration tests for stats functionality"""
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_stats_endpoint_integration(self, mock_metrics_collector, mock_storage_manager, client, sample_stats_response):
        """Test stats endpoint integration"""
        # Setup mocks
        mock_storage_manager.get_stats = AsyncMock(return_value=sample_stats_response)
        mock_metrics_collector.increment_stats_requested = MagicMock()
        
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all expected fields are present
        required_fields = [
            "total_messages",
            "messages_by_type", 
            "messages_by_source",
            "latest_message",
            "oldest_message",
            "average_messages_per_hour"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify data types
        assert isinstance(data["total_messages"], int)
        assert isinstance(data["messages_by_type"], dict)
        assert isinstance(data["messages_by_source"], dict)
        assert isinstance(data["average_messages_per_hour"], (int, float))
        
        # Verify metrics were updated
        mock_metrics_collector.increment_stats_requested.assert_called_once()
    
    @patch('app.main.storage')
    @patch('app.main.metrics')
    def test_stats_concurrent_requests(self, mock_metrics_collector, mock_storage_manager, client, sample_stats_response):
        """Test handling concurrent stats requests"""
        import threading
        
        # Setup mocks
        mock_storage_manager.get_stats = AsyncMock(return_value=sample_stats_response)
        mock_metrics_collector.increment_stats_requested = MagicMock()
        
        results = []
        
        def send_request():
            response = client.get("/stats")
            results.append(response.status_code)
        
        # Create multiple threads to simulate concurrent requests
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=send_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 5
        assert mock_metrics_collector.increment_stats_requested.call_count == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
