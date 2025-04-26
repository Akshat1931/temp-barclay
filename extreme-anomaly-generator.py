# Create a file called extreme-anomaly-generator.py
import requests
import time
import uuid
import random
import argparse
from datetime import datetime, timedelta

# Configure command line arguments
parser = argparse.ArgumentParser(description='Generate extreme API anomalies and baselines')
parser.add_argument('--logs', type=int, default=500, help='Number of logs to generate')
parser.add_argument('--anomalies', type=int, default=20, help='Number of manual anomalies to create')
parser.add_argument('--services', type=int, default=4, help='Number of services to generate data for')
parser.add_argument('--wait', type=int, default=60, help='Wait time in seconds after log generation')
parser.add_argument('--mode', choices=['logs', 'anomalies', 'both', 'baselines'], default='both', 
                    help='Operation mode: logs, anomalies, both, or baselines')
args = parser.parse_args()

# Define services and endpoints for more diverse data
SERVICES = {
    "user-service": {
        "endpoints": ["/api/users", "/api/users/profile", "/api/users/authenticate"],
        "environment": "production"
    },
    "product-service": {
        "endpoints": ["/api/products", "/api/products/search", "/api/products/categories"],
        "environment": "production"
    },
    "payment-service": {
        "endpoints": ["/api/payments", "/api/payments/process", "/api/payments/verify"],
        "environment": "production"
    },
    "notification-service": {
        "endpoints": ["/api/notifications", "/api/notifications/send", "/api/notifications/status"],
        "environment": "production"
    }
}

# Function to generate logs with extreme response times
def generate_extreme_logs(count=500, service_count=4):
    """Generate logs with extreme response times for multiple services"""
    print(f"Generating {count} extreme response time logs across {service_count} services...")
    
    # Select a subset of services if requested
    service_names = list(SERVICES.keys())[:service_count]
    
    for i in range(count):
        # Rotate through services to ensure even distribution
        service_name = service_names[i % len(service_names)]
        service = SERVICES[service_name]
        
        # Select random endpoint for this service
        endpoint = random.choice(service["endpoints"])
        environment = service["environment"]
        
        # Create log with extremely high response time (5-25 seconds)
        response_time = random.randint(5000, 25000)
        
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": service_name,
            "level": "INFO",
            "message": "API request completed",
            "logger": "extreme-anomaly-generator",
            "environment": environment,
            "host": f"{environment}-host",
            "request_id": str(uuid.uuid4()),
            "api_details": {
                "method": random.choice(["GET", "POST", "PUT"]),
                "endpoint": endpoint,
                "status_code": 200,
                "duration_ms": response_time,
                "response_size": random.randint(512, 4096)
            }
        }
        
        # Send to Logstash
        try:
            response = requests.post("http://localhost:8080", json=log_data, timeout=5)
            if i % 50 == 0:  # Only print status every 50 logs to reduce console spam
                print(f"Sent log {i+1}/{count}: Status {response.status_code}")
        except Exception as e:
            print(f"Error sending log: {e}")
        
        # Small delay between logs to avoid overwhelming Logstash
        time.sleep(0.05)
    
    print("Finished generating extreme logs")

# Function to generate normal baseline data
def generate_baseline_data(count=1000, service_count=4):
    """Generate normal baseline data for services"""
    print(f"Generating {count} baseline logs across {service_count} services...")
    
    # Select a subset of services if requested
    service_names = list(SERVICES.keys())[:service_count]
    
    # Generate data for the past 24 hours with timestamps spread out
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=24)
    
    for i in range(count):
        # Rotate through services to ensure even distribution
        service_name = service_names[i % len(service_names)]
        service = SERVICES[service_name]
        
        # Select random endpoint for this service
        endpoint = random.choice(service["endpoints"])
        environment = service["environment"]
        
        # Create log with normal response time (50-500ms)
        response_time = random.randint(50, 500)
        
        # Calculate timestamp spread across the 24 hour period
        point_time = start_time + timedelta(seconds=(i * 86400 / count))
        
        log_data = {
            "timestamp": point_time.isoformat(),
            "service": service_name,
            "level": "INFO",
            "message": "API request completed",
            "logger": "baseline-generator",
            "environment": environment,
            "host": f"{environment}-host",
            "request_id": str(uuid.uuid4()),
            "api_details": {
                "method": random.choice(["GET", "POST", "PUT"]),
                "endpoint": endpoint,
                "status_code": 200,
                "duration_ms": response_time,
                "response_size": random.randint(512, 2048)
            }
        }
        
        # Send to Logstash
        try:
            response = requests.post("http://localhost:8080", json=log_data, timeout=5)
            if i % 100 == 0:  # Only print status every 100 logs
                print(f"Sent baseline log {i+1}/{count}: Status {response.status_code}")
        except Exception as e:
            print(f"Error sending log: {e}")
        
        # Small delay between logs
        time.sleep(0.02)
    
    print("Finished generating baseline data")

