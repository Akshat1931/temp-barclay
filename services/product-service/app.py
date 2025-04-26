"""
Product Service API
Manages product-related operations
"""
import sys
import os
import uuid
import time
import random
import logging
import json
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Sample product database (in-memory for demonstration)
PRODUCTS = {
    1: {"id": 1, "name": "Laptop", "category": "Electronics", "price": 999.99, "stock": 50},
    2: {"id": 2, "name": "Smartphone", "category": "Electronics", "price": 599.99, "stock": 100},
    3: {"id": 3, "name": "Headphones", "category": "Accessories", "price": 199.99, "stock": 75}
}

@app.route('/api/products', methods=['GET'])
def list_products():
    """Retrieve all products"""
    # Simulate potential processing delay
    time.sleep(random.uniform(0.05, 0.2))
    
    # Occasionally introduce a slow response
    if random.random() < 0.05:  # 5% chance
        time.sleep(random.uniform(1.0, 3.0))
        logger.warning("Slow product list retrieval")
    
    return jsonify(list(PRODUCTS.values()))

@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """Retrieve a specific product by ID"""
    # Simulate processing time
    time.sleep(random.uniform(0.05, 0.1))
    
    product = PRODUCTS.get(product_id)
    if product:
        return jsonify(product)
    
    return jsonify({"error": "Product not found"}), 404

@app.route('/api/products/search', methods=['GET'])
def search_products():
    """Search products by category or name"""
    # Simulate search processing
    time.sleep(random.uniform(0.1, 0.3))
    
    # Get search parameters
    category = request.args.get('category')
    name = request.args.get('name')
    
    # Simulate search logic
    results = []
    for product in PRODUCTS.values():
        if (category and product['category'].lower() == category.lower()) or \
           (name and name.lower() in product['name'].lower()):
            results.append(product)
    
    # Simulate occasional search failures
    if random.random() < 0.1:  # 10% chance of search error
        logger.warning(f"Search failed for category: {category}, name: {name}")
        return jsonify({"error": "Search failed"}), 500
    
    return jsonify(results)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "product-service"})

if __name__ == '__main__':
    # Run the Flask app
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)