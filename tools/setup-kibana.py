#!/usr/bin/env python3
"""
Script to set up production Kibana dashboards for API monitoring
"""

import requests
import json
import time
import logging
import sys
import os
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Kibana configuration
KIBANA_HOST = os.environ.get("KIBANA_HOST", "http://localhost:5601")
ES_HOST = os.environ.get("ES_HOST", "http://localhost:9200")
KIBANA_API = f"{KIBANA_HOST}/api"
KIBANA_USER = os.environ.get("KIBANA_USER", "elastic")
KIBANA_PASSWORD = os.environ.get("KIBANA_PASSWORD", "")

# Authentication headers
AUTH = (KIBANA_USER, KIBANA_PASSWORD) if KIBANA_USER and KIBANA_PASSWORD else None
HEADERS = {"kbn-xsrf": "true", "Content-Type": "application/json"}

def wait_for_kibana():
    """Wait for Kibana to be available"""
    logger.info("Waiting for Kibana to be ready...")
    retries = 30
    
    for i in range(retries):
        try:
            if AUTH:
                response = requests.get(f"{KIBANA_HOST}/api/status", auth=AUTH)
            else:
                response = requests.get(f"{KIBANA_HOST}/api/status")
                
            if response.status_code == 200:
                logger.info("Kibana is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        
        logger.info(f"Kibana not ready yet. Retry {i+1}/{retries}")
        time.sleep(10)
    
    logger.error("Kibana did not become available in time")
    return False

def create_index_patterns():
    """Create index patterns in Kibana for production monitoring"""
    logger.info("Creating index patterns for production monitoring...")
    
    patterns = [
        {
            "name": "api-logs-*",
            "title": "api-logs-*",
            "timeFieldName": "@timestamp"
        },
        {
            "name": "api-anomalies",
            "title": "api-anomalies",
            "timeFieldName": "timestamp"
        },
        {
            "name": "api-service-baselines",
            "title": "api-service-baselines",
            "timeFieldName": "updated_at"
        }
    ]
    
    for pattern in patterns:
        try:
            url = f"{KIBANA_API}/saved_objects/index-pattern/{pattern['name']}"
            
            # Check if pattern already exists
            if AUTH:
                response = requests.get(url, auth=AUTH)
            else:
                response = requests.get(url)
            
            if response.status_code == 200:
                logger.info(f"Index pattern '{pattern['name']}' already exists")
                continue
                
            # Create the pattern
            data = {
                "attributes": {
                    "title": pattern["title"],
                    "timeFieldName": pattern["timeFieldName"]
                }
            }
            
            if AUTH:
                response = requests.post(url, headers=HEADERS, json=data, auth=AUTH)
            else:
                response = requests.post(url, headers=HEADERS, json=data)
            
            if response.status_code in [200, 201]:
                logger.info(f"Created index pattern '{pattern['name']}'")
            else:
                logger.error(f"Failed to create index pattern '{pattern['name']}': {response.text}")
                
        except Exception as e:
            logger.error(f"Error creating index pattern '{pattern['name']}': {e}")

def set_default_index_pattern():
    """Set the default index pattern for production monitoring"""
    logger.info("Setting default index pattern...")
    
    url = f"{KIBANA_API}/saved_objects/config/7.17.0"
    data = {
        "attributes": {
            "defaultIndex": "api-logs-*"
        }
    }
    
    try:
        if AUTH:
            response = requests.post(url, headers=HEADERS, json=data, auth=AUTH)
        else:
            response = requests.post(url, headers=HEADERS, json=data)
        
        if response.status_code in [200, 201]:
            logger.info("Default index pattern set successfully")
        else:
            logger.error(f"Failed to set default index pattern: {response.text}")
            
    except Exception as e:
        logger.error(f"Error setting default index pattern: {e}")

def create_visualizations():
    """Create visualizations for production monitoring"""
    logger.info("Creating visualizations...")
    
    # Define visualizations
    visualizations = [
        {
            "id": "api-response-times",
            "type": "visualization",
            "attributes": {
                "title": "API Response Times by Service",
                "visState": json.dumps({
                    "title": "API Response Times by Service",
                    "type": "line",
                    "params": {
                        "type": "line",
                        "grid": {"categoryLines": false},
                        "categoryAxes": [
                            {
                                "id": "CategoryAxis-1",
                                "type": "category",
                                "position": "bottom",
                                "show": true,
                                "scale": {"type": "linear"},
                                "labels": {"show": true, "truncate": 100},
                                "title": {}
                            }
                        ],
                        "valueAxes": [
                            {
                                "id": "ValueAxis-1",
                                "name": "LeftAxis-1",
                                "type": "value",
                                "position": "left",
                                "show": true,
                                "scale": {"type": "linear", "mode": "normal"},
                                "labels": {"show": true, "rotate": 0, "filter": false, "truncate": 100},
                                "title": {"text": "Response Time (ms)"}
                            }
                        ],
                        "seriesParams": [
                            {
                                "show": true,
                                "type": "line",
                                "mode": "normal",
                                "data": {"label": "Average", "id": "1"},
                                "valueAxis": "ValueAxis-1",
                                "drawLinesBetweenPoints": true,
                                "lineWidth": 2,
                                "interpolate": "linear",
                                "showCircles": true
                            },
                            {
                                "show": true,
                                "type": "line",
                                "mode": "normal",
                                "data": {"label": "95th Percentile", "id": "2"},
                                "valueAxis": "ValueAxis-1",
                                "drawLinesBetweenPoints": true,
                                "lineWidth": 1,
                                "interpolate": "linear",
                                "showCircles": true
                            }
                        ],
                        "addTooltip": true,
                        "addLegend": true,
                        "legendPosition": "right",
                        "times": [],
                        "addTimeMarker": false,
                        "labels": {"show": false},
                        "dimensions": {
                            "x": {"accessor": 0, "format": {"id": "date", "params": {"pattern": "HH:mm:ss"}}, "params": {"date": true, "interval": "PT1M", "format": "HH:mm:ss"}, "aggType": "date_histogram"},
                            "y": [{"accessor": 1, "format": {"id": "number", "params": {"pattern": "0,0.00"}}, "params": {}, "aggType": "avg"},
                                  {"accessor": 2, "format": {"id": "number", "params": {"pattern": "0,0.00"}}, "params": {}, "aggType": "percentiles"}],
                            "series": [{"accessor": 3, "format": {"id": "string"}, "params": {}, "aggType": "terms"}]
                        }
                    },
                    "aggs": [
                        {"id": "1", "enabled": true, "type": "avg", "schema": "metric", "params": {"field": "response_time", "customLabel": "Average"}},
                        {"id": "2", "enabled": true, "type": "percentiles", "schema": "metric", "params": {"field": "response_time", "percents": [95], "customLabel": "95th Percentile"}},
                        {"id": "3", "enabled": true, "type": "date_histogram", "schema": "segment", "params": {"field": "@timestamp", "timeRange": {"from": "now-1h", "to": "now"}, "useNormalizedEsInterval": true, "interval": "auto", "drop_partials": false, "min_doc_count": 1, "extended_bounds": {}}},
                        {"id": "4", "enabled": true, "type": "terms", "schema": "group", "params": {"field": "service", "size": 10, "order": "desc", "orderBy": "1", "otherBucket": false, "otherBucketLabel": "Other", "missingBucket": false, "missingBucketLabel": "Missing"}}
                    ]
                }),
                "uiStateJSON": "{}",
                "description": "",
                "savedSearchId": "api-logs",
                "version": 1,
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({
                        "filter": [],
                        "query": {"query": "", "language": "kuery"}
                    })
                }
            }
        },
        {
            "id": "api-error-rates",
            "type": "visualization",
            "attributes": {
                "title": "API Error Rates by Service",
                "visState": json.dumps({
                    "title": "API Error Rates by Service",
                    "type": "area",
                    "params": {
                        "type": "area",
                        "grid": {"categoryLines": false},
                        "categoryAxes": [
                            {
                                "id": "CategoryAxis-1",
                                "type": "category",
                                "position": "bottom",
                                "show": true,
                                "scale": {"type": "linear"},
                                "labels": {"show": true, "truncate": 100},
                                "title": {}
                            }
                        ],
                        "valueAxes": [
                            {
                                "id": "ValueAxis-1",
                                "name": "LeftAxis-1",
                                "type": "value",
                                "position": "left",
                                "show": true,
                                "scale": {"type": "linear", "mode": "percentage", "defaultYExtents": false},
                                "labels": {"show": true, "rotate": 0, "filter": false, "truncate": 100},
                                "title": {"text": "Error Rate (%)"}
                            }
                        ],
                        "seriesParams": [
                            {
                                "show": true,
                                "type": "area",
                                "mode": "stacked",
                                "data": {"label": "Error Rate", "id": "1"},
                                "valueAxis": "ValueAxis-1",
                                "drawLinesBetweenPoints": true,
                                "lineWidth": 2,
                                "interpolate": "linear",
                                "showCircles": true
                            }
                        ],
                        "addTooltip": true,
                        "addLegend": true,
                        "legendPosition": "right",
                        "times": [],
                        "addTimeMarker": false,
                        "labels": {},
                        "thresholdLine": {
                            "show": true,
                            "value": 5,
                            "width": 1,
                            "style": "full",
                            "color": "#E7664C"
                        }
                    },
                    "aggs": [
                        {"id": "1", "enabled": true, "type": "avg", "schema": "metric", "params": {"field": "is_error", "customLabel": "Error Rate"}},
                        {"id": "2", "enabled": true, "type": "date_histogram", "schema": "segment", "params": {"field": "@timestamp", "timeRange": {"from": "now-1h", "to": "now"}, "useNormalizedEsInterval": true, "interval": "auto", "drop_partials": false, "min_doc_count": 1, "extended_bounds": {}}},
                        {"id": "3", "enabled": true, "type": "terms", "schema": "group", "params": {"field": "service", "size": 10, "order": "desc", "orderBy": "1", "otherBucket": false, "otherBucketLabel": "Other", "missingBucket": false, "missingBucketLabel": "Missing"}}
                    ]
                }),
                "uiStateJSON": "{}",
                "description": "",
                "savedSearchId": "api-logs",
                "version": 1,
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({
                        "filter": [],
                        "query": {"query": "", "language": "kuery"}
                    })
                }
            }
        },
        {
            "id": "api-anomaly-summary",
            "type": "visualization",
            "attributes": {
                "title": "API Anomaly Summary",
                "visState": json.dumps({
                    "title": "API Anomaly Summary",
                    "type": "metric",
                    "params": {
                        "addTooltip": true,
                        "addLegend": false,
                        "type": "metric",
                        "metric": {
                            "percentageMode": false,
                            "useRanges": false,
                            "colorSchema": "Red to Green",
                            "metricColorMode": "Labels",
                            "colorsRange": [
                                {"from": 0, "to": 10},
                                {"from": 10, "to": 50},
                                {"from": 50, "to": 100}
                            ],
                            "labels": {"show": true},
                            "invertColors": false,
                            "style": {"bgFill": "#000", "bgColor": false, "labelColor": false, "subText": "", "fontSize": 36}
                        }
                    },
                    "aggs": [
                        {"id": "1", "enabled": true, "type": "count", "schema": "metric", "params": {"customLabel": "Total Anomalies"}},
                        {"id": "2", "enabled": true, "type": "cardinality", "schema": "metric", "params": {"field": "service", "customLabel": "Affected Services"}},
                        {"id": "3", "enabled": true, "type": "count", "schema": "metric", "params": {"customLabel": "Critical Anomalies"}}
                    ]
                }),
                "uiStateJSON": "{}",
                "description": "",
                "version": 1,
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({
                        "query": {"query": "", "language": "kuery"},
                        "filter": [
                            {"meta": {"index": "api-anomalies", "type": "phrase", "key": "severity", "value": "critical", "params": {"query": "critical"}, "disabled": false, "negate": false}, "query": {"match_phrase": {"severity": "critical"}}, "$state": {"store": "appState"}}
                        ],
                        "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index"
                    })
                }
            },
            "references": [
                {"name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern", "id": "api-anomalies"}
            ]
        },
        {
            "id": "api-traffic-volume",
            "type": "visualization",
            "attributes": {
                "title": "API Traffic Volume",
                "visState": json.dumps({
                    "title": "API Traffic Volume",
                    "type": "histogram",
                    "params": {
                        "type": "histogram",
                        "grid": {"categoryLines": false},
                        "categoryAxes": [
                            {
                                "id": "CategoryAxis-1",
                                "type": "category",
                                "position": "bottom",
                                "show": true,
                                "scale": {"type": "linear"},
                                "labels": {"show": true, "truncate": 100},
                                "title": {}
                            }
                        ],
                        "valueAxes": [
                            {
                                "id": "ValueAxis-1",
                                "name": "LeftAxis-1",
                                "type": "value",
                                "position": "left",
                                "show": true,
                                "scale": {"type": "linear", "mode": "normal"},
                                "labels": {"show": true, "rotate": 0, "filter": false, "truncate": 100},
                                "title": {"text": "Request Count"}
                            }
                        ],
                        "seriesParams": [
                            {
                                "show": "true",
                                "type": "histogram",
                                "mode": "stacked",
                                "data": {"label": "Count", "id": "1"},
                                "valueAxis": "ValueAxis-1",
                                "drawLinesBetweenPoints": true,
                                "showCircles": true
                            }
                        ],
                        "addTooltip": true,
                        "addLegend": true,
                        "legendPosition": "right",
                        "times": [],
                        "addTimeMarker": false
                    },
                    "aggs": [
                        {"id": "1", "enabled": true, "type": "count", "schema": "metric", "params": {}},
                        {"id": "2", "enabled": true, "type": "date_histogram", "schema": "segment", "params": {"field": "@timestamp", "timeRange": {"from": "now-24h", "to": "now"}, "useNormalizedEsInterval": true, "interval": "auto", "drop_partials": false, "min_doc_count": 1, "extended_bounds": {}}},
                        {"id": "3", "enabled": true, "type": "terms", "schema": "group", "params": {"field": "service", "size": 10, "order": "desc", "orderBy": "1", "otherBucket": false, "otherBucketLabel": "Other", "missingBucket": false, "missingBucketLabel": "Missing"}}
                    ]
                }),
                "uiStateJSON": "{}",
                "description": "",
                "version": 1,
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({
                        "query": {"query": "", "language": "kuery"},
                        "filter": [],
                        "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index"
                    })
                }
            },
            "references": [
                {"name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern", "id": "api-logs-*"}
            ]
        }
    ]
    
    # Create each visualization
    for vis in visualizations:
        try:
            url = f"{KIBANA_API}/saved_objects/visualization/{vis['id']}"
            
            # Check if visualization already exists
            if AUTH:
                response = requests.get(url, auth=AUTH)
            else:
                response = requests.get(url)
            
            if response.status_code == 200:
                logger.info(f"Visualization '{vis['id']}' already exists, updating...")
                if AUTH:
                    response = requests.put(url, headers=HEADERS, json={"attributes": vis["attributes"]}, auth=AUTH)
                else:
                    response = requests.put(url, headers=HEADERS, json={"attributes": vis["attributes"]})
            else:
                # Create the visualization
                if AUTH:
                    response = requests.post(
                        f"{KIBANA_API}/saved_objects/visualization/{vis['id']}",
                        headers=HEADERS,
                        json={"attributes": vis["attributes"]},
                        auth=AUTH
                    )
                else:
                    response = requests.post(
                        f"{KIBANA_API}/saved_objects/visualization/{vis['id']}",
                        headers=HEADERS,
                        json={"attributes": vis["attributes"]}
                    )
            
            if response.status_code in [200, 201]:
                logger.info(f"Created/updated visualization '{vis['id']}'")
            else:
                logger.error(f"Failed to create visualization '{vis['id']}': {response.text}")
                
        except Exception as e:
            logger.error(f"Error creating visualization '{vis['id']}': {e}")