# Function to directly create anomalies in Elasticsearch
def create_manual_anomalies(count=20, service_count=4):
    print(f"Creating {count} manual anomalies directly in Elasticsearch...")
    
    # Select a subset of services if requested
    service_names = list(SERVICES.keys())[:service_count]
    
    for i in range(count):
        # Rotate through services
        service_name = service_names[i % len(service_names)]
        service = SERVICES[service_name]
        endpoint = random.choice(service["endpoints"])
        
        # Create anomaly document with varying severity
        severity = random.choice(["medium", "high", "critical"])
        response_time = random.randint(10000, 30000)
        
        anomaly = {
            "type": "response_time" if random.random() < 0.7 else "error_rate",
            "service": service_name,
            "endpoint": endpoint,
            "avg_response_time": float(response_time),
            "p95_response_time": float(response_time * 1.2),
            "request_count": random.randint(10, 100),
            "timestamp": datetime.utcnow().isoformat(),
            "severity": severity,
            "detector": "manual-generator",
            "environment": "production",
            "manual": True
        }
        
        # Add error rate fields if it's that type of anomaly
        if anomaly["type"] == "error_rate":
            anomaly["error_rate"] = random.uniform(0.2, 0.8)
            anomaly["error_count"] = int(anomaly["request_count"] * anomaly["error_rate"])
        
        # Send directly to Elasticsearch
        try:
            response = requests.post(
                "http://localhost:9200/api-anomalies/_doc",
                json=anomaly,
                timeout=5
            )
            print(f"Created manual anomaly {i+1}/{count}: Status {response.status_code}")
        except Exception as e:
            print(f"Error creating anomaly: {e}")
        
        time.sleep(0.2)
    
    print("Finished creating manual anomalies")

# Function to create service baselines directly
def create_service_baselines(service_count=4):
    print(f"Creating service baselines directly in Elasticsearch...")
    
    # Select a subset of services if requested
    service_names = list(SERVICES.keys())[:service_count]
    
    for service_name in service_names:
        service = SERVICES[service_name]
        
        for endpoint in service["endpoints"]:
            # Create baseline document with realistic values
            baseline = {
                "service": service_name,
                "endpoint": endpoint,
                "avg_response_time": float(random.randint(100, 300)),
                "median_response_time": float(random.randint(80, 250)),
                "p95_response_time": float(random.randint(300, 600)),
                "p99_response_time": float(random.randint(500, 900)),
                "error_rate": float(random.uniform(0.01, 0.05)),
                "request_count": random.randint(1000, 5000),
                "status_codes": {"200": random.randint(900, 4500), "404": random.randint(10, 50), "500": random.randint(5, 30)},
                "updated_at": datetime.utcnow().isoformat(),
                "environment": "production"
            }
            
            # Send directly to Elasticsearch
            try:
                response = requests.post(
                    "http://localhost:9200/api-service-baselines/_doc",
                    json=baseline,
                    timeout=5
                )
                print(f"Created baseline for {service_name}{endpoint}: Status {response.status_code}")
            except Exception as e:
                print(f"Error creating baseline: {e}")
            
            time.sleep(0.2)
    
    print("Finished creating service baselines")

