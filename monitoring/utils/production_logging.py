"""
Standardized logging configuration for production API services.
This module provides consistent JSON logging that integrates with ELK stack.
"""

import os
import json
import uuid
import socket
import logging
import traceback
from datetime import datetime
from pythonjsonlogger import jsonlogger

# Service info
SERVICE_NAME = os.environ.get("SERVICE_NAME", "unknown-service")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")  # production, staging, development
SERVICE_VERSION = os.environ.get("SERVICE_VERSION", "1.0.0")
HOSTNAME = socket.gethostname()

class ProductionJsonFormatter(jsonlogger.JsonFormatter):
    """
    JSON formatter for production API services that outputs consistent logs
    compatible with the ELK stack and anomaly detection system.
    """
    def __init__(self, **kwargs):
        json_fmt = {
            "timestamp": "%(asctime)s",
            "level": "%(levelname)s",
            "logger": "%(name)s",
            "message": "%(message)s",
        }
        super().__init__(json_fmt=json_fmt, **kwargs)
        
    def add_fields(self, log_record, record, message_dict):
        """Add standard fields to the log record"""
        super().add_fields(log_record, record, message_dict)
        
        # Add standard service information
        log_record["service"] = SERVICE_NAME
        log_record["environment"] = ENVIRONMENT
        log_record["environment_type"] = ENVIRONMENT  # For compatibility with monitoring
        log_record["host"] = HOSTNAME
        log_record["service_version"] = SERVICE_VERSION
        
        # Add timestamp in ISO format
        now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        log_record["@timestamp"] = now
        
        # Add request ID if it exists
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
        
        # Add API details if they exist
        if hasattr(record, "api_details") and record.api_details:
            log_record.update(record.api_details)
        
        # Add exception info if it exists
        if record.exc_info:
            log_record["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add correlation ID for distributed tracing
        if hasattr(record, "trace_id"):
            log_record["trace_id"] = record.trace_id
        if hasattr(record, "span_id"):
            log_record["span_id"] = record.span_id


def configure_production_logging(module_name=None, log_level=None):
    """
    Configure production-ready JSON logging for a service
    
    Args:
        module_name: Optional specific logger name
        log_level: Logging level (defaults to INFO or from env var)
    
    Returns:
        Configured logger instance
    """
    if not log_level:
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    
    # Get the numeric level
    numeric_level = getattr(logging, log_level, logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers if any
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(ProductionJsonFormatter())
    root_logger.addHandler(console_handler)
    
    # Create file handler if LOG_FILE is defined
    log_file = os.environ.get("LOG_FILE")
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(ProductionJsonFormatter())
        root_logger.addHandler(file_handler)
    
    # Return the specific logger if module_name is provided
    if module_name:
        logger = logging.getLogger(module_name)
        logger.setLevel(numeric_level)
        return logger
    
    return root_logger


def get_request_logger(request_id=None):
    """
    Get a logger with request_id context
    
    Args:
        request_id: Optional request ID, will generate if not provided
    
    Returns:
        Logger with request context
    """
    if not request_id:
        request_id = str(uuid.uuid4())
        
    logger = logging.getLogger(SERVICE_NAME)
    
    # Create a logger adapter that adds request_id to all log records
    class RequestAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            if 'extra' not in kwargs:
                kwargs['extra'] = {}
            kwargs['extra']['request_id'] = self.extra['request_id']
            return msg, kwargs
    
    return RequestAdapter(logger, {'request_id': request_id})


class ApiLogMiddleware:
    """
    Middleware for Flask/WSGI applications to log API requests
    """
    def __init__(self, app, app_name=None):
        self.app = app
        self.app_name = app_name or SERVICE_NAME
        self.logger = logging.getLogger(self.app_name)
    
    def __call__(self, environ, start_response):
        # Generate request ID
        request_id = environ.get('HTTP_X_REQUEST_ID') or str(uuid.uuid4())
        environ['request_id'] = request_id
        
        # Track request start time
        request_start = datetime.now()
        
        # Get request information
        method = environ.get('REQUEST_METHOD', '')
        path = environ.get('PATH_INFO', '')
        query = environ.get('QUERY_STRING', '')
        client_ip = environ.get('REMOTE_ADDR', '')
        
        # Log request start
        self.logger.info(
            f"API request started: {method} {path}",
            extra={
                'request_id': request_id,
                'api_details': {
                    'http_method': method,
                    'endpoint': path,
                    'query': query,
                    'client_ip': client_ip
                }
            }
        )
        
        # Track response data
        response_status = [200]
        response_headers = []
        response_body_size = [0]
        
        def custom_start_response(status, headers, exc_info=None):
            status_code = int(status.split(' ')[0])
            response_status[0] = status_code
            response_headers[:] = headers
            return start_response(status, headers, exc_info)
        
        # Process the request
        response_body = []
        try:
            result = self.app(environ, custom_start_response)
            for data in result:
                response_body.append(data)
                response_body_size[0] += len(data)
            return response_body
        finally:
            # Calculate duration
            duration = (datetime.now() - request_start).total_seconds() * 1000  # ms
            
            # Log request completion
            status_code = response_status[0]
            self.logger.info(
                f"API request completed: {method} {path} - {status_code}",
                extra={
                    'request_id': request_id,
                    'api_details': {
                        'http_method': method,
                        'endpoint': path,
                        'client_ip': client_ip,
                        'status_code': status_code,
                        'response_time': duration,
                        'response_size': response_body_size[0]
                    }
                }
            )


# Flask integration
def setup_flask_logging(app, service_name=None):
    """
    Configure Flask application with standardized logging
    
    Args:
        app: Flask application
        service_name: Optional service name
    """
    from flask import request, g
    import time
    
    if not service_name:
        service_name = SERVICE_NAME
    
    # Configure logging
    configure_production_logging(service_name)
    logger = logging.getLogger(service_name)
    
    # Request middleware
    @app.before_request
    def before_request():
        # Get or generate request ID
        request_id = request.headers.get('X-Request-ID')
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Store in Flask g object
        g.request_id = request_id
        g.start_time = time.time()
        
        # Log request start
        logger.info(
            f"API request started: {request.method} {request.path}",
            extra={
                'request_id': request_id,
                'api_details': {
                    'http_method': request.method,
                    'endpoint': request.path,
                    'query_string': request.query_string.decode('utf-8'),
                    'client_ip': request.remote_addr
                }
            }
        )
    
    @app.after_request
    def after_request(response):
        # Calculate request duration
        duration = time.time() - g.start_time
        response_time = int(duration * 1000)  # Convert to milliseconds
        
        # Add request ID to response headers
        response.headers['X-Request-ID'] = g.request_id
        
        # Log request completion
        logger.info(
            f"API request completed: {request.method} {request.path} - {response.status_code}",
            extra={
                'request_id': g.request_id,
                'api_details': {
                    'http_method': request.method,
                    'endpoint': request.path,
                    'client_ip': request.remote_addr,
                    'status_code': response.status_code,
                    'response_time': response_time,
                    'response_size': response.calculate_content_length()
                }
            }
        )
        
        return response
    
    # Exception handler
    @app.errorhandler(Exception)
    def handle_exception(error):
        logger.error(
            f"API request error: {request.method} {request.path} - {type(error).__name__}: {str(error)}",
            exc_info=True,
            extra={
                'request_id': getattr(g, 'request_id', 'unknown'),
                'api_details': {
                    'http_method': request.method,
                    'endpoint': request.path,
                    'client_ip': request.remote_addr,
                    'error': str(error)
                }
            }
        )
        
        # Let Flask handle the exception
        return app.handle_user_exception(error)
    
    return logger


# Django integration
def setup_django_logging(service_name=None):
    """
    Configure Django application with standardized logging
    
    Args:
        service_name: Optional service name
    """
    if not service_name:
        service_name = SERVICE_NAME
        
    # Configure Django logging settings
    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'json': {
                '()': ProductionJsonFormatter,
            },
        },
        'handlers': {
            'console': {
                'level': os.environ.get('LOG_LEVEL', 'INFO'),
                'class': 'logging.StreamHandler',
                'formatter': 'json',
            },
            'file': {
                'level': os.environ.get('LOG_LEVEL', 'INFO'),
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.environ.get('LOG_FILE', '/var/log/api-services/django.log'),
                'maxBytes': 10485760,  # 10 MB
                'backupCount': 5,
                'formatter': 'json',
            } if os.environ.get('LOG_FILE') else {
                'level': 'ERROR',
                'class': 'logging.NullHandler',
            },
        },
        'loggers': {
            '': {
                'handlers': ['console', 'file'] if os.environ.get('LOG_FILE') else ['console'],
                'level': os.environ.get('LOG_LEVEL', 'INFO'),
            },
            service_name: {
                'handlers': ['console', 'file'] if os.environ.get('LOG_FILE') else ['console'],
                'level': os.environ.get('LOG_LEVEL', 'INFO'),
                'propagate': False,
            },
            'django': {
                'handlers': ['console', 'file'] if os.environ.get('LOG_FILE') else ['console'],
                'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
                'propagate': False,
            },
            'django.request': {
                'handlers': ['console', 'file'] if os.environ.get('LOG_FILE') else ['console'],
                'level': 'INFO',
                'propagate': False,
            },
        }
    }
    
    return logging_config, logging.getLogger(service_name)


