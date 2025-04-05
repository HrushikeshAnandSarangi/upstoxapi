from flask import Flask, request, jsonify, Blueprint
import requests
from datetime import datetime
import os
import logging
from functools import wraps
import time
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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

# Set up rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[os.getenv('RATE_LIMIT', "100 per minute")],
    storage_uri="memory://"
)

# Blueprint for API versioning
api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')

# Upstox API configuration
API_BASE_URL = os.getenv('UPSTOX_API_URL', 'https://api.upstox.com/v2')
ACCESS_TOKEN = os.getenv('UPSTOX_ACCESS_TOKEN')

if not ACCESS_TOKEN:
    logger.warning("UPSTOX_ACCESS_TOKEN environment variable not set")

# Configuration timeout for API requests
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))  # seconds

def get_headers():
    """Generate headers for Upstox API requests"""
    return {
        'Accept': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}',
        'Api-Version': '2.0',
        'Content-Type': 'application/json'
    }

def token_required(f):
    """Decorator to check if the token is provided"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ACCESS_TOKEN:
            return jsonify({'error': 'API token is missing. Set UPSTOX_ACCESS_TOKEN environment variable.'}), 401
        return f(*args, **kwargs)
    return decorated

def handle_response(response):
    """Handle API responses and errors"""
    if response.status_code in (200, 201):
        return jsonify(response.json()), response.status_code
    
    error_data = {
        'status_code': response.status_code,
        'error': 'Unknown error'
    }
    
    try:
        error_data.update(response.json())
    except:
        error_data['error'] = response.text

    logger.error(f"API Error: {error_data}")
    return jsonify(error_data), response.status_code

@api_v1.route('/portfolio', methods=['GET'])
@token_required
@limiter.limit(os.getenv('PORTFOLIO_RATE_LIMIT', '60 per minute'))
def get_portfolio():
    """Get user's short-term positions"""
    try:
        logger.info("Fetching portfolio data")
        response = requests.get(
            f'{API_BASE_URL}/portfolio/short-term-positions',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.Timeout:
        logger.error("Timeout error fetching portfolio")
        return jsonify({'error': 'Request to Upstox API timed out'}), 504
    except requests.exceptions.ConnectionError:
        logger.error("Connection error fetching portfolio")
        return jsonify({'error': 'Failed to connect to Upstox API'}), 502
    except Exception as e:
        logger.error(f"Error fetching portfolio: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/holdings', methods=['GET'])
@token_required
@limiter.limit(os.getenv('HOLDINGS_RATE_LIMIT', '60 per minute'))
def get_holdings():
    """Get user's long-term holdings"""
    try:
        logger.info("Fetching holdings data")
        response = requests.get(
            f'{API_BASE_URL}/portfolio/long-term-holdings',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.Timeout:
        logger.error("Timeout error fetching holdings")
        return jsonify({'error': 'Request to Upstox API timed out'}), 504
    except requests.exceptions.ConnectionError:
        logger.error("Connection error fetching holdings")
        return jsonify({'error': 'Failed to connect to Upstox API'}), 502
    except Exception as e:
        logger.error(f"Error fetching holdings: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/orders', methods=['GET'])
@token_required
@limiter.limit(os.getenv('ORDERS_RATE_LIMIT', '60 per minute'))
def get_orders():
    """Get all orders"""
    try:
        logger.info("Fetching orders")
        response = requests.get(
            f'{API_BASE_URL}/order/get-orders',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.Timeout:
        logger.error("Timeout error fetching orders")
        return jsonify({'error': 'Request to Upstox API timed out'}), 504
    except requests.exceptions.ConnectionError:
        logger.error("Connection error fetching orders")
        return jsonify({'error': 'Failed to connect to Upstox API'}), 502
    except Exception as e:
        logger.error(f"Error fetching orders: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/order/<order_id>', methods=['GET'])
@token_required
def get_order(order_id):
    """Get specific order by ID"""
    try:
        logger.info(f"Fetching order: {order_id}")
        response = requests.get(
            f'{API_BASE_URL}/order/get-order/{order_id}',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error fetching order {order_id}")
        return jsonify({'error': 'Request to Upstox API timed out'}), 504
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error fetching order {order_id}")
        return jsonify({'error': 'Failed to connect to Upstox API'}), 502
    except Exception as e:
        logger.error(f"Error fetching order {order_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/buy', methods=['POST'])
@token_required
@limiter.limit(os.getenv('ORDER_RATE_LIMIT', '30 per minute'))
def buy_order():
    """Place a buy order"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        data['transaction_type'] = 'BUY'
        return place_order_internal(data)
    except Exception as e:
        logger.error(f"Error placing buy order: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/sell', methods=['POST'])
@token_required
@limiter.limit(os.getenv('ORDER_RATE_LIMIT', '30 per minute'))
def sell_order():
    """Place a sell order"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        data['transaction_type'] = 'SELL'
        return place_order_internal(data)
    except Exception as e:
        logger.error(f"Error placing sell order: {str(e)}")
        return jsonify({'error': str(e)}), 500

def place_order_internal(order_data):
    """Internal function to place orders"""
    required_fields = ['exchange', 'symbol', 'quantity', 'order_type', 'product']
    for field in required_fields:
        if field not in order_data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    order_payload = {
        "quantity": order_data.get('quantity'),
        "product": order_data.get('product'),  # CNC, INTRADAY, etc.
        "validity": order_data.get('validity', 'DAY'),
        "price": order_data.get('price', 0),
        "tag": order_data.get('tag', f"order_{datetime.now().strftime('%Y%m%d%H%M%S')}"),
        "instrument_token": order_data.get('instrument_token'),
        "symbol": order_data.get('symbol'),
        "exchange": order_data.get('exchange'),  # NSE, BSE, NFO, etc.
        "transaction_type": order_data.get('transaction_type'),  # BUY/SELL
        "order_type": order_data.get('order_type'),  # MARKET, LIMIT, SL, etc.
        "disclosed_quantity": order_data.get('disclosed_quantity', 0),
        "trigger_price": order_data.get('trigger_price', 0),
        "is_amo": order_data.get('is_amo', False)
    }

    logger.info(f"Placing {order_data.get('transaction_type')} order for {order_data.get('symbol')}")
    try:
        response = requests.post(
            f'{API_BASE_URL}/order/place',
            json=order_payload,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.Timeout:
        logger.error("Timeout error placing order")
        return jsonify({'error': 'Request to Upstox API timed out'}), 504
    except requests.exceptions.ConnectionError:
        logger.error("Connection error placing order")
        return jsonify({'error': 'Failed to connect to Upstox API'}), 502
    except Exception as e:
        logger.error(f"Error placing order: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/order', methods=['POST'])
@token_required
@limiter.limit(os.getenv('ORDER_RATE_LIMIT', '30 per minute'))
def place_order():
    """Place an order (buy/sell)"""
    try:
        order_data = request.json
        if not order_data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        return place_order_internal(order_data)
    except Exception as e:
        logger.error(f"Error placing order: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/order/<order_id>', methods=['PUT'])
@token_required
@limiter.limit(os.getenv('ORDER_RATE_LIMIT', '30 per minute'))
def modify_order(order_id):
    """Modify an existing order"""
    try:
        if not order_id:
            return jsonify({'error': 'Order ID is required'}), 400

        data = request.json
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        valid_fields = ['quantity', 'price', 'order_type', 'validity', 'disclosed_quantity', 'trigger_price']
        modified_data = {k: v for k, v in data.items() if k in valid_fields}

        if not modified_data:
            return jsonify({'error': 'No valid fields to modify'}), 400

        logger.info(f"Modifying order: {order_id}")
        response = requests.put(
            f'{API_BASE_URL}/order/modify/{order_id}',
            json=modified_data,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error modifying order {order_id}")
        return jsonify({'error': 'Request to Upstox API timed out'}), 504
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error modifying order {order_id}")
        return jsonify({'error': 'Failed to connect to Upstox API'}), 502
    except Exception as e:
        logger.error(f"Error modifying order {order_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/order/<order_id>', methods=['DELETE'])
@token_required
@limiter.limit(os.getenv('ORDER_RATE_LIMIT', '30 per minute'))
def cancel_order(order_id):
    """Cancel an existing order"""
    try:
        if not order_id:
            return jsonify({'error': 'Order ID is required'}), 400
            
        logger.info(f"Cancelling order: {order_id}")
        response = requests.delete(
            f'{API_BASE_URL}/order/cancel/{order_id}',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error cancelling order {order_id}")
        return jsonify({'error': 'Request to Upstox API timed out'}), 504
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error cancelling order {order_id}")
        return jsonify({'error': 'Failed to connect to Upstox API'}), 502
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/market-quote/<symbol>', methods=['GET'])
@token_required
@limiter.limit(os.getenv('MARKET_QUOTE_RATE_LIMIT', '120 per minute'))
def get_market_quote(symbol):
    """Get market quote for a symbol"""
    try:
        logger.info(f"Fetching market quote for: {symbol}")
        response = requests.get(
            f'{API_BASE_URL}/market-quote/{symbol}',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error fetching market quote for {symbol}")
        return jsonify({'error': 'Request to Upstox API timed out'}), 504
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error fetching market quote for {symbol}")
        return jsonify({'error': 'Failed to connect to Upstox API'}), 502
    except Exception as e:
        logger.error(f"Error fetching market quote for {symbol}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_v1.route('/funds', methods=['GET'])
@token_required
@limiter.limit(os.getenv('FUNDS_RATE_LIMIT', '30 per minute'))
def get_funds():
    """Get user's funds and margins"""
    try:
        logger.info("Fetching funds and margins")
        response = requests.get(
            f'{API_BASE_URL}/user/get-funds-and-margin',
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT
        )
        return handle_response(response)
    except requests.exceptions.Timeout:
        logger.error("Timeout error fetching funds")
        return jsonify({'error': 'Request to Upstox API timed out'}), 504
    except requests.exceptions.ConnectionError:
        logger.error("Connection error fetching funds")
        return jsonify({'error': 'Failed to connect to Upstox API'}), 502
    except Exception as e:
        logger.error(f"Error fetching funds: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """API health check endpoint"""
    health_data = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.1.0',
        'environment': os.getenv('FLASK_ENV', 'production'),
        'upstox_api': 'unconfigured' if not ACCESS_TOKEN else 'configured'
    }
    
    # Basic check if we can connect to Upstox API
    if ACCESS_TOKEN:
        try:
            requests.get(
                f'{API_BASE_URL}/user/profile',
                headers=get_headers(),
                timeout=5  # Short timeout for health check
            )
            health_data['upstox_api_status'] = 'connected'
        except:
            health_data['upstox_api_status'] = 'disconnected'
    
    return jsonify(health_data)

# Register blueprint
app.register_blueprint(api_v1)

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found', 'path': request.path}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed', 'method': request.method, 'path': request.path}), 405

@app.errorhandler(429)
def ratelimit_handler(error):
    return jsonify({'error': 'Rate limit exceeded', 'message': str(error)}), 429

@app.errorhandler(500)
def internal_server_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')
    
    logger.info(f"Starting Upstox API server on port {port} (debug={debug})")
    
    # Use gunicorn for production deployment if available
    if os.getenv('USE_GUNICORN', 'False').lower() in ('true', '1', 't'):
        # This block will execute if you're using gunicorn to run the app
        # gunicorn command: gunicorn --bind 0.0.0.0:$PORT app:app
        pass
    else:
        # For local development or simple deployments
        app.run(host='0.0.0.0', port=port, debug=debug)