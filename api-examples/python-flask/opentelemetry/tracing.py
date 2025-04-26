"""
OpenTelemetry integration for production API services.
This module provides standardized tracing and metrics collection for production environments.
"""

import os
import logging
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.propagate import extract, inject


# Setup logging
logger = logging.getLogger(__name__)

def setup_production_telemetry(service_name, environment="production", framework="flask"):
    """
    Set up OpenTelemetry for a production service
    
    Args:
        service_name: Name of the service
        environment: Environment (production, staging, etc.)
        framework: Web framework being used (flask, django, fastapi)
    
    Returns:
        Tuple of (tracer, inject_headers_func)
    """
    # Configure the tracer provider
    resource = Resource(attributes={
        SERVICE_NAME: service_name,
        "environment": environment,
        "deployment.region": os.environ.get("DEPLOYMENT_REGION", "default"),
        "service.version": os.environ.get("SERVICE_VERSION", "1.0.0"),
    })
    
    # Create a tracer provider
    tracer_provider = TracerProvider(resource=resource)
    
    # Configure the OTLP exporter to send spans to Jaeger
    jaeger_host = os.environ.get("JAEGER_HOST", "jaeger")
    jaeger_port = os.environ.get("JAEGER_PORT", "4317")
    otlp_endpoint = f"http://{jaeger_host}:{jaeger_port}"
    
    logger.info(f"Configuring OpenTelemetry with endpoint: {otlp_endpoint}")
    
    # Create the exporter
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        
        # Add the exporter to the provider
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        
        # Set the provider as the global provider
        trace.set_tracer_provider(tracer_provider)
        
        # Get a tracer for this service
        tracer = trace.get_tracer(service_name, os.environ.get("SERVICE_VERSION", "1.0.0"))
        
        logger.info(f"Successfully configured OpenTelemetry for {service_name} in {environment}")
    except Exception as e:
        logger.error(f"Failed to configure OpenTelemetry exporter: {e}")
        tracer = trace.get_tracer(service_name)
    
    # Helper function to inject context headers
    def inject_headers(headers=None):
        """Inject trace context into outgoing request headers"""
        if headers is None:
            headers = {}
        
        inject(headers)
        return headers
    
    return tracer, inject_headers

def instrument_flask_app(app, service_name, environment="production"):
    """Instrument a Flask application with OpenTelemetry"""
    # Initialize tracer
    tracer, inject_headers = setup_production_telemetry(
        service_name=service_name,
        environment=environment,
        framework="flask"
    )
    
    # Instrument Flask
    FlaskInstrumentor().instrument_app(app)
    
    # Instrument other libraries
    RequestsInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    
    # Optional instrumentations - uncomment as needed
    try:
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        CeleryInstrumentor().instrument()
        Psycopg2Instrumentor().instrument()
        PymongoInstrumentor().instrument()
    except ImportError:
        pass
    
    # Add middleware for request context
    @app.before_request
    def before_request():
        # Enhance the current span with additional attributes
        current_span = trace.get_current_span()
        if current_span:
            # Add useful attributes for analysis
            current_span.set_attribute("service.name", service_name)
            current_span.set_attribute("environment", environment)
            
            # Add feature flags if used
            feature_flags = os.environ.get("FEATURE_FLAGS", "")
            if feature_flags:
                current_span.set_attribute("service.feature_flags", feature_flags)
    
    return tracer, inject_headers

def instrument_django_app(service_name, environment="production"):
    """Instrument a Django application with OpenTelemetry"""
    # Initialize tracer
    tracer, inject_headers = setup_production_telemetry(
        service_name=service_name,
        environment=environment,
        framework="django"
    )
    
    # Instrument Django
    DjangoInstrumentor().instrument()
    
    # Instrument other libraries
    RequestsInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    
    # Optional instrumentations - uncomment as needed
    try:
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        CeleryInstrumentor().instrument()
        Psycopg2Instrumentor().instrument()
        PymongoInstrumentor().instrument()
    except ImportError:
        pass
    
    return tracer, inject_headers

def instrument_fastapi_app(app, service_name, environment="production"):
    """Instrument a FastAPI application with OpenTelemetry"""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    
    # Initialize tracer
    tracer, inject_headers = setup_production_telemetry(
        service_name=service_name,
        environment=environment, 
        framework="fastapi"
    )
    
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # Instrument other libraries
    RequestsInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    
    # Optional instrumentations - uncomment as needed
    try:
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        CeleryInstrumentor().instrument()
        Psycopg2Instrumentor().instrument()
        PymongoInstrumentor().instrument()
    except ImportError:
        pass
    
    return tracer, inject_headers