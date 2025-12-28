import logging
import sys
import os
from typing import Optional
from datetime import datetime
import json


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
            
        return json.dumps(log_entry)


class ContextFilter(logging.Filter):
    """Filter to add context information to log records"""
    
    def filter(self, record):
        record.request_id = getattr(record, 'request_id', 'N/A')
        record.user_id = getattr(record, 'user_id', 'N/A')
        return True


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    log_file: Optional[str] = None
) -> None:
    """Setup application logging configuration"""
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Setup formatters
    if format_type.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(ContextFilter())
    root_logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(ContextFilter())
        root_logger.addHandler(file_handler)
    
    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name"""
    return logging.getLogger(name)


class LoggerMixin:
    """Mixin class to add logging capabilities to any class"""
    
    @property
    def logger(self):
        if not hasattr(self, '_logger'):
            self._logger = get_logger(self.__class__.__module__ + '.' + self.__class__.__name__)
        return self._logger
    
    def log_with_context(self, level: str, message: str, **context):
        """Log a message with additional context"""
        log_method = getattr(self.logger, level.lower())
        extra_fields = {'extra_fields': context}
        log_method(message, extra=extra_fields)


def log_request_response(logger: logging.Logger, request_id: str, method: str, path: str, 
                        status_code: Optional[int] = None, duration: Optional[float] = None):
    """Log HTTP request/response information"""
    
    log_data = {
        "request_id": request_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration * 1000 if duration else None
    }
    
    if status_code and status_code >= 400:
        logger.error(f"HTTP {status_code} - {method} {path}", extra={'extra_fields': log_data})
    else:
        logger.info(f"HTTP {status_code or 'REQUEST'} - {method} {path}", extra={'extra_fields': log_data})


def log_error_with_traceback(logger: logging.Logger, error: Exception, context: Optional[dict] = None):
    """Log an error with full traceback and context"""
    
    log_data = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context or {}
    }
    
    logger.error(f"Error occurred: {str(error)}", exc_info=True, extra={'extra_fields': log_data})
