from flask import Flask, request, jsonify, Blueprint
import requests
from datetime import datetime
import os
import logging
from functools import wraps

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
ACCESS_TOKEN = os.getenv('UPSTOX_ACCESS_TOKEN','eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI2VkJGNlYiLCJqdGkiOiI2N2YxMzQ3NmQxOWRlNzJiZWNjNGNlNDkiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaWF0IjoxNzQzODYwODU0LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NDM4OTA0MDB9.VO64nBhf3bDpJuh1BpBdsdBm9WMZ78Qj_PdCUq39vdE')
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))  # seconds

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

@api_v1.route('/profile', methods=['GET'])
@token_required
def get_profile():
    """Get account holder's profile information"""
    try:
        response = requests.get(
            f'{API_BASE_URL}/user/profile',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        
        if response.status_code == 200:
            profile_data = response.json()
            return jsonify({
                'name': profile_data.get('data', {}).get('user_name'),
                'email': profile_data.get('data', {}).get('email'),
                'exchanges': profile_data.get('data', {}).get('exchanges')
            }), 200
        return handle_response(response)
    except requests.exceptions.RequestException as e:
        logger.error(f"Profile error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/portfolio', methods=['GET'])
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

@api_v1.route('/holdings', methods=['GET'])
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

@api_v1.route('/orders', methods=['GET'])
@token_required
def get_orders():
    """Get order list"""
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

@api_v1.route('/order/<order_id>', methods=['GET'])
@token_required
def get_order(order_id):
    """Get order details"""
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

@api_v1.route('/order/place', methods=['POST'])
@token_required
def place_order():
    """Place new order"""
    try:
        data = request.json
        required_fields = ['instrument_token', 'quantity', 'order_type', 'product', 'transaction_type']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing {field}'}), 400

        if data['product'] not in PRODUCT_MAP:
            return jsonify({'error': 'Invalid product type'}), 400

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
        return handle_response(response)
    except Exception as e:
        logger.error(f"Place order error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/order/modify', methods=['PUT'])
@token_required
def modify_order():
    """Modify existing order"""
    try:
        data = request.json
        if 'order_id' not in data:
            return jsonify({'error': 'Missing order_id'}), 400

        valid_fields = ['quantity', 'price', 'order_type', 'validity', 
                       'disclosed_quantity', 'trigger_price', 'product']
        modified_data = {k: v for k, v in data.items() if k in valid_fields}

        if 'product' in modified_data:
            if modified_data['product'] not in PRODUCT_MAP:
                return jsonify({'error': 'Invalid product type'}), 400
            modified_data['product'] = PRODUCT_MAP[modified_data['product']]

        logger.info(f"Modifying order {data['order_id']}: {modified_data}")
        response = requests.put(
            f'{API_BASE_URL}/order/modify',
            json={'order_id': data['order_id'], **modified_data},
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except Exception as e:
        logger.error(f"Modify order error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/order/cancel', methods=['DELETE'])
@token_required
def cancel_order():
    """Cancel order"""
    try:
        order_id = request.args.get('order_id')
        if not order_id:
            return jsonify({'error': 'Missing order_id'}), 400

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

@api_v1.route('/market-quote', methods=['GET'])
@token_required
def get_market_quote():
    """Get market quotes"""
    try:
        instrument_key = request.args.get('instrument_key')
        if not instrument_key:
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

@api_v1.route('/funds', methods=['GET'])
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
            status['upstox_status'] = f'error: {str(e)}'
    
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