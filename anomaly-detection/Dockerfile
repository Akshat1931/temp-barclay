FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY api-examples/python-flask/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create monitoring directory structure
RUN mkdir -p /app/monitoring/utils

# Copy monitoring module
COPY monitoring/ /app/monitoring/

# Copy application code
COPY api-examples/python-flask/ .

# Set Python path
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Expose the application port
EXPOSE 8000

# Run the application
CMD ["python", "app.py"]