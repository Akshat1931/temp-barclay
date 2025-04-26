import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from monitoring.utils.production_logging import configure_production_logging
import json
import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import LocalOutlierFactor
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = configure_production_logging(__name__)

# Elasticsearch connection - Use real connection parameters
ES_HOST = os.environ.get('ES_HOST', 'elasticsearch')
ES_PORT = os.environ.get('ES_PORT', '9200')
ES_USER = os.environ.get('ES_USER', '')
ES_PASSWORD = os.environ.get('ES_PASSWORD', '')

# Set up Elasticsearch client with authentication
if ES_USER and ES_PASSWORD:
    es = Elasticsearch([f'http://{ES_HOST}:{ES_PORT}'], http_auth=(ES_USER, ES_PASSWORD))
else:
    es = Elasticsearch([f'http://{ES_HOST}:{ES_PORT}'])

# Configuration for production use
ANALYSIS_INTERVAL = int(os.environ.get('ANALYSIS_INTERVAL', '300'))  # 5 minutes
HISTORICAL_WINDOW = int(os.environ.get('HISTORICAL_WINDOW', '24'))   # 24 hours
MAX_SAMPLES = int(os.environ.get('MAX_SAMPLES', '100000'))          # 100k samples
ANOMALY_THRESHOLD = float(os.environ.get('ANOMALY_THRESHOLD', '0.01'))  # 1% - more precise
MIN_DATA_POINTS = int(os.environ.get('MIN_DATA_POINTS', '30'))      # Min data points required

# Alert integration options
ALERT_WEBHOOK_URL = os.environ.get('ALERT_WEBHOOK_URL', '')         # Webhook for alerts (Slack, etc.)
PAGERDUTY_API_KEY = os.environ.get('PAGERDUTY_API_KEY', '')         # PagerDuty integration
ALERT_EMAIL = os.environ.get('ALERT_EMAIL', '')                     # Email for alerts

# Filter options
INCLUDED_SERVICES = os.environ.get('INCLUDED_SERVICES', '').split(',') if os.environ.get('INCLUDED_SERVICES') else []
EXCLUDED_SERVICES = os.environ.get('EXCLUDED_SERVICES', '').split(',') if os.environ.get('EXCLUDED_SERVICES') else []