# Function to check if indices exist
def check_indices():
    print("Checking Elasticsearch indices...")
    
    indices = ["api-anomalies", "api-service-baselines", "api-logs-*"]
    
    for index in indices:
        try:
            if "*" in index:
                # For wildcard indices, use _cat/indices
                response = requests.get(f"http://localhost:9200/_cat/indices/{index}?format=json")
                if response.status_code == 200:
                    indices_data = response.json()
                    if indices_data:
                        print(f"Found {len(indices_data)} indices matching {index}")
                    else:
                        print(f"No indices found matching {index}")
            else:
                # For specific indices
                response = requests.get(f"http://localhost:9200/{index}")
                
                if response.status_code == 200:
                    print(f"Index {index} exists")
                    
                    # Check how many documents it has
                    count_response = requests.get(f"http://localhost:9200/{index}/_count")
                    if count_response.status_code == 200:
                        count = count_response.json().get("count", 0)
                        print(f"Index {index} contains {count} documents")
                elif response.status_code == 404:
                    print(f"Index {index} doesn't exist yet")
                    
                    # Create the index with appropriate mappings
                    if index == "api-anomalies":
                        create_anomalies_index()
                    elif index == "api-service-baselines":
                        create_baselines_index()
                else:
                    print(f"Unexpected response for {index}: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Error checking index {index}: {e}")

def create_anomalies_index():
    """Create the api-anomalies index with proper mapping"""
    try:
        mapping = {
            "mappings": {
                "properties": {
                    "timestamp": {"type": "date"},
                    "type": {"type": "keyword"},
                    "service": {"type": "keyword"},
                    "endpoint": {"type": "keyword"},
                    "avg_response_time": {"type": "float"},
                    "p95_response_time": {"type": "float"},
                    "p99_response_time": {"type": "float"},
                    "error_rate": {"type": "float"},
                    "error_count": {"type": "integer"},
                    "request_count": {"type": "integer"},
                    "severity": {"type": "keyword"},
                    "detector": {"type": "keyword"},
                    "environment": {"type": "keyword"},
                    "threshold_value": {"type": "float"},
                    "baseline_value": {"type": "float"}
                }
            }
        }
        
        response = requests.put(
            "http://localhost:9200/api-anomalies",
            json=mapping
        )
        
        print(f"api-anomalies index creation result: {response.status_code}")
    except Exception as e:
        print(f"Error creating api-anomalies index: {e}")

def create_baselines_index():
    """Create the api-service-baselines index with proper mapping"""
    try:
        mapping = {
            "mappings": {
                "properties": {
                    "service": {"type": "keyword"},
                    "endpoint": {"type": "keyword"},
                    "avg_response_time": {"type": "float"},
                    "median_response_time": {"type": "float"},
                    "p95_response_time": {"type": "float"},
                    "p99_response_time": {"type": "float"},
                    "error_rate": {"type": "float"},
                    "request_count": {"type": "integer"},
                    "status_codes": {"type": "object"},
                    "updated_at": {"type": "date"},
                    "environment": {"type": "keyword"}
                }
            }
        }
        
        response = requests.put(
            "http://localhost:9200/api-service-baselines",
            json=mapping
        )
        
        print(f"api-service-baselines index creation result: {response.status_code}")
    except Exception as e:
        print(f"Error creating api-service-baselines index: {e}")

if __name__ == "__main__":
    # First check the indices
    check_indices()
    
    if args.mode in ['logs', 'both']:
        # Generate extreme logs - these should trigger the anomaly detector
        generate_extreme_logs(args.logs, args.services)
    
    if args.mode == 'baselines':
        # Generate baseline data
        generate_baseline_data(1000, args.services)
        # Create service baselines directly
        create_service_baselines(args.services)
    
    # Wait for the anomaly detector to process the logs
    if args.wait > 0 and args.mode in ['logs', 'both']:
        print(f"\nWaiting {args.wait} seconds for anomaly detection to process logs...")
        time.sleep(args.wait)
    
    # Check if any anomalies were detected
    check_indices()
    
    if args.mode in ['anomalies', 'both']:
        # Create anomalies manually
        create_manual_anomalies(args.anomalies, args.services)
        
        # Verify the manually created anomalies
        check_indices()