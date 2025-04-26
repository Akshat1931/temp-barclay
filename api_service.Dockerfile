FROM python:3.9-slim

WORKDIR /app

# Copy requirements file
COPY api-examples/python-flask/requirements.txt .

# Install dependencies (add the missing ones)
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install uuid python-json-logger opentelemetry-exporter-jaeger==1.11.1 opentelemetry-instrumentation

# Create required directories
RUN mkdir -p /app/monitoring/utils

# Copy the monitoring module files
COPY monitoring/__init__.py /app/monitoring/
COPY monitoring/utils/__init__.py /app/monitoring/utils/
COPY monitoring/utils/production_logging.py /app/monitoring/utils/

# Copy application code
COPY api-examples/python-flask/ .

# Create log directory
RUN mkdir -p /app/logs

# Set Python path
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Run the application
CMD ["python", "app.py"]