FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY anomaly-detection/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install python-json-logger requests opentelemetry-exporter-jaeger

# Create the monitoring module structure
RUN mkdir -p /app/monitoring/utils

# Copy monitoring module files
COPY monitoring/ /app/monitoring/

# Copy application code
COPY anomaly-detection/ /app/

# Set Python path
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Run the anomaly detection service
CMD ["python", "app.py"]