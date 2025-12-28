import time
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import json

from .logging_utils import get_logger


logger = get_logger(__name__)


@dataclass
class MetricPoint:
    """Single metric data point with timestamp"""
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: Dict[str, str] = field(default_factory=dict)


class Counter:
    """Simple counter metric that can be incremented"""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.value = 0
        self._lock = threading.Lock()
    
    def increment(self, amount: float = 1.0, tags: Dict[str, str] = None):
        """Increment the counter by specified amount"""
        with self._lock:
            self.value += amount
            logger.debug(f"Counter {self.name} incremented to {self.value}")
    
    def get_value(self) -> float:
        """Get current counter value"""
        with self._lock:
            return self.value
    
    def reset(self):
        """Reset counter to zero"""
        with self._lock:
            self.value = 0


class Gauge:
    """Gauge metric that can be set to arbitrary values"""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.value = 0.0
        self._lock = threading.Lock()
    
    def set(self, value: float, tags: Dict[str, str] = None):
        """Set gauge to specific value"""
        with self._lock:
            self.value = value
            logger.debug(f"Gauge {self.name} set to {self.value}")
    
    def get_value(self) -> float:
        """Get current gauge value"""
        with self._lock:
            return self.value


class Histogram:
    """Histogram metric that tracks distribution of values"""
    
    def __init__(self, name: str, description: str = "", buckets: List[float] = None):
        self.name = name
        self.description = description
        self.buckets = buckets or [0.1, 0.5, 1.0, 2.5, 5.0, 10.0]
        self.count = 0
        self.sum = 0.0
        self.bucket_counts = defaultdict(int)
        self._lock = threading.Lock()
    
    def observe(self, value: float, tags: Dict[str, str] = None):
        """Observe a new value"""
        with self._lock:
            self.count += 1
            self.sum += value
            
            for bucket in self.buckets:
                if value <= bucket:
                    self.bucket_counts[bucket] += 1
            
            logger.debug(f"Histogram {self.name} observed value {value}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get histogram statistics"""
        with self._lock:
            return {
                "count": self.count,
                "sum": self.sum,
                "buckets": dict(self.bucket_counts),
                "average": self.sum / max(self.count, 1)
            }


class MetricsCollector:
    """Main metrics collection system"""
    
    def __init__(self):
        self.counters: Dict[str, Counter] = {}
        self.gauges: Dict[str, Gauge] = {}
        self.histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()
        
        # Initialize default metrics
        self._setup_default_metrics()
    
    def _setup_default_metrics(self):
        """Setup default application metrics"""
        self.create_counter("messages_received_total", "Total number of messages received")
        self.create_counter("messages_requested_total", "Total number of message requests")
        self.create_counter("stats_requested_total", "Total number of stats requests")
        self.create_counter("errors_total", "Total number of errors")
        self.create_histogram("request_duration_seconds", "Request duration in seconds")
        self.create_gauge("active_connections", "Number of active connections")
    
    def create_counter(self, name: str, description: str = "") -> Counter:
        """Create a new counter metric"""
        with self._lock:
            if name in self.counters:
                return self.counters[name]
            
            counter = Counter(name, description)
            self.counters[name] = counter
            return counter
    
    def create_gauge(self, name: str, description: str = "") -> Gauge:
        """Create a new gauge metric"""
        with self._lock:
            if name in self.gauges:
                return self.gauges[name]
            
            gauge = Gauge(name, description)
            self.gauges[name] = gauge
            return gauge
    
    def create_histogram(self, name: str, description: str = "", buckets: List[float] = None) -> Histogram:
        """Create a new histogram metric"""
        with self._lock:
            if name in self.histograms:
                return self.histograms[name]
            
            histogram = Histogram(name, description, buckets)
            self.histograms[name] = histogram
            return histogram
    
    def get_counter(self, name: str) -> Optional[Counter]:
        """Get counter by name"""
        return self.counters.get(name)
    
    def get_gauge(self, name: str) -> Optional[Gauge]:
        """Get gauge by name"""
        return self.gauges.get(name)
    
    def get_histogram(self, name: str) -> Optional[Histogram]:
        """Get histogram by name"""
        return self.histograms.get(name)
    
    def increment_messages_received(self):
        """Increment messages received counter"""
        self.get_counter("messages_received_total").increment()
    
    def increment_messages_requested(self):
        """Increment messages requested counter"""
        self.get_counter("messages_requested_total").increment()
    
    def increment_stats_requested(self):
        """Increment stats requested counter"""
        self.get_counter("stats_requested_total").increment()
    
    def increment_errors(self):
        """Increment errors counter"""
        self.get_counter("errors_total").increment()
    
    def record_request_duration(self, duration: float):
        """Record request duration"""
        self.get_histogram("request_duration_seconds").observe(duration)
    
    def set_active_connections(self, count: int):
        """Set active connections gauge"""
        self.get_gauge("active_connections").set(float(count))
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics in a dictionary format"""
        metrics = {}
        
        # Collect counters
        metrics["counters"] = {
            name: {"value": counter.get_value(), "description": counter.description}
            for name, counter in self.counters.items()
        }
        
        # Collect gauges
        metrics["gauges"] = {
            name: {"value": gauge.get_value(), "description": gauge.description}
            for name, gauge in self.gauges.items()
        }
        
        # Collect histograms
        metrics["histograms"] = {
            name: {**histogram.get_stats(), "description": histogram.description}
            for name, histogram in self.histograms.items()
        }
        
        return metrics
    
    def reset_all_metrics(self):
        """Reset all metrics to zero"""
        with self._lock:
            for counter in self.counters.values():
                counter.reset()
            
            for gauge in self.gauges.values():
                gauge.set(0.0)
            
            for histogram in self.histograms.values():
                histogram.count = 0
                histogram.sum = 0.0
                histogram.bucket_counts.clear()
        
        logger.info("All metrics reset")
    
    def export_prometheus_format(self) -> str:
        """Export metrics in Prometheus format"""
        lines = []
        
        # Export counters
        for name, counter in self.counters.items():
            lines.append(f"# HELP {name} {counter.description}")
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {counter.get_value()}")
        
        # Export gauges
        for name, gauge in self.gauges.items():
            lines.append(f"# HELP {name} {gauge.description}")
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {gauge.get_value()}")
        
        # Export histograms
        for name, histogram in self.histograms.items():
            lines.append(f"# HELP {name} {histogram.description}")
            lines.append(f"# TYPE {name} histogram")
            lines.append(f"{name}_sum {histogram.sum}")
            lines.append(f"{name}_count {histogram.count}")
            
            for bucket, count in histogram.bucket_counts.items():
                lines.append(f"{name}_bucket{{le=\"{bucket}\"}} {count}")
        
        return "\n".join(lines)


class PrometheusMetrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._http_requests_total: Dict[tuple[str, str], int] = defaultdict(int)
        self._webhook_requests_total: Dict[str, int] = defaultdict(int)
        self._latency_buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._latency_bucket_counts: Dict[float, int] = defaultdict(int)
        self._latency_sum = 0.0
        self._latency_count = 0

    def inc_http_request(self, path: str, status: int):
        with self._lock:
            self._http_requests_total[(path, str(status))] += 1

    def inc_webhook_result(self, result: str):
        with self._lock:
            self._webhook_requests_total[result] += 1

    def observe_latency(self, seconds: float):
        with self._lock:
            self._latency_count += 1
            self._latency_sum += float(seconds)
            for b in self._latency_buckets:
                if seconds <= b:
                    self._latency_bucket_counts[b] += 1

    def export(self) -> str:
        with self._lock:
            lines: List[str] = []

            lines.append("# TYPE http_requests_total counter")
            for (path, status), count in sorted(self._http_requests_total.items()):
                lines.append(
                    f"http_requests_total{{path=\"{path}\",status=\"{status}\"}} {count}"
                )

            lines.append("# TYPE webhook_requests_total counter")
            for result, count in sorted(self._webhook_requests_total.items()):
                lines.append(f"webhook_requests_total{{result=\"{result}\"}} {count}")

            lines.append("# TYPE request_latency_seconds histogram")
            cumulative = 0
            for b in self._latency_buckets:
                cumulative += self._latency_bucket_counts.get(b, 0)
                lines.append(f"request_latency_seconds_bucket{{le=\"{b}\"}} {cumulative}")
            lines.append(f"request_latency_seconds_bucket{{le=\"+Inf\"}} {self._latency_count}")
            lines.append(f"request_latency_seconds_sum {self._latency_sum}")
            lines.append(f"request_latency_seconds_count {self._latency_count}")

            return "\n".join(lines) + "\n"


# Global metrics instance
metrics = MetricsCollector()


prom_metrics = PrometheusMetrics()