def create_dashboard():
    """Create main monitoring dashboard"""
    logger.info("Creating production monitoring dashboard...")
    
    dashboard_id = "api-monitoring-dashboard"
    dashboard_title = "Production API Monitoring"
    
    # Define dashboard with panels
    dashboard = {
        "attributes": {
            "title": dashboard_title,
            "hits": 0,
            "description": "Real-time monitoring of production API services",
            "panelsJSON": json.dumps([
                {
                    "panelIndex": "1",
                    "gridData": {"x": 0, "y": 0, "w": 24, "h": 8, "i": "1"},
                    "embeddableConfig": {},
                    "id": "api-anomaly-summary",
                    "type": "visualization"
                },
                {
                    "panelIndex": "2",
                    "gridData": {"x": 0, "y": 8, "w": 24, "h": 12, "i": "2"},
                    "embeddableConfig": {},
                    "id": "api-response-times",
                    "type": "visualization"
                },
                {
                    "panelIndex": "3",
                    "gridData": {"x": 0, "y": 20, "w": 24, "h": 12, "i": "3"},
                    "embeddableConfig": {},
                    "id": "api-error-rates",
                    "type": "visualization"
                },
                {
                    "panelIndex": "4",
                    "gridData": {"x": 0, "y": 32, "w": 24, "h": 10, "i": "4"},
                    "embeddableConfig": {},
                    "id": "api-traffic-volume",
                    "type": "visualization"
                }
            ]),
            "optionsJSON": json.dumps({
                "hidePanelTitles": false,
                "useMargins": true
            }),
            "version": 1,
            "timeRestore": true,
            "timeTo": "now",
            "timeFrom": "now-24h",
            "refreshInterval": {
                "pause": false,
                "value": 60000  # 1 minute refresh
            },
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({
                    "query": {
                        "language": "kuery",
                        "query": ""
                    },
                    "filter": []
                })
            }
        }
    }
    
    try:
        url = f"{KIBANA_API}/saved_objects/dashboard/{dashboard_id}"
        
        # Check if dashboard already exists
        if AUTH:
            response = requests.get(url, auth=AUTH)
        else:
            response = requests.get(url)
        
        if response.status_code == 200:
            logger.info(f"Dashboard '{dashboard_id}' already exists, updating...")
            if AUTH:
                response = requests.put(url, headers=HEADERS, json=dashboard, auth=AUTH)
            else:
                response = requests.put(url, headers=HEADERS, json=dashboard)
        else:
            # Create the dashboard
            if AUTH:
                response = requests.post(url, headers=HEADERS, json=dashboard, auth=AUTH)
            else:
                response = requests.post(url, headers=HEADERS, json=dashboard)
        
        if response.status_code in [200, 201]:
            logger.info(f"Created/updated dashboard '{dashboard_title}'")
            logger.info(f"Dashboard URL: {KIBANA_HOST}/app/kibana#/dashboard/{dashboard_id}")
        else:
            logger.error(f"Failed to create dashboard: {response.text}")
            
    except Exception as e:
        logger.error(f"Error creating dashboard: {e}")