# Django middleware class
class DjangoApiLoggingMiddleware:
    """
    Django middleware for API request logging
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger(SERVICE_NAME)
    
    def __call__(self, request):
        # Get or generate request ID
        request_id = request.META.get('HTTP_X_REQUEST_ID')
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Store for later use
        request.request_id = request_id
        request.start_time = datetime.now()
        
        # Log request start
        self.logger.info(
            f"API request started: {request.method} {request.path}",
            extra={
                'request_id': request_id,
                'api_details': {
                    'http_method': request.method,
                    'endpoint': request.path,
                    'query_string': request.META.get('QUERY_STRING', ''),
                    'client_ip': self._get_client_ip(request)
                }
            }
        )
        
        # Process the request
        response = self.get_response(request)
        
        # Calculate duration
        duration = (datetime.now() - request.start_time).total_seconds() * 1000  # ms
        
        # Add request ID to response
        response['X-Request-ID'] = request_id
        
        # Log request completion
        self.logger.info(
            f"API request completed: {request.method} {request.path} - {response.status_code}",
            extra={
                'request_id': request_id,
                'api_details': {
                    'http_method': request.method,
                    'endpoint': request.path,
                    'client_ip': self._get_client_ip(request),
                    'status_code': response.status_code,
                    'response_time': duration,
                    'response_size': len(response.content) if hasattr(response, 'content') else 0
                }
            }
        )
        
        return response
    
    def process_exception(self, request, exception):
        """Log exceptions during request processing"""
        self.logger.error(
            f"API request error: {request.method} {request.path} - {type(exception).__name__}: {str(exception)}",
            exc_info=True,
            extra={
                'request_id': getattr(request, 'request_id', 'unknown'),
                'api_details': {
                    'http_method': request.method,
                    'endpoint': request.path,
                    'client_ip': self._get_client_ip(request),
                    'error': str(exception)
                }
            }
        )
        return None
    
    def _get_client_ip(self, request):
        """Extract client IP from request with proxy support"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')