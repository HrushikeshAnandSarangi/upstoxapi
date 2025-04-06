from flask import Flask, request, jsonify, Blueprint, redirect, url_for
import requests
from datetime import datetime
import os
import logging
from functools import wraps
import json
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("api.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Blueprint for API versioning
api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')

# Upstox API configuration
API_BASE_URL = os.getenv('UPSTOX_API_URL', 'https://api.upstox.com/v2')
ACCESS_TOKEN = 'eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI2VkJGNlYiLCJqdGkiOiI2N2YxMzQ3NmQxOWRlNzJiZWNjNGNlNDkiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaWF0IjoxNzQzODYwODU0LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NDM4OTA0MDB9.VO64nBhf3bDpJuh1BpBdsdBm9WMZ78Qj_PdCUq39vdE'  # Replace with your actual access token
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))
# Use the correct Upstox add funds URL
UPSTOX_FUNDS_URL = os.getenv('UPSTOX_FUNDS_URL', 'https://upstox.com/funds/add')

if not ACCESS_TOKEN:
    logger.warning("UPSTOX_ACCESS_TOKEN environment variable not set")

# Product type mapping
PRODUCT_MAP = {
    'CNC': 'D',
    'INTRADAY': 'I',
    'MIS': 'MIS',
    'CO': 'CO',
    'BO': 'BO'
}

def get_headers():
    """Generate headers for Upstox API requests"""
    return {
        'Accept': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}',
        'Api-Version': '2.0'
    }

