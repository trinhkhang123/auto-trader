from flask import Flask, request, jsonify
from trading_bot import TradingBot
import logging
from datetime import datetime
import threading
from flask_cors import CORS
import os
# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/trading_api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

env = os.getenv('EVN', 'testnet')
bot = TradingBot(testnet=(env == 'testnet'))

# Khởi động WebSocket tự động khi ứng dụng bắt đầu
try:
    websocket_thread = threading.Thread(target=bot.start_websocket)
    websocket_thread.daemon = True
    websocket_thread.start()
    logger.info("WebSocket started automatically on application startup")
except Exception as e:
    logger.error(f"Error starting WebSocket on application startup: {str(e)}")

@app.route('/api/v1/order_best', methods=['POST'])
def create_order_best():
    """API để lấy danh sách lệnh giao dịch."""
    try:
        data = request.get_json()
        required_fields = ['asset', 'position', 'entry1', 'strategy_type', 'leverage', 'tp1', 'stoploss', 'bot', 'tp2', 'tp3']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        signal = {
            'asset': data['asset'],
            'position': data['position'],
            'entry1': float(data['entry1']),
            'strategy_type': data['strategy_type'],
            'leverage': int(data['leverage']),
            'tp1': float(data['tp1']),
            'tp2': float(data['tp2']),
            'tp3': float(data['tp3']),
            'stoploss': float(data['stoploss']),
            'bot': data['bot']
        }

        result = bot.create_order_best(signal,'best')
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 201

    except Exception as e:
        logger.error(f"Error in create_order_best API: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/order_ema', methods=['POST'])
def create_order_ema():
    """API để lấy danh sách lệnh giao dịch."""
    try:
        data = request.get_json()
        required_fields = ['asset', 'position', 'entry1', 'strategy_type', 'leverage', 'tp1', 'stoploss', 'bot', 'tp2', 'tp3']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        signal = {
            'asset': data['asset'],
            'position': data['position'],
            'entry1': float(data['entry1']),
            'strategy_type': data['strategy_type'],
            'leverage': int(data['leverage']),
            'tp1': float(data['tp1']),
            'tp2': float(data['tp2']),
            'tp3': float(data['tp3']),
            'stoploss': float(data['stoploss']),
            'bot': data['bot']
        }

        result = bot.create_order_best(signal,'ema')
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 201

    except Exception as e:
        logger.error(f"Error in create_order_ema API: {str(e)}")
        return jsonify({'error': str(e)}), 500
@app.route('/api/v1/orders', methods=['POST'])
def create_order():
    """API để tạo lệnh giao dịch mới."""
    try:
        data = request.get_json()
        required_fields = ['symbol', 'side', 'entry', 'strategy_type', 'leverage', 'tp1_price', 'sl_price', 'bot_name', 'tp2_price']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        signal = {
            'symbol': data['symbol'],
            'side': data['side'],
            'entry': float(data['entry']),
            'strategy_type': data['strategy_type'],
            'leverage': int(data['leverage']),
            'tp1_price': float(data['tp1_price']),
            'tp2_price': float(data['tp2_price']),
            'sl_price': float(data['sl_price']),
            'bot_name': data['bot_name']
        }

        result = bot.create_order(signal)
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 201

    except Exception as e:
        logger.error(f"Error in create_order API: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/orders/<int:trade_id>/status', methods=['GET'])
def check_order_status(trade_id):
    """API để kiểm tra trạng thái lệnh."""
    try:
        status = bot.check_order_status(trade_id)
        if status == 'NOT_FOUND':
            return jsonify({'error': 'Trade not found'}), 404
        return jsonify({'trade_id': trade_id, 'status': status}), 200

    except Exception as e:
        logger.error(f"Error in check_order_status API: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/positions/<int:trade_id>', methods=['PUT'])
def update_position(trade_id):
    """API để cập nhật trạng thái vị thế dựa trên giá thị trường."""
    try:
        data = request.get_json()
        if 'current_price' not in data:
            return jsonify({'error': 'Missing current_price'}), 400

        current_price = float(data['current_price'])
        result = bot.update_position(trade_id, current_price)
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in update_position API: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/positions/<int:trade_id>/stoploss', methods=['PUT'])
def update_stoploss(trade_id):
    """API để cập nhật stoploss cho giao dịch."""
    try:
        data = request.get_json()
        if 'new_sl' not in data:
            return jsonify({'error': 'Missing new_sl'}), 400

        new_sl = float(data['new_sl'])
        success = bot.update_stoploss(trade_id, new_sl)
        if not success:
            return jsonify({'error': 'Failed to update stoploss'}), 400
        return jsonify({'message': f'Stoploss updated to {new_sl} for trade {trade_id}'}), 200

    except Exception as e:
        logger.error(f"Error in update_stoploss API: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/positions/<int:trade_id>/close', methods=['POST'])
def close_position(trade_id):
    """API để đóng một phần hoặc toàn bộ vị thế."""
    try:
        data = request.get_json()
        percentage = float(data.get('percentage', 1.0))
        if percentage <= 0 or percentage > 1:
            return jsonify({'error': 'Percentage must be between 0 and 1'}), 400

        trade = bot.get_trade_by_id(trade_id)
        if not trade:
            return jsonify({'error': 'Trade not found'}), 404

        ticker = bot.client.get_tickers(category='linear', symbol=trade['symbol'])
        if ticker['retCode'] != 0:
            return jsonify({'error': 'Failed to get current price'}), 500
        current_price = float(ticker['result']['list'][0]['lastPrice'])

        success = bot.close_position(trade_id, percentage, current_price)
        if not success:
            return jsonify({'error': 'Failed to close position'}), 400
        return jsonify({'message': f'Closed {percentage*100}% of position for trade {trade_id}'}), 200

    except Exception as e:
        logger.error(f"Error in close_position API: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/trades/<int:trade_id>', methods=['GET'])
def get_trade(trade_id):
    """API để lấy thông tin giao dịch."""
    try:
        trade = bot.get_trade_by_id(trade_id)
        if not trade:
            return jsonify({'error': 'Trade not found'}), 404
        return jsonify({
            'id': trade['id'],
            'order_id': trade['order_id'],
            'symbol': trade['symbol'],
            'side': trade['side'],
            'entry_price': float(trade['entry_price']) if trade['entry_price'] is not None else None,
            'quantity': float(trade['quantity']) if trade['quantity'] is not None else None,
            'position_size': float(trade['position_size']) if trade['position_size'] is not None else None,
            'leverage': int(trade['leverage']) if trade['leverage'] is not None else None,
            'tp1_price': float(trade['tp1_price']) if trade['tp1_price'] is not None else None,
            'tp2_price': float(trade['tp2_price']) if trade['tp2_price'] is not None else None,
            'tp3_price': float(trade['tp3_price']) if trade['tp3_price'] is not None else None,
            'sl_price': float(trade['sl_price']) if trade['sl_price'] is not None else None,
            'current_sl': float(trade['current_sl']) if trade['current_sl'] is not None else None,
            'current_tp': float(trade['current_tp']) if trade['current_tp'] is not None else None,
            'strategy_type': trade['strategy_type'],
            'status': trade['status'],
            'bot_name': trade['bot_name'] if trade['bot_name'] is not None else 'N/A',
            'pnl': float(trade['pnl']) if trade['pnl'] is not None else None,
            'pnl_percent': float(trade['pnl_percent']) if trade['pnl_percent'] is not None else None,
            'filled_at': trade['filled_at'].isoformat() if trade['filled_at'] is not None else None,
            'closed_at': trade['closed_at'].isoformat() if trade['closed_at'] is not None else None,
            'updated_at': trade['updated_at'].isoformat() if trade['updated_at'] is not None else None
        }), 200

    except Exception as e:
        logger.error(f"Error in get_trade API: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/websocket/start', methods=['POST'])
def start_websocket():
    """API để khởi động WebSocket."""
    try:
        thread = threading.Thread(target=bot.start_websocket)
        thread.daemon = True
        thread.start()
        logger.info("WebSocket started via API")
        return jsonify({'message': 'WebSocket started successfully'}), 200

    except Exception as e:
        logger.error(f"Error in start_websocket API: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/health', methods=['GET'])
def health_check():
    """API để kiểm tra trạng thái bot."""
    try:
        # Kiểm tra kết nối với Bybit
        account_info = bot.get_account_info()
        return jsonify({
            'status': 'running',
            'exchange': 'bybit',
            'testnet': bot.testnet,
            'account_info': account_info
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/balance', methods=['GET'])
def get_balance():
    """API để lấy thông tin số dư tài khoản."""
    try:
        # Lấy thông tin tài khoản
        account_info = bot.get_account_info()
        
        # Lấy thông tin vị thế hiện tại
        positions = bot.get_positions()
        
        # Tính tổng ký quỹ đã sử dụng
        used_margin = sum(
            float(pos.get('position_margin', 0)) 
            for pos in positions 
            if pos.get('position_margin')
        )
        
        # Trả về thông tin số dư
        return jsonify({
            'success': True,
            'available_balance': float(account_info.get('available_balance', 0)),
            'equity': float(account_info.get('total_equity', 0)),
            'used_margin': used_margin,
            'wallet_balance': float(account_info.get('wallet_balance', 0)),
            'currency': 'USDT'
        })
    except Exception as e:
        logger.error(f"Error getting balance: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Không thể lấy số dư tài khoản: {str(e)}'
        }), 500

@app.route('/api/v1/trades', methods=['GET'])
def get_trades():
    """API để lấy danh sách lệnh giao dịch với bộ lọc bot_nasme và status."""
    try:
        bot_name = request.args.get('bot_name', '')
        status = request.args.get('status', '')

        # Lấy tất cả lệnh từ hàm get_trade
        trades = bot.get_all_orders()


        # Áp dụng bộ lọc
        filtered_trades = trades
        if bot_name:
            filtered_trades = [trade for trade in filtered_trades if bot_name.lower() in trade['bot_name'].lower()]
        if status:
            if status == 'all':
                filtered_trades = trades
            else:
                filtered_trades = [trade for trade in filtered_trades if trade['status'] == status]

        logger.info(f"Retrieved {len(filtered_trades)} trades with filters bot_name='{bot_name}', status='{status}'")
        return jsonify(filtered_trades), 200

    except Exception as e:
        logger.error(f"Error fetching trades: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/cancel_order', methods=['POST'])
def cancel_order():
    """API để hủy lệnh giao dịch."""
    try:
        data = request.get_json()
        if 'symbol' not in data or 'orderId' not in data:
            return jsonify({'error': 'Missing symbol or orderId'}), 400
        symbol = data['symbol']
        orderId = data['orderId']
        result = bot.cancel_order(symbol, orderId)
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error canceling order: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Flask starting...")  # thêm dòng này
    app.run(host='0.0.0.0', port=5001, debug=True)