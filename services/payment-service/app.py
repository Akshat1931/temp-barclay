"""
Payment Service API
Manages payment-related operations
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

# Sample payment records (in-memory for demonstration)
PAYMENTS = {}

@app.route('/api/payments', methods=['GET'])
def list_payments():
    """Retrieve all payment records"""
    # Simulate potential processing delay
    time.sleep(random.uniform(0.05, 0.2))
    
    # Occasionally introduce a slow response
    if random.random() < 0.05:  # 5% chance
        time.sleep(random.uniform(1.0, 3.0))
        logger.warning("Slow payment list retrieval")
    
    return jsonify(list(PAYMENTS.values()))

@app.route('/api/payments/<int:payment_id>', methods=['GET'])
def get_payment(payment_id):
    """Retrieve a specific payment by ID"""
    # Simulate processing time
    time.sleep(random.uniform(0.05, 0.1))
    
    payment = PAYMENTS.get(payment_id)
    if payment:
        return jsonify(payment)
    
    return jsonify({"error": "Payment not found"}), 404

@app.route('/api/payments/process', methods=['POST'])
def process_payment():
    """Process a new payment"""
    # Simulate payment processing
    time.sleep(random.uniform(0.2, 0.5))
    
    # Get payment details from request
    payment_data = request.get_json()
    
    # Validate payment data
    if not all(key in payment_data for key in ['user_id', 'amount', 'method']):
        return jsonify({"error": "Invalid payment details"}), 400
    
    # Simulate payment processing logic
    payment_id = len(PAYMENTS) + 1
    payment = {
        "id": payment_id,
        "user_id": payment_data['user_id'],
        "amount": payment_data['amount'],
        "method": payment_data['method'],
        "status": "pending"
    }
    
    # Simulate occasional payment failures
    if random.random() < 0.1:  # 10% chance of payment failure
        logger.warning(f"Payment processing failed for user: {payment_data['user_id']}")
        payment['status'] = "failed"
        PAYMENTS[payment_id] = payment
        return jsonify({"error": "Payment processing failed"}), 500
    
    # Mark payment as successful
    payment['status'] = "completed"
    PAYMENTS[payment_id] = payment
    
    return jsonify(payment), 201

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "payment-service"})

if __name__ == '__main__':
    # Run the Flask app
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)