def create_api_logs_saved_search():
    """Create a saved search for API logs"""
    logger.info("Creating API logs saved search...")
    
    saved_search = {
        "attributes": {
            "title": "API Logs",
            "description": "API logs across all services",
            "columns": ["@timestamp", "service", "endpoint", "status_code", "response_time", "environment"],
            "sort": ["@timestamp", "desc"],
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({
                    "query": {
                        "query": "",
                        "language": "kuery"
                    },
                    "filter": [],
                    "highlightAll": True,
                    "version": True,
                    "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index"
                })
            }
        },
        "references": [
            {
                "id": "api-logs-*",
                "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
                "type": "index-pattern"
            }
        ]
    }
    
    try:
        search_id = "api-logs"
        url = f"{KIBANA_API}/saved_objects/search/{search_id}"
        
        # Check if search already exists
        if AUTH:
            response = requests.get(url, auth=AUTH)
        else:
            response = requests.get(url)
        
        if response.status_code == 200:
            logger.info(f"Saved search '{search_id}' already exists, updating...")
            if AUTH:
                response = requests.put(url, headers=HEADERS, json=saved_search, auth=AUTH)
            else:
                response = requests.put(url, headers=HEADERS, json=saved_search)
        else:
            # Create the saved search
            if AUTH:
                response = requests.post(url, headers=HEADERS, json=saved_search, auth=AUTH)
            else:
                response = requests.post(url, headers=HEADERS, json=saved_search)
        
        if response.status_code in [200, 201]:
            logger.info(f"Created/updated saved search 'API Logs'")
        else:
            logger.error(f"Failed to create saved search: {response.text}")
            
    except Exception as e:
        logger.error(f"Error creating saved search: {e}")

if __name__ == "__main__":
    if not wait_for_kibana():
        sys.exit(1)
        
    create_index_patterns()
    set_default_index_pattern()
    create_api_logs_saved_search()
    create_visualizations()
    create_dashboard()
    
    logger.info("Kibana dashboard setup completed successfully!")