class AnomalyDetector:
    def __init__(self):
        self.models = {
            'response_time': None,
            'error_rate': None,
            'status_codes': None
        }
        self.service_baselines = {}
        self.last_training_time = None
        self.index_pattern = os.environ.get('API_LOGS_INDEX', 'api-logs-*')
        
    def check_elasticsearch(self):
        """Check Elasticsearch connection and indices"""
        try:
            if not es.ping():
                logger.error("Cannot connect to Elasticsearch")
                return False
                
            # Check if index pattern exists
            indices = es.indices.get(index=self.index_pattern)
            if not indices:
                logger.warning(f"No indices found matching {self.index_pattern}")
                return False
                
            # Create anomalies index if needed
            if not es.indices.exists(index="api-anomalies"):
                logger.info("Creating api-anomalies index")
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
                            "request_count": {"type": "integer"},
                            "severity": {"type": "keyword"},
                            "detector": {"type": "keyword"},
                            "environment": {"type": "keyword"},
                            "environment_type": {"type": "keyword"},
                            "threshold_value": {"type": "float"},
                            "baseline_value": {"type": "float"}
                        }
                    }
                }
                es.indices.create(index="api-anomalies", body=mapping)
            
            logger.info("Elasticsearch connection verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error checking Elasticsearch: {e}")
            return False
        
    def fetch_data(self, hours=HISTORICAL_WINDOW):
        """Fetch real API logs from Elasticsearch"""
        now = datetime.utcnow()
        start_time = now - timedelta(hours=hours)
        
        logger.info(f"Fetching production data from {start_time} to {now}")
        
        # Build query with filters for real services
        query = {
            "size": MAX_SAMPLES,
            "sort": [{"@timestamp": {"order": "asc"}}],
            "query": {
                "bool": {
                    "must": [
                        {"range": {"@timestamp": {"gte": start_time.isoformat(), "lte": now.isoformat()}}},
                        {"exists": {"field": "response_time"}}
                    ],
                    "filter": [
                        {"range": {"response_time": {"gt": 0}}}  # Filter out invalid entries
                    ]
                }
            },
            "_source": [
                "@timestamp", "service", "endpoint", "status_code", "response_time", 
                "environment", "request_id", "environment_type", "http_method"
            ]
        }
        
        # Add service filters if specified
        if INCLUDED_SERVICES:
            query["query"]["bool"]["must"].append({"terms": {"service": INCLUDED_SERVICES}})
        
        if EXCLUDED_SERVICES:
            query["query"]["bool"]["must_not"] = [{"terms": {"service": EXCLUDED_SERVICES}}]
        
        try:
            result = es.search(index=self.index_pattern, body=query)
            hits = result['hits']['hits']
            
            if not hits:
                logger.warning(f"No data found in {self.index_pattern}")
                return pd.DataFrame()
                
            # Process real production data
            data = []
            for hit in hits:
                source = hit['_source']
                data.append({
                    'timestamp': source.get('@timestamp'),
                    'service': source.get('service'),
                    'endpoint': source.get('endpoint'),
                    'status_code': source.get('status_code'),
                    'response_time': source.get('response_time'),
                    'environment': source.get('environment'),
                    'environment_type': source.get('environment_type', 'unknown'),
                    'request_id': source.get('request_id'),
                    'http_method': source.get('http_method')
                })
            
            df = pd.DataFrame(data)
            
            # Convert timestamp and filter out invalid entries
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['is_error'] = df['status_code'].apply(lambda x: 1 if x and x >= 400 else 0)
            
            # Filter out invalid response times
            df = df[df['response_time'].notnull() & (df['response_time'] > 0)]
            
            logger.info(f"Successfully fetched {len(df)} real API logs")
            
            # Summarize data by service
            if not df.empty:
                service_counts = df.groupby('service').size()
                logger.info(f"Service distribution: {service_counts.to_dict()}")
                
                # Calculate average response times by service
                avg_times = df.groupby('service')['response_time'].mean().round(2)
                logger.info(f"Average response times by service: {avg_times.to_dict()}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching real data from Elasticsearch: {e}")
            return pd.DataFrame()

    def preprocess_data(self, df):
        """Process real production data for anomaly detection"""
        if df.empty:
            logger.warning("No data available for preprocessing")
            return None, None, None
            
        # Group by service and endpoint - real production grouping
        grouped = df.groupby(['service', 'endpoint'])
        
        # Extract features for anomaly detection
        response_time_data = []
        error_rate_data = []
        status_code_data = []
        
        # Process each service/endpoint combination
        for (service, endpoint), group in grouped:
            # Skip if too few data points for reliable analysis
            if len(group) < MIN_DATA_POINTS:
                logger.info(f"Skipping {service}/{endpoint} - only {len(group)} data points (need {MIN_DATA_POINTS})")
                continue
                
            # Calculate real metrics
            avg_response_time = group['response_time'].mean()
            median_response_time = group['response_time'].median()
            p95_response_time = group['response_time'].quantile(0.95)
            p99_response_time = group['response_time'].quantile(0.99)
            error_rate = group['is_error'].mean()
            request_count = len(group)
            status_codes = group['status_code'].value_counts().to_dict()
            
            # Store baseline for this service/endpoint
            service_key = f"{service}:{endpoint}"
            self.service_baselines[service_key] = {
                'avg_response_time': avg_response_time,
                'median_response_time': median_response_time,
                'p95_response_time': p95_response_time,
                'p99_response_time': p99_response_time,
                'error_rate': error_rate,
                'request_count': request_count,
                'status_codes': status_codes,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"Production metrics - {service}/{endpoint}: avg={avg_response_time:.2f}ms, p95={p95_response_time:.2f}ms, error_rate={error_rate:.4f}")
            
            # Create feature vectors for ML models
            response_time_data.append({
                'service': service,
                'endpoint': endpoint,
                'avg_response_time': avg_response_time,
                'median_response_time': median_response_time,
                'p95_response_time': p95_response_time,
                'p99_response_time': p99_response_time,
                'count': request_count
            })
            
            error_rate_data.append({
                'service': service,
                'endpoint': endpoint,
                'error_rate': error_rate,
                'count': request_count
            })
            
            status_code_data.append({
                'service': service,
                'endpoint': endpoint,
                'status_codes': status_codes,
                'count': request_count
            })
        
        # Convert to DataFrames
        response_time_df = pd.DataFrame(response_time_data) if response_time_data else None
        error_rate_df = pd.DataFrame(error_rate_data) if error_rate_data else None
        
        # Save baselines to Elasticsearch for reference
        try:
            es.index(
                index="api-service-baselines",
                id="latest",
                document={
                    "baselines": self.service_baselines,
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Failed to save baselines: {e}")
        
        return response_time_df, error_rate_df, status_code_data

    def train_models(self):
        """Train anomaly detection models on real production data"""
        logger.info("Training anomaly detection models on production data")
        
        # Fetch historical production data
        df = self.fetch_data(hours=HISTORICAL_WINDOW)
        if df.empty:
            logger.warning("No production data available for model training")
            return
            
        # Process the real data
        response_time_df, error_rate_df, status_code_data = self.preprocess_data(df)
        
        if response_time_df is None or len(response_time_df) < 2:
            logger.warning("Insufficient production data for model training")
            return
            
        # Train response time model on production data
        try:
            X_rt = response_time_df[['avg_response_time', 'p95_response_time']].values
            scaler_rt = StandardScaler()
            X_rt_scaled = scaler_rt.fit_transform(X_rt)
            
            # Use IsolationForest for response time anomalies
            model_rt = IsolationForest(
                contamination=ANOMALY_THRESHOLD,
                random_state=42,
                n_estimators=100,
                max_samples='auto'
            )
            model_rt.fit(X_rt_scaled)
            
            self.models['response_time'] = {
                'model': model_rt,
                'scaler': scaler_rt,
                'features': ['avg_response_time', 'p95_response_time'],
                'trained_at': datetime.utcnow().isoformat()
            }
            logger.info("Response time model trained successfully on production data")
        except Exception as e:
            logger.error(f"Error training response time model: {e}")
            
        # Train error rate model on production data
        try:
            if error_rate_df is not None and len(error_rate_df) >= 2:
                X_er = error_rate_df[['error_rate']].values
                scaler_er = StandardScaler()
                X_er_scaled = scaler_er.fit_transform(X_er)
                
                # Calculate optimal neighbors for LOF
                n_neighbors = max(5, min(20, len(X_er_scaled) // 2))
                
                # Use Local Outlier Factor for error rate anomalies
                model_er = LocalOutlierFactor(
                    n_neighbors=n_neighbors,
                    contamination=ANOMALY_THRESHOLD,
                    novelty=True  # Enable predict method
                )
                model_er.fit(X_er_scaled)
                
                self.models['error_rate'] = {
                    'model': model_er,
                    'scaler': scaler_er,
                    'features': ['error_rate'],
                    'trained_at': datetime.utcnow().isoformat()
                }
                logger.info("Error rate model trained successfully on production data")
            else:
                logger.warning("Insufficient error rate data for model training")
        except Exception as e:
            logger.error(f"Error training error rate model: {e}")
            
        self.last_training_time = datetime.utcnow()
    
    def detect_anomalies(self):
        """Detect anomalies in real-time production data"""
        # Fetch recent production data (last 5 minutes)
        recent_df = self.fetch_data(hours=0.1)  # ~6 minutes
        if recent_df.empty:
            logger.warning("No recent production data available for anomaly detection")
            return []
            
        # Process the real-time data
        response_time_df, error_rate_df, _ = self.preprocess_data(recent_df)
        
        if response_time_df is None or len(response_time_df) < 1:
            logger.warning("Insufficient recent production data for anomaly detection")
            return []
            
        anomalies = []
        
        # Detect response time anomalies in production
        if self.models['response_time'] is not None:
            try:
                model_info = self.models['response_time']
                X_rt = response_time_df[model_info['features']].values
                X_rt_scaled = model_info['scaler'].transform(X_rt)
                
                # Predict anomalies (-1 for anomalies, 1 for normal)
                predictions = model_info['model'].predict(X_rt_scaled)
                
                # Find anomalies in production data
                for i, pred in enumerate(predictions):
                    if pred == -1:  # Anomaly
                        service = response_time_df.iloc[i]['service']
                        endpoint = response_time_df.iloc[i]['endpoint']
                        avg_rt = response_time_df.iloc[i]['avg_response_time']
                        p95_rt = response_time_df.iloc[i]['p95_response_time']
                        count = response_time_df.iloc[i]['count']
                        
                        # Get baseline for comparison if available
                        service_key = f"{service}:{endpoint}"
                        baseline = self.service_baselines.get(service_key, {})
                        baseline_avg = baseline.get('avg_response_time', 0)
                        
                        # Calculate severity
                        if baseline_avg > 0:
                            deviation = avg_rt / baseline_avg
                            severity = 'critical' if deviation > 3 else 'high' if deviation > 2 else 'medium'
                        else:
                            severity = 'high' if avg_rt > 1000 else 'medium'
                        
                        anomalies.append({
                            'type': 'response_time',
                            'service': service,
                            'endpoint': endpoint,
                            'avg_response_time': float(avg_rt),
                            'p95_response_time': float(p95_rt),
                            'request_count': int(count),
                            'timestamp': datetime.utcnow().isoformat(),
                            'severity': severity,
                            'detector': 'ml_model',
                            'baseline_value': float(baseline_avg) if baseline_avg else None,
                            'deviation': float(deviation) if baseline_avg else None
                        })
                        logger.info(f"⚠️ ML model detected response time anomaly in production: {service}/{endpoint} - {avg_rt:.2f}ms")
            except Exception as e:
                logger.error(f"Error detecting response time anomalies: {e}")
                
        # Detect error rate anomalies in production data
        if self.models['error_rate'] is not None and error_rate_df is not None:
            try:
                model_info = self.models['error_rate']
                X_er = error_rate_df[model_info['features']].values
                X_er_scaled = model_info['scaler'].transform(X_er)
                
                # For LOF in novelty mode
                scores = model_info['model'].decision_function(X_er_scaled)
                predictions = np.where(scores < -0.5, -1, 1)  # Use threshold on anomaly scores
                
                # Find anomalies
                for i, pred in enumerate(predictions):
                    if pred == -1:  # Anomaly
                        service = error_rate_df.iloc[i]['service']
                        endpoint = error_rate_df.iloc[i]['endpoint']
                        error_rate = error_rate_df.iloc[i]['error_rate']
                        count = error_rate_df.iloc[i]['count']
                        
                        # Get baseline for comparison
                        service_key = f"{service}:{endpoint}"
                        baseline = self.service_baselines.get(service_key, {})
                        baseline_er = baseline.get('error_rate', 0)
                        
                        # Calculate severity based on error rate and baseline
                        if baseline_er > 0:
                            severity = 'critical' if error_rate > max(0.1, baseline_er * 5) else 'high' if error_rate > max(0.05, baseline_er * 3) else 'medium'
                        else:
                            severity = 'critical' if error_rate > 0.2 else 'high' if error_rate > 0.1 else 'medium'
                        
                        anomalies.append({
                            'type': 'error_rate',
                            'service': service,
                            'endpoint': endpoint,
                            'error_rate': float(error_rate),
                            'request_count': int(count),
                            'timestamp': datetime.utcnow().isoformat(),
                            'severity': severity,
                            'detector': 'ml_model',
                            'baseline_value': float(baseline_er) if baseline_er else None
                        })
                        logger.info(f"⚠️ ML model detected error rate anomaly in production: {service}/{endpoint} - {error_rate:.4f}")
            except Exception as e:
                logger.error(f"Error detecting error rate anomalies: {e}")
        
        return anomalies
    
    def find_direct_anomalies(self):
        """Find direct threshold anomalies in real-time production data"""
        recent_df = self.fetch_data(hours=0.1)  # ~6 minutes
        if recent_df.empty:
            return []
            
        anomalies = []
        
        # Define production thresholds - adjust these for your real services
        RESPONSE_TIME_THRESHOLD = float(os.environ.get('RESPONSE_TIME_THRESHOLD', '3000'))  # 3s
        ERROR_RATE_THRESHOLD = float(os.environ.get('ERROR_RATE_THRESHOLD', '0.1'))  # 10%
        
        # Find high response times directly in production data
        high_rt = recent_df[recent_df['response_time'] > RESPONSE_TIME_THRESHOLD]
        
        # Group high response times by service/endpoint
        if not high_rt.empty:
            rt_groups = high_rt.groupby(['service', 'endpoint']).agg(
                avg_response_time=('response_time', 'mean'),
                p95_response_time=('response_time', lambda x: np.percentile(x, 95)),
                count=('response_time', 'count')
            ).reset_index()
            
            for _, row in rt_groups.iterrows():
                service = row['service']
                endpoint = row['endpoint']
                response_time = row['avg_response_time']
                p95 = row['p95_response_time']
                count = row['count']
                
                # Get baseline if available
                service_key = f"{service}:{endpoint}"
                baseline = self.service_baselines.get(service_key, {})
                baseline_avg = baseline.get('avg_response_time', 0)
                
                # Calculate severity
                if baseline_avg > 0:
                    deviation = response_time / baseline_avg
                    severity = 'critical' if deviation > 4 else 'high' if deviation > 2.5 else 'medium'
                else:
                    severity = 'critical' if response_time > 5000 else 'high' if response_time > 3000 else 'medium'
                
                anomalies.append({
                    'type': 'response_time',
                    'service': service,
                    'endpoint': endpoint,
                    'avg_response_time': float(response_time),
                    'p95_response_time': float(p95),
                    'request_count': int(count),
                    'timestamp': datetime.utcnow().isoformat(),
                    'severity': severity,
                    'detector': 'threshold',
                    'threshold_value': float(RESPONSE_TIME_THRESHOLD),
                    'baseline_value': float(baseline_avg) if baseline_avg else None
                })
                logger.info(f"⚠️ Threshold detected response time anomaly: {service}/{endpoint} - {response_time:.2f}ms")
        
        # Find high error rates directly in production data
        if not recent_df.empty and 'is_error' in recent_df.columns:
            error_groups = recent_df.groupby(['service', 'endpoint']).agg(
                error_count=('is_error', 'sum'),
                total=('is_error', 'count')
            ).reset_index()
            
            error_groups['error_rate'] = error_groups['error_count'] / error_groups['total'].where(error_groups['total'] > 0, 0)
            high_errors = error_groups[error_groups['error_rate'] > ERROR_RATE_THRESHOLD]
            
            for _, row in high_errors.iterrows():
                service = row['service']
                endpoint = row['endpoint']
                error_rate = row['error_rate']
                count = row['total']
                
                # Get baseline if available
                service_key = f"{service}:{endpoint}"
                baseline = self.service_baselines.get(service_key, {})
                baseline_er = baseline.get('error_rate', 0)
                
                # Calculate severity
                if baseline_er > 0:
                    severity = 'critical' if error_rate > max(0.2, baseline_er * 5) else 'high' if error_rate > max(0.1, baseline_er * 3) else 'medium'
                else:
                    severity = 'critical' if error_rate > 0.3 else 'high' if error_rate > 0.2 else 'medium'
                
                anomalies.append({
                    'type': 'error_rate',
                    'service': service,
                    'endpoint': endpoint,
                    'error_rate': float(error_rate),
                    'error_count': int(row['error_count']),
                    'request_count': int(count),
                    'timestamp': datetime.utcnow().isoformat(),
                    'severity': severity,
                    'detector': 'threshold',
                    'threshold_value': float(ERROR_RATE_THRESHOLD),
                    'baseline_value': float(baseline_er) if baseline_er else None
                })
                logger.info(f"⚠️ Threshold detected error rate anomaly: {service}/{endpoint} - {error_rate:.4f}")
        
        return anomalies

    def send_alerts(self, anomalies):
        """Send alerts for real production anomalies"""
        if not anomalies:
            return
            
        # Index anomalies in Elasticsearch
        for anomaly in anomalies:
            try:
                # Add environment info if available
                if 'environment' not in anomaly and 'environment_type' not in anomaly:
                    anomaly['environment'] = 'production'
                    anomaly['environment_type'] = 'production'
                
                # Index in Elasticsearch
                result = es.index(index='api-anomalies', document=anomaly)
                logger.info(f"Alert indexed: {anomaly['type']} anomaly for {anomaly['service']}/{anomaly['endpoint']}")
                
                # Send webhook alert for critical anomalies
                if anomaly['severity'] == 'critical' and ALERT_WEBHOOK_URL:
                    self._send_webhook_alert(anomaly)
                
                # Send PagerDuty alert for critical anomalies
                if anomaly['severity'] == 'critical' and PAGERDUTY_API_KEY:
                    self._send_pagerduty_alert(anomaly)
                    
            except Exception as e:
                logger.error(f"Error sending alert to Elasticsearch: {e}")
    
    def _send_webhook_alert(self, anomaly):
        """Send webhook alert (e.g., to Slack)"""
        try:
            # Format message based on anomaly type
            if anomaly['type'] == 'response_time':
                title = f"🚨 High Response Time Alert: {anomaly['service']}/{anomaly['endpoint']}"
                message = (
                    f"*{anomaly['severity'].upper()}* response time anomaly detected\n"
                    f"• Service: `{anomaly['service']}`\n"
                    f"• Endpoint: `{anomaly['endpoint']}`\n"
                    f"• Avg Response Time: {anomaly['avg_response_time']:.2f}ms\n"
                    f"• P95 Response Time: {anomaly['p95_response_time']:.2f}ms\n"
                    f"• Request Count: {anomaly.get('request_count', 'N/A')}\n"
                    f"• Detection Method: {anomaly['detector']}\n"
                )
                
                # Add baseline comparison if available
                if anomaly.get('baseline_value') and anomaly.get('baseline_value') > 0:
                    deviation = anomaly['avg_response_time'] / anomaly['baseline_value']
                    message += f"• Deviation from baseline: {deviation:.2f}x normal\n"
            else:
                # Error rate anomaly
                title = f"🚨 High Error Rate Alert: {anomaly['service']}/{anomaly['endpoint']}"
                message = (
                    f"*{anomaly['severity'].upper()}* error rate anomaly detected\n"
                    f"• Service: `{anomaly['service']}`\n"
                    f"• Endpoint: `{anomaly['endpoint']}`\n"
                    f"• Error Rate: {anomaly['error_rate'] * 100:.2f}%\n"
                    f"• Request Count: {anomaly.get('request_count', 'N/A')}\n"
                    f"• Detection Method: {anomaly['detector']}\n"
                )
                
                # Add baseline comparison if available
                if anomaly.get('baseline_value') and anomaly.get('baseline_value') > 0:
                    deviation = anomaly['error_rate'] / anomaly['baseline_value']
                    message += f"• Deviation from baseline: {deviation:.2f}x normal\n"
            
            # Create webhook payload
            payload = {
                "text": title,
                "attachments": [
                    {
                        "color": "danger" if anomaly['severity'] == 'critical' else "warning",
                        "title": title,
                        "text": message,
                        "fields": [
                            {
                                "title": "Time",
                                "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "short": True
                            },
                            {
                                "title": "Environment",
                                "value": anomaly.get('environment', 'production'),
                                "short": True
                            }
                        ]
                    }
                ]
            }
            
            # Send to webhook
            response = requests.post(
                ALERT_WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            
            if response.status_code < 200 or response.status_code >= 300:
                logger.error(f"Failed to send webhook alert: {response.status_code} - {response.text}")
            else:
                logger.info(f"Webhook alert sent successfully for {anomaly['service']}/{anomaly['endpoint']}")
                
        except Exception as e:
            logger.error(f"Error sending webhook alert: {e}")
    
    def _send_pagerduty_alert(self, anomaly):
        """Send alert to PagerDuty for critical issues"""
        if not PAGERDUTY_API_KEY:
            return
            
        try:
            # Format alert details based on anomaly type
            if anomaly['type'] == 'response_time':
                summary = f"Critical Response Time: {anomaly['service']}/{anomaly['endpoint']} - {anomaly['avg_response_time']:.2f}ms"
                details = {
                    "service": anomaly['service'],
                    "endpoint": anomaly['endpoint'],
                    "avg_response_time": float(anomaly['avg_response_time']),
                    "p95_response_time": float(anomaly['p95_response_time']),
                    "request_count": int(anomaly.get('request_count', 0)),
                    "severity": anomaly['severity'],
                    "detector": anomaly['detector'],
                    "timestamp": anomaly['timestamp']
                }
            else:
                # Error rate anomaly
                summary = f"Critical Error Rate: {anomaly['service']}/{anomaly['endpoint']} - {anomaly['error_rate'] * 100:.2f}%"
                details = {
                    "service": anomaly['service'],
                    "endpoint": anomaly['endpoint'],
                    "error_rate": float(anomaly['error_rate']),
                    "request_count": int(anomaly.get('request_count', 0)),
                    "severity": anomaly['severity'],
                    "detector": anomaly['detector'],
                    "timestamp": anomaly['timestamp']
                }
            
            # Add baseline comparison if available
            if anomaly.get('baseline_value') and anomaly.get('baseline_value') > 0:
                if anomaly['type'] == 'response_time':
                    deviation = anomaly['avg_response_time'] / anomaly['baseline_value']
                    details['baseline_avg_response_time'] = float(anomaly['baseline_value'])
                    details['deviation_factor'] = float(deviation)
                else:
                    deviation = anomaly['error_rate'] / anomaly['baseline_value']
                    details['baseline_error_rate'] = float(anomaly['baseline_value'])
                    details['deviation_factor'] = float(deviation)
            
            # Create PagerDuty event
            payload = {
                "routing_key": PAGERDUTY_API_KEY,
                "event_action": "trigger",
                "payload": {
                    "summary": summary,
                    "source": f"{anomaly.get('environment', 'production')}-monitoring",
                    "severity": "critical",
                    "custom_details": details
                }
            }
            
            # Send to PagerDuty Events API
            response = requests.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            
            if response.status_code != 202:
                logger.error(f"Failed to send PagerDuty alert: {response.status_code} - {response.text}")
            else:
                logger.info(f"PagerDuty alert sent successfully for {anomaly['service']}/{anomaly['endpoint']}")
                
        except Exception as e:
            logger.error(f"Error sending PagerDuty alert: {e}")

    def run(self):
        """Main execution loop for production monitoring"""
        logger.info("Starting production API anomaly detection service")
        
        # Check Elasticsearch connection first
        if not self.check_elasticsearch():
            logger.error("Failed to verify Elasticsearch connection. Exiting.")
            return
        
        # Initial model training on production data
        self.train_models()
        
        # Record startup for dashboard
        startup_doc = {
            'type': 'service_event',
            'event': 'startup',
            'service': 'anomaly-detection',
            'timestamp': datetime.utcnow().isoformat(),
            'environment': 'production',
            'version': os.environ.get('VERSION', '1.0.0'),
            'config': {
                'ANALYSIS_INTERVAL': ANALYSIS_INTERVAL,
                'HISTORICAL_WINDOW': HISTORICAL_WINDOW,
                'ANOMALY_THRESHOLD': ANOMALY_THRESHOLD,
                'MIN_DATA_POINTS': MIN_DATA_POINTS
            }
        }
        
        try:
            es.index(index='api-anomalies', document=startup_doc)
        except Exception as e:
            logger.error(f"Failed to record startup: {e}")
        
        # Continuous monitoring loop
        while True:
            try:
                start_time = time.time()
                logger.info("Running anomaly detection cycle on production data")
                
                # Detect anomalies using ML models
                ml_anomalies = self.detect_anomalies()
                if ml_anomalies:
                    logger.info(f"Detected {len(ml_anomalies)} ML-based anomalies in production")
                
                # Also detect anomalies using direct thresholds
                direct_anomalies = self.find_direct_anomalies()
                if direct_anomalies:
                    logger.info(f"Found {len(direct_anomalies)} direct threshold anomalies in production")
                
                # Combine all anomalies
                all_anomalies = ml_anomalies + direct_anomalies
                
                # Send alerts
                if all_anomalies:
                    logger.info(f"Detected {len(all_anomalies)} total anomalies in production")
                    self.send_alerts(all_anomalies)
                else:
                    logger.info("No anomalies detected in production")
                
                # Retrain models periodically (every 6 hours)
                now = datetime.utcnow()
                if (self.last_training_time is None or 
                    (now - self.last_training_time).total_seconds() > 6 * 3600):
                    logger.info("Retraining anomaly detection models on fresh production data")
                    self.train_models()
                
                # Log cycle stats
                cycle_time = time.time() - start_time
                logger.info(f"Anomaly detection cycle completed in {cycle_time:.2f} seconds")
                
                # Calculate wait time to maintain consistent intervals
                wait_time = max(1, ANALYSIS_INTERVAL - cycle_time)
                time.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Error in anomaly detection loop: {e}")
                time.sleep(60)  # Wait before retrying

if __name__ == "__main__":
    detector = AnomalyDetector()
    detector.run()