def token_required(f):
    """Decorator to check if the token is provided"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ACCESS_TOKEN:
            return jsonify({'error': 'Missing API token'}), 401
        return f(*args, **kwargs)
    return decorated

def handle_response(response):
    """Handle API responses and errors"""
    if response.status_code in (200, 201):
        return jsonify(response.json()), response.status_code
    
    try:
        error_data = response.json()
        error_msg = error_data.get('error', {}).get('message', 'Unknown error')
    except:
        error_msg = response.text or 'Unknown error'

    logger.error(f"API Error ({response.status_code}): {error_msg}")
    return jsonify({
        'status': 'error',
        'code': response.status_code,
        'message': error_msg
    }), response.status_code

def validate_instrument(instrument_token):
    """Validate instrument token before placing order"""
    try:
        response = requests.get(
            f'{API_BASE_URL}/market-quote/quotes',
            params={'instrument_key': instrument_token},
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        
        if response.status_code != 200:
            return False, "Invalid instrument token"
        
        return True, None
    except Exception as e:
        logger.error(f"Instrument validation error: {str(e)}")
        return False, str(e)

def check_sufficient_funds(transaction_type, instrument_token, quantity, price=0):
    """Check if sufficient funds are available for the transaction"""
    try:
        # Get current stock quote for market orders
        if price == 0:
            quote_response = requests.get(
                f'{API_BASE_URL}/market-quote/quotes',
                params={'instrument_key': instrument_token},
                headers=get_headers(),
                timeout=REQUEST_TIMEOUT
            )
            
            if quote_response.status_code != 200:
                return False, "Failed to get stock quote"
                
            quote_data = quote_response.json().get('data', {})
            last_price = quote_data.get(instrument_token, {}).get('last_price', 0)
            price = last_price if last_price > 0 else 1000  # Default if can't get price
        
        # Calculate estimated cost
        estimated_cost = quantity * price
        
        # Only check funds for buy orders
        if transaction_type.upper() == "BUY":
            # Get available funds
            funds_response = requests.get(
                f'{API_BASE_URL}/user/get-funds-and-margin',
                headers=get_headers(),
                timeout=REQUEST_TIMEOUT
            )
            
            if funds_response.status_code != 200:
                return False, "Failed to get funds information"
                
            funds_data = funds_response.json().get('data', {})
            available_funds = funds_data.get('equity', {}).get('available_margin', 0)
            
            if available_funds < estimated_cost:
                return False, f"Insufficient funds. Required: {estimated_cost}, Available: {available_funds}"
        
        return True, None
    except Exception as e:
        logger.error(f"Funds check error: {str(e)}")
        return False, str(e)

@app.route('/')
def hello_world():
    return "Hello, World! This is the root of the application."

@app.route('/order', methods=['POST'])
@token_required
def order():
    """Basic order endpoint for backward compatibility"""
    try:
        instrument_token = "NSE_EQ|INE848E01016"
        
        # Validate the instrument token
        is_valid, error_msg = validate_instrument(instrument_token)
        if not is_valid:
            return jsonify({'error': f'Invalid instrument: {error_msg}'}), 400
        
        # Check if sufficient funds are available
        has_funds, funds_error = check_sufficient_funds("BUY", instrument_token, 1)
        
        payload = json.dumps({
            "quantity": 1,
            "product": "D",
            "validity": "DAY",
            "price": 0,
            "tag": "string",
            "instrument_token": instrument_token,
            "order_type": "MARKET",
            "transaction_type": "BUY",
            "disclosed_quantity": 0,
            "trigger_price": 0,
            "is_amo": False
        })
        headers = {
            'Content-Type': 'application/json',
            **get_headers()
        }

        # If insufficient funds, redirect to add funds page
        if not has_funds:
            funds_url = f"{UPSTOX_FUNDS_URL}?reason=insufficient_funds&error={funds_error}"
            return jsonify({
                'status': 'redirect',
                'message': funds_error,
                'redirect_url': funds_url
            }), 303  # Status 303 See Other
        
        response = requests.post(f"{API_BASE_URL}/order/place", headers=headers, data=payload)
        
        if response.status_code in (200, 201):
            result = response.json()
            order_id = result.get('data', {}).get('order_id')
            
            return jsonify({
                'status': 'success',
                'message': 'Order initiated successfully',
                'order_data': result
            })
        
        return handle_response(response)
    
    except Exception as e:
        logger.error(f"Order error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/profile', methods=['GET'])
@token_required
def get_profile():
    """Get account holder's profile information"""
    try:
        response = requests.get(
            f'{API_BASE_URL}/user/profile',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.RequestException as e:
        logger.error(f"Profile error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/portfolio', methods=['GET'])
@token_required
def get_portfolio():
    """Get portfolio holdings"""
    try:
        response = requests.get(
            f'{API_BASE_URL}/portfolio/short-term-positions',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.RequestException as e:
        logger.error(f"Portfolio error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/holdings', methods=['GET'])
@token_required
def get_holdings():
    """Get long-term holdings"""
    try:
        response = requests.get(
            f'{API_BASE_URL}/portfolio/long-term-holdings',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.RequestException as e:
        logger.error(f"Holdings error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/orders', methods=['GET'])
@token_required
def get_orders():
    """Get all orders"""
    try:
        response = requests.get(
            f'{API_BASE_URL}/order/retrieve/all',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.RequestException as e:
        logger.error(f"Orders error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/orders/<order_id>', methods=['GET'])
@token_required
def get_order(order_id):
    """Get specific order details"""
    try:
        response = requests.get(
            f'{API_BASE_URL}/order/details',
            params={'order_id': order_id},
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.RequestException as e:
        logger.error(f"Order details error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/orders', methods=['POST'])
@token_required
def place_order():
    """Place new order with funds check and potential redirection"""
    try:
        data = request.json
        required_fields = ['instrument_token', 'quantity', 'order_type', 'product', 'transaction_type']
        
        if missing := [field for field in required_fields if field not in data]:
            return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

        if data['product'] not in PRODUCT_MAP:
            return jsonify({'error': 'Invalid product type'}), 400
            
        # Validate the instrument token before placing order
        is_valid, error_msg = validate_instrument(data['instrument_token'])
        if not is_valid:
            return jsonify({'error': f'Invalid instrument: {error_msg}'}), 400
            
        # For buy orders, check if sufficient funds are available
        if data['transaction_type'].upper() == "BUY":
            has_funds, funds_error = check_sufficient_funds(
                data['transaction_type'], 
                data['instrument_token'], 
                data['quantity'], 
                data.get('price', 0)
            )
            
            # If insufficient funds, redirect to add funds page
            if not has_funds:
                funds_url = f"{UPSTOX_FUNDS_URL}?reason=insufficient_funds&error={funds_error}&instrument={data['instrument_token']}"
                return jsonify({
                    'status': 'redirect',
                    'message': funds_error,
                    'redirect_url': funds_url
                }), 303  # Status 303 See Other

        payload = {
            "quantity": data['quantity'],
            "product": PRODUCT_MAP[data['product']],
            "validity": data.get('validity', 'DAY'),
            "price": data.get('price', 0),
            "tag": data.get('tag', 'AUTO_FLASK'),
            "instrument_token": data['instrument_token'],
            "order_type": data['order_type'],
            "transaction_type": data['transaction_type'],
            "disclosed_quantity": data.get('disclosed_quantity', 0),
            "trigger_price": data.get('trigger_price', 0),
            "is_amo": data.get('is_amo', False)
        }

        logger.info(f"Placing {data['transaction_type']} order: {payload}")
        response = requests.post(
            f'{API_BASE_URL}/order/place',
            json=payload,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        
        if response.status_code in (200, 201):
            result = response.json()
            return jsonify({
                'status': 'success',
                'message': f"{data['transaction_type']} order placed successfully",
                'order_data': result
            })
        
        return handle_response(response)
    except Exception as e:
        logger.error(f"Place order error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/funds/add', methods=['GET'])
@token_required
def redirect_to_add_funds():
    """Redirect to Upstox add funds page"""
    reason = request.args.get('reason', 'general')
    instrument = request.args.get('instrument', '')
    
    # Construct URL to Upstox add funds page
    funds_url = f"{UPSTOX_FUNDS_URL}?source=api&reason={reason}"
    if instrument:
        funds_url += f"&instrument={instrument}"
    
    return redirect(funds_url)

@app.route('/orders/<order_id>', methods=['PUT'])
@token_required
def modify_order(order_id):
    """Modify existing order"""
    try:
        data = request.json
        valid_fields = ['quantity', 'price', 'order_type', 'validity', 
                       'disclosed_quantity', 'trigger_price', 'product']
        modified_data = {k: v for k, v in data.items() if k in valid_fields}

        if 'product' in modified_data:
            if modified_data['product'] not in PRODUCT_MAP:
                return jsonify({'error': 'Invalid product type'}), 400
            modified_data['product'] = PRODUCT_MAP[modified_data['product']]

        # Get original order details to check transaction type
        order_response = requests.get(
            f'{API_BASE_URL}/order/details',
            params={'order_id': order_id},
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        
        if order_response.status_code != 200:
            return jsonify({'error': 'Failed to retrieve original order details'}), 500
            
        order_data = order_response.json().get('data', {})
        transaction_type = order_data.get('transaction_type', '')
        instrument_token = order_data.get('instrument_token', '')
        
        # For buy orders and quantity increases, check if sufficient funds are available
        if (transaction_type.upper() == "BUY" and 
            ('quantity' in modified_data or 'price' in modified_data)):
            
            # Get the new quantity or use original
            new_quantity = modified_data.get('quantity', order_data.get('quantity', 0))
            new_price = modified_data.get('price', order_data.get('price', 0))
            
            has_funds, funds_error = check_sufficient_funds(
                transaction_type, 
                instrument_token, 
                new_quantity, 
                new_price
            )
            
            # If insufficient funds, redirect to add funds page
            if not has_funds:
                funds_url = f"{UPSTOX_FUNDS_URL}?reason=insufficient_funds&error={funds_error}&instrument={instrument_token}&order_id={order_id}"
                return jsonify({
                    'status': 'redirect',
                    'message': funds_error,
                    'redirect_url': funds_url
                }), 303  # Status 303 See Other

        logger.info(f"Modifying order {order_id}: {modified_data}")
        response = requests.put(
            f'{API_BASE_URL}/order/modify',
            json={'order_id': order_id, **modified_data},
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        
        return handle_response(response)
    except Exception as e:
        logger.error(f"Modify order error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/orders/<order_id>', methods=['DELETE'])
@token_required
def cancel_order(order_id):
    """Cancel order"""
    try:
        logger.info(f"Cancelling order {order_id}")
        response = requests.delete(
            f'{API_BASE_URL}/order/cancel',
            params={'order_id': order_id},
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except Exception as e:
        logger.error(f"Cancel order error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/market-quote', methods=['GET'])
@token_required
def get_market_quote():
    """Get market quotes"""
    try:
        if not (instrument_key := request.args.get('instrument_key')):
            return jsonify({'error': 'Missing instrument_key'}), 400

        response = requests.get(
            f'{API_BASE_URL}/market-quote/quotes',
            params={'instrument_key': instrument_key},
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.RequestException as e:
        logger.error(f"Market quote error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/funds', methods=['GET'])
@token_required
def get_funds():
    """Get available funds"""
    try:
        response = requests.get(
            f'{API_BASE_URL}/user/get-funds-and-margin',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.RequestException as e:
        logger.error(f"Funds error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    status = {
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'upstox_configured': bool(ACCESS_TOKEN)
    }
    
    if ACCESS_TOKEN:
        try:
            requests.get(
                f'{API_BASE_URL}/user/profile',
                headers=get_headers(),
                timeout=3
            )
            status['upstox_status'] = 'connected'
        except Exception as e:
            status['upstox_status'] = f'connection error: {str(e)}'
    
    return jsonify(status)

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal error: {str(e)}")
    return jsonify({'error': 'Internal server error'}), 500

# Register blueprint
app.register_blueprint(api_v1)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)