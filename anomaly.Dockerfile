FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY anomaly-detection/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install python-json-logger requests

# Create monitoring directory structure
RUN mkdir -p /app/monitoring/utils

# Copy the monitoring module
COPY monitoring/__init__.py /app/monitoring/
COPY monitoring/utils/__init__.py /app/monitoring/utils/
COPY monitoring/utils/production_logging.py /app/monitoring/utils/

# Copy the application code
COPY anomaly-detection/ .

# Set Python path
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Run the application
CMD ["python", "app.py"]