"""
User Service API
Manages user-related operations
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

# Sample user database (in-memory for demonstration)
USERS = {
    1: {"id": 1, "username": "john_doe", "email": "john@example.com", "role": "admin"},
    2: {"id": 2, "username": "jane_smith", "email": "jane@example.com", "role": "user"},
    3: {"id": 3, "username": "bob_wilson", "email": "bob@example.com", "role": "user"}
}

@app.route('/api/users', methods=['GET'])
def list_users():
    """Retrieve all users"""
    # Simulate potential processing delay
    time.sleep(random.uniform(0.05, 0.2))
    
    # Occasionally introduce a slow response
    if random.random() < 0.05:  # 5% chance
        time.sleep(random.uniform(1.0, 3.0))
        logger.warning("Slow user list retrieval")
    
    return jsonify(list(USERS.values()))

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Retrieve a specific user by ID"""
    # Simulate processing time
    time.sleep(random.uniform(0.05, 0.1))
    
    user = USERS.get(user_id)
    if user:
        return jsonify(user)
    
    return jsonify({"error": "User not found"}), 404

@app.route('/api/users/authenticate', methods=['POST'])
def authenticate_user():
    """Simulate user authentication"""
    # Simulate authentication processing
    time.sleep(random.uniform(0.1, 0.3))
    
    # Get credentials from request
    auth_data = request.get_json()
    username = auth_data.get('username')
    password = auth_data.get('password')
    
    # Simulate authentication logic
    if not username or not password:
        return jsonify({"error": "Invalid credentials"}), 400
    
    # Simulate occasional authentication failures
    if random.random() < 0.1:  # 10% chance of auth failure
        logger.warning(f"Authentication failed for user: {username}")
        return jsonify({"error": "Authentication failed"}), 401
    
    # Find user by username
    for user in USERS.values():
        if user['username'] == username:
            return jsonify({
                "status": "success", 
                "user_id": user['id'], 
                "username": user['username']
            })
    
    return jsonify({"error": "User not found"}), 404

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "user-service"})

if __name__ == '__main__':
    # Run the Flask app
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)