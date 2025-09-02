import os
import threading
from typing import Dict, Any, List
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
import mysql.connector
from mysql.connector import Error
import logging
from datetime import datetime
import time
import json
import signal
import sys
import uuid
import random
import math
import schedule
from datetime import timedelta
# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

class TradingBot:
    def __init__(self, testnet: bool = True):
        """Khởi tạo bot với kết nối Bybit API, WebSocket và MySQL."""
        self.running = True
        self.testnet = testnet
        try:
            self.client = HTTP(
                testnet=testnet,
                api_key=os.getenv('BYBIT_API_KEY'),
                api_secret=os.getenv('BYBIT_API_SECRET')
            )
            self.db_config = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'user': os.getenv('DB_USER', 'homestead'),
                'password': os.getenv('DB_PASSWORD', 'secret'),
                'database': os.getenv('DB_NAME', 'auto_trader'),
                'pool_name': 'trading_pool',
                'pool_size': 5,
                'pool_reset_session': True,
                'autocommit': True
            }
            self.db_pool = None
            self.init_db_pool()
            ws_endpoint = 'wss://stream-testnet.bybit.com/v5/public/linear' if testnet else 'wss://stream.bybit.com/v5/public/linear'
            self.ws = WebSocket(
                testnet=testnet,
                channel_type='linear'
            )
            ws_endpoint_private = 'wss://stream-testnet.bybit.com/v5/private' if testnet else 'wss://stream.bybit.com/v5/private'
            print(ws_endpoint_private, testnet)
            self.ws_private = WebSocket(
                testnet=testnet,
                channel_type='private',
                api_key=os.getenv('BYBIT_API_KEY'),
                api_secret=os.getenv('BYBIT_API_SECRET')
            )
            self.active_trades = {}
            signal.signal(signal.SIGINT, self.shutdown)
            signal.signal(signal.SIGTERM, self.shutdown)
            logger.info("TradingBot initialized successfully")
            self.schedule_jobs()
            # Khởi động luồng cho schedule
            self.start_schedule_thread()
        except Exception as e:
            logger.error(f"Initialization error: {str(e)}")
            raise

    def get_account_balance(self, account_type: str = 'UNIFIED') -> Dict[str, Any]:
        """
        Lấy thông tin số dư tài khoản
        
        Args:
            account_type: Loại tài khoản (UNIFIED, CONTRACT, SPOT)
            
        Returns:
            Dict chứa thông tin số dư tài khoản
        """
        try:
            response = self.client.get_wallet_balance(
                accountType=account_type,
                coin="USDT"
            )
            
            if response.get('retCode') == 0:
                result = response.get('result', {})
                if self.testnet:
                    balance_info = result.get('list', [{}])[0].get('coin', [{}])[0]
                else:
                    balance_info = result.get('list', [{}])[0].get('coin', [{}])[0]
                
                return {
                    'equity': float(balance_info.get('equity', 0)),
                    'available_balance': float(balance_info.get('availableToWithdraw', 0)),
                    'used_margin': float(balance_info.get('usedMargin', 0)),
                    'order_margin': float(balance_info.get('orderMargin', 0)),
                    'position_margin': float(balance_info.get('positionMargin', 0)),
                    'wallet_balance': float(balance_info.get('walletBalance', 0))
                }
            else:
                logger.error(f"Lỗi khi lấy số dư tài khoản: {response.get('retMsg')}")
                return {}
                
        except Exception as e:
            logger.error(f"Lỗi trong quá trình lấy số dư tài khoản: {str(e)}")
            return {}

    def init_db_pool(self):
        """Khởi tạo connection pool cho database."""
        try:
            # Lấy các tham số cấu hình từ db_config
            db_config = self.db_config.copy()
            pool_name = db_config.pop('pool_name')
            pool_size = db_config.pop('pool_size')
            
            # Tạo connection pool
            self.db_pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name=pool_name,
                pool_size=pool_size,
                **db_config
            )
            logger.info(f"Initialized MySQL connection pool with {pool_size} connections")
        except Error as e:
            logger.error(f"Error initializing database pool: {str(e)}")
            raise

    def get_db_connection(self, retries=3, delay=1):
        """Lấy kết nối từ pool với cơ chế retry tự động."""
        attempt = 0
        last_exception = None
        
        while attempt < retries:
            try:
                connection = self.db_pool.get_connection()
                if connection.is_connected():
                    return connection
            except Error as e:
                last_exception = e
                logger.warning(f"Failed to get database connection (attempt {attempt + 1}/{retries}): {str(e)}")
                time.sleep(delay)
                attempt += 1
        
        logger.error(f"Failed to get database connection after {retries} attempts")
        if last_exception:
            raise last_exception
        raise Error("Failed to get database connection")

    def execute_query(self, query, params=None, fetch=True, commit=False, max_retries=3, retry_delay=1):
        """
        Thực thi câu query với kết nối từ pool.
        
        Args:
            query (str): Câu lệnh SQL cần thực thi
            params (tuple, optional): Các tham số cho câu lệnh SQL
            fetch (bool): Có lấy kết quả trả về hay không
            commit (bool): Có commit transaction hay không
            max_retries (int): Số lần thử lại tối đa khi gặp lỗi
            retry_delay (int): Thời gian chờ giữa các lần thử lại (giây)
            
        Returns:
            Kết quả trả về phụ thuộc vào tham số fetch:
            - Nếu fetch=True và có kết quả: list các dict
            - Nếu fetch=False: số dòng bị ảnh hưởng hoặc lastrowid
            - None nếu không có kết quả
            
        Raises:
            Exception: Khi vượt quá số lần thử lại hoặc lỗi nghiêm trọng
        """
        attempt = 0
        last_exception = None
        
        while attempt < max_retries:
            connection = None
            cursor = None
            try:
                # Lấy kết nối từ pool
                connection = self.get_db_connection()
                cursor = connection.cursor(dictionary=True)
                
                # Thực thi câu lệnh
                cursor.execute(query, params or ())
                
                # Commit nếu được yêu cầu
                if commit:
                    connection.commit()
                    
                # Xử lý kết quả trả về
                if fetch:
                    if cursor.with_rows:
                        result = cursor.fetchall()
                        return result if result else None
                    return None
                    
                # Trả về ID của bản ghi vừa insert (nếu có)
                if cursor.lastrowid:
                    return cursor.lastrowid
                    
                # Trả về số dòng bị ảnh hưởng
                return cursor.rowcount
                
            except (mysql.connector.errors.OperationalError, 
                   mysql.connector.errors.InterfaceError) as e:
                # Ghi log lỗi kết nối
                last_exception = e
                logger.warning(f"Database connection error (attempt {attempt + 1}/{max_retries}): {str(e)}")
                
                # Rollback nếu có lỗi
                if connection and connection.is_connected():
                    try:
                        connection.rollback()
                    except:
                        pass
                
                # Tăng số lần thử lại
                attempt += 1
                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)  # Tăng dần thời gian chờ
                
            except Exception as e:
                # Ghi log lỗi khác
                logger.error(f"Error executing query: {str(e)}")
                if connection and connection.is_connected():
                    try:
                        connection.rollback()
                    except:
                        pass
                raise
                
            finally:
                # Luôn đóng cursor và connection
                if cursor:
                    try:
                        cursor.close()
                    except:
                        pass
                
                if connection and connection.is_connected():
                    try:
                        connection.close()
                    except:
                        pass
        
        # Nếu vượt quá số lần thử lại
        error_msg = f"Failed to execute query after {max_retries} attempts"
        logger.error(error_msg)
        if last_exception:
            raise type(last_exception)(f"{error_msg}: {str(last_exception)}")
        raise Exception(error_msg)

    def __del__(self):
        """Đóng tất cả kết nối khi hủy đối tượng."""
        if hasattr(self, 'ws'):
            self.ws.exit()
        if hasattr(self, 'ws_private'):
            self.ws_private.exit()
            logger.info("WebSocket connections closed")
        logger.info("TradingBot shutdown completed")

    def cancel_order(self, symbol: str, orderId: str) -> Dict[str, Any]:
        """Hủy lệnh giao dịch trên Bybit."""
        try:
            response = self.client.cancel_order(
                category='linear',
                symbol=symbol,
                orderId=orderId
            )
            if response.get('retCode', 0) == 0:
                logger.info(f"Cancelled order {orderId} for {symbol}")
            else:
                logger.warning(f"Failed to cancel order {orderId} for {symbol}: {response.get('retMsg', 'Lỗi không xác định')}")
            return response
        except Exception as e:
            logger.error(f"Error cancelling order: {str(e)}")
            return {}
    def create_order(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo lệnh giao dịch trên Bybit với Take Profit và Stop Loss."""
        try:
            if signal['strategy_type'] not in ['strategy1', 'strategy2']:
                raise ValueError("Invalid strategy_type. Must be 'strategy1' or 'strategy2'")
            position_size = 30 if signal['strategy_type'] == 'strategy1' else 10
            quantity = position_size / signal['entry'] * 0.25

            side = signal.get('side', 'Buy').capitalize()
            if side not in ['Buy', 'Sell']:
                raise ValueError("Side must be either 'Buy' or 'Sell'")
            bot_name = signal.get('bot_name', 'Unknown')

            try:
                # Kiểm tra các vị thế hiện tại
                response = self.client.get_position_list(
                    category='linear',
                    symbol=signal['symbol']
                )
                if response.get('retCode', -1) == 0:
                    positions = response.get('result', {}).get('list', [])
                    for position in positions:
                        if position['symbol'] == signal['symbol'] and position['side'] == side and float(position['size']) > 0:
                            # Đóng vị thế
                            close_response = self.client.close_position(
                                category='linear',
                                symbol=signal['symbol'],
                                side='Buy' if position['side'] == 'Sell' else 'Sell',  # Đảo ngược side để đóng vị thế
                                qty=position['size']
                            )
                            if close_response.get('retCode', 0) == 0:
                                logger.info(f"Đã đóng vị thế cho {signal['symbol']}, side: {side}, qty: {position['size']}")
                            else:
                                logger.warning(f"Không thể đóng vị thế cho {signal['symbol']}: {close_response.get('retMsg', 'Lỗi không xác định')}")
                else:
                    logger.warning(f"Không thể lấy danh sách vị thế: {response.get('retMsg', 'Lỗi không xác định')}")
           
                response = self.client.get_open_orders(
                    category='linear',
                    symbol=signal['symbol'],
                    side=side
                )
                if response.get('retCode', -1) == 0:
                    orders = response.get('result', {}).get('list', [])
                    for order in orders:
                        if order['symbol'] == signal['symbol'] and order['side'] == side:
                            cancel_response = self.client.cancel_order(
                                category='linear',
                                symbol=signal['symbol'],
                                orderId=order['orderId']
                            )
                            if cancel_response.get('retCode', 0) == 0:
                                logger.info(f"Closed existing order {order['orderId']} for {signal['symbol']}, side: {side}")
                            else:
                                logger.warning(f"Failed to close order {order['orderId']}: {cancel_response.get('retMsg', 'Unknown error')}")
                else:
                    logger.warning(f"Failed to fetch open orders: {response.get('retMsg', 'Unknown error')}")
            except Exception as e:
                logger.warning(f"Error checking/closing open orders: {str(e)}")
            # Kiểm tra và thiết lập chế độ vị thế
            try:
                self.client.switch_position_mode(category='linear', mode=3, symbol=signal['symbol'])
                logger.info(f"Switched to Hedge Mode for {signal['symbol']}")
            except Exception as e:
                logger.warning(f"Failed to switch to Hedge Mode: {str(e)}")
            
            response = self.client.get_instruments_info(category="linear", symbol=signal['symbol'])
            instrument = response["result"]["list"][0]
            qty_step = float(instrument['lotSizeFilter']['qtyStep'])

            positions = self.client.get_positions(category='linear', symbol=signal['symbol'])

            quantity = math.floor(quantity / qty_step) * qty_step
            # Xác định positionIdx dựa trên chế độ
            position_idx = 1 if side == 'Buy' else 2 

            # Thiết lập đòn bẩy
            leverage = signal.get('leverage', 5)
            try:
                current_leverage = positions['result']['list'][0].get('leverage', '1')
                if current_leverage != str(leverage):
                    leverage_response = self.client.set_leverage(
                        category='linear',
                        symbol=signal['symbol'],
                        buyLeverage=str(leverage),
                        sellLeverage=str(leverage)
                    )
                    if leverage_response.get('retCode', -1) == 0:
                        logger.info(f"Leverage set to {leverage}x for {signal['symbol']}")
                    else:
                        logger.warning(f"Failed to set leverage: {leverage_response.get('retMsg', 'Unknown error')}")
                else:
                    logger.info(f"Leverage already at {leverage}x for {signal['symbol']}")
            except Exception as e:
                logger.warning(f"Failed to set leverage: {str(e)}")
          
            order = self.client.place_order(
                category='linear',
                symbol=signal['symbol'],
                side=side,
                orderType='Market',
                qty=f"{round(quantity, 8)}",
                timeInForce='GTC',
                positionIdx=position_idx,
                stopLoss=f"{signal['sl_price']}",
                reduceOnly=False
            )

            # Lưu vào cơ sở dữ liệu
            if order['retCode'] == 0:
                order_id = order['result']['orderId']
               
                insert_query = """
                    INSERT INTO trades (
                        order_id, symbol, side, entry_price, quantity, position_size, 
                        leverage, tp1_price, tp2_price, tp3_price, sl_price, 
                        current_sl, current_tp, strategy_type, status, bot_name
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                insert_params = (
                    order_id,
                    signal['symbol'],
                    side,
                    signal['entry'],
                    quantity,
                    position_size,
                    leverage,
                    signal.get('tp1_price'),
                    signal.get('tp2_price'),
                    signal.get('tp3_price'),
                    signal['sl_price'],
                    signal['sl_price'],
                    signal.get('tp1_price'),
                    signal['strategy_type'],
                    'OPEN',
                    bot_name
                )
                
                # Thực thi câu lệnh INSERT và lấy ID của bản ghi vừa tạo
                trade_id = self.execute_query(
                    query=insert_query,
                    params=insert_params,
                    fetch=False,
                    commit=True
                )
                self.active_trades[trade_id] = signal['symbol']
                logger.info(f"Order created: {order_id}, Trade ID: {trade_id}, Bot: {bot_name}")
                return {'trade_id': trade_id, 'order_id': order_id, 'status': 'OPEN', 'bot_name': bot_name}
            else:
                logger.error(f"Order creation failed: {order['retMsg']}")
                return {'error': order['retMsg']}

        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            return {'error': str(e)}


    def create_order_best(self, signal: Dict[str, Any], type: str) -> Dict[str, Any]:
        """Tạo lệnh giao dịch trên Bybit với Take Profit và Stop Loss, vị thế 30 USDT."""
        try:
            # Map signal keys from provided data to expected keys
            strategy_type = signal.get('strategy_type', 'strategy1')  # Default to 'strategy1' if not provided
            
            position_size = 300  # Fixed position size of 30 USDT
            quantity = position_size / signal['entry1']  # Calculate quantity based on entry price
            
            # Kiểm tra số dư tài khoản trước khi đặt lệnh
            # balance = self.get_account_balance('UNIFIED')
            # if not balance or balance.get('available_balance', 0) < position_size * 1.1:  # Thêm 10% dự phòng
            #     error_msg = f"Không đủ số dư để đặt lệnh. Cần tối thiểu: {position_size * 1.1:.2f} USDT, Số dư khả dụng: {balance.get('available_balance', 0) if balance else 0:.2f} USDT"
            #     logger.error(error_msg)
            #     return {'error': error_msg}
            
            side = 'Buy' if signal.get('position') == 'LONG' else 'Sell' if signal.get('position') == 'SHORT' else signal.get('position', 'Buy').capitalize()
            if side not in ['Buy', 'Sell']:
                raise ValueError("Side must be either 'Buy' or 'Sell'")
            bot_name = signal.get('bot', 'Unknown')

            try:
                # Kiểm tra các vị thế hiện tại
                response = self.client.get_positions(
                    category='linear',
                    symbol=signal['asset']
                )
                if response.get('retCode', -1) == 0:
                    positions = response.get('result', {}).get('list', [])
                    for position in positions:
                        if position['symbol'] == signal['asset'] and float(position['size']) > 0:
                            position_idx = int(position.get('positionIdx', 0))
                            close_response = self.client.place_order(
                                category='linear',
                                symbol=signal['asset'],
                                side='Buy' if position['side'] == 'Sell' else 'Sell',
                                orderType='Market',
                                qty=str(round(position['size'], 8)),
                                reduceOnly=True,
                                positionIdx=position_idx
                            )
                            
                            if close_response.get('retCode', 0) == 0:
                                logger.info(f"Đã đóng vị thế cho {signal['asset']}, side: {side}, qty: {position['size']}")
                            else:
                                logger.warning(f"Không thể đóng vị thế cho {signal['asset']}: {close_response.get('retMsg', 'Lỗi không xác định')}")
                else:
                    logger.warning(f"Không thể lấy danh sách vị thế: {response.get('retMsg', 'Lỗi không xác định')}")

                # Kiểm tra và hủy các lệnh mở hiện tại
                response = self.client.get_open_orders(
                    category='linear',
                    symbol=signal['asset'],
                    side=side
                )
                if response.get('retCode', -1) == 0:
                    orders = response.get('result', {}).get('list', [])
                    for order in orders:
                        if order['symbol'] == signal['asset'] and order['side'] == side:
                            cancel_response = self.client.cancel_order(
                                category='linear',
                                symbol=signal['asset'],
                                orderId=order['orderId']
                            )
                            if cancel_response.get('retCode', 0) == 0:
                                logger.info(f"Closed existing order {order['orderId']} for {signal['asset']}, side: {side}")
                            else:
                                logger.warning(f"Failed to close order {order['orderId']}: {cancel_response.get('retMsg', 'Unknown error')}")
                else:
                    logger.warning(f"Failed to fetch open orders: {response.get('retMsg', 'Unknown error')}")
            except Exception as e:
                logger.warning(f"Error checking/closing open orders: {str(e)}")

            # Kiểm tra và thiết lập chế độ vị thế
            try:
                self.client.switch_position_mode(category='linear', mode=3, symbol=signal['asset'])
                logger.info(f"Switched to Hedge Mode for {signal['asset']}")
            except Exception as e:
                logger.warning(f"Failed to switch to Hedge Mode: {str(e)}")

            # Lấy thông tin công cụ để xác định qty_step
            response = self.client.get_instruments_info(category="linear", symbol=signal['asset'])
            instrument = response["result"]["list"][0]
            qty_step = float(instrument['lotSizeFilter']['qtyStep'])

            positions = self.client.get_positions(category='linear', symbol=signal['asset'])

            quantity = math.floor(quantity / qty_step) * qty_step
            # Xác định positionIdx dựa trên chế độ
            position_idx = 1 if side == 'Buy' else 2

            # Thiết lập đòn bẩy
            leverage = signal.get('leverage', 5)
            try:
                current_leverage = positions['result']['list'][0].get('leverage', '1')
                if current_leverage != str(leverage):
                    leverage_response = self.client.set_leverage(
                        category='linear',
                        symbol=signal['asset'],
                        buyLeverage=str(leverage),
                        sellLeverage=str(leverage)
                    )
                    if leverage_response.get('retCode', -1) == 0:
                        logger.info(f"Leverage set to {leverage}x for {signal['asset']}")
                    else:
                        logger.warning(f"Failed to set leverage: {leverage_response.get('retMsg', 'Unknown error')}")
                else:
                    logger.info(f"Leverage already at {leverage}x for {signal['asset']}")
            except Exception as e:
                logger.warning(f"Failed to set leverage: {str(e)}")

            # Đặt lệnh giao dịch
            if type == 'ema':
                order = self.client.place_order(
                    category='linear',
                    symbol=signal['asset'],
                    side=side,
                    orderType='Market',
                    qty=f"{round(quantity, 8)}",
                    timeInForce='GTC',
                    positionIdx=position_idx,
                    takeProfit=f"{signal['tp3']}",
                    stopLoss=f"{signal['stoploss']}",
                    reduceOnly=False
                )
            else:
                order = self.client.place_order(
                    category='linear',
                    symbol=signal['asset'],
                    side=side,
                    orderType='Limit',  # Changed from 'Market' to 'Limit'
                    qty=f"{round(quantity, 8)}",
                    price=f"{signal['entry1']}",  # Specify the desired entry price
                    timeInForce='GTC',
                    positionIdx=position_idx,
                    takeProfit=f"{signal['tp3']}",
                    stopLoss=f"{signal['stoploss']}",
                    reduceOnly=False
                )
            
            # Lưu vào cơ sở dữ liệu
            if order['retCode'] == 0:
                order_id = order['result']['orderId']

                if type == 'ema':
                    avg_price = order.get('result', {}).get('avgPrice')
                    if avg_price and float(avg_price) > 0:
                        percentage = (float(signal['entry1']) - float(avg_price)) / float(avg_price)
                        signal['entry1'] = avg_price
                        signal['tp1'] = float(signal['tp1']) - percentage*float(avg_price)
                        signal['tp2'] = float(signal['tp2']) - percentage*float(avg_price)
                        signal['tp3'] = float(signal['tp3']) - percentage*float(avg_price)
                        signal['stoploss'] = float(signal['stoploss']) - percentage*float(avg_price)
                        self.update_stoploss(trade_id, signal['stoploss'])
                        logger.info(f"Updated stoploss for trade {trade_id}: {signal['stoploss']}")
            
                insert_query = """
                    INSERT INTO trades (
                        order_id, symbol, side, entry_price, quantity, position_size, 
                        leverage, tp1_price, tp2_price, tp3_price, sl_price, 
                        current_sl, current_tp, strategy_type, status, bot_name
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                insert_params = (
                    order_id,
                    signal['asset'],
                    side,
                    signal['entry1'],
                    quantity,
                    position_size,
                    leverage,
                    signal.get('tp1'),
                    signal.get('tp2'),
                    signal.get('tp3', 0),
                    signal['stoploss'],
                    signal['stoploss'],
                    signal.get('tp1'),
                    strategy_type,
                    'FILLED' if type == 'ema' else 'OPEN',
                    bot_name
                )
                
                # Thực thi câu lệnh INSERT
                trade_id = self.execute_query(
                    query=insert_query,
                    params=insert_params,
                    fetch=False,
                    commit=True
                )
                
                if type == 'ema':
                    self.place_tp_orders(trade_id=trade_id, symbol=signal['asset'], side=side, quantity=quantity, tp1_price=signal.get('tp1'), tp2_price=signal.get('tp2'), tp3_price=signal.get('tp3', 0), position_idx=position_idx, entry_price=signal['entry1'])
  
                return { 'order_id': order_id, 'status': 'OPEN', 'bot_name': bot_name}
            else:
                logger.error(f"Order creation failed: {order['retMsg']}")
                return {'error': order['retMsg']}

        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            return {'error': str(e)}

    def place_tp_orders(self, trade_id: int, symbol: str, side: str, quantity: float, tp1_price: float, tp2_price: float, tp3_price: float, position_idx: int, entry_price: float) -> Dict[str, Any]:
        """Đặt lệnh TP1, TP2, TP3, mỗi lệnh đóng 10 USDT."""
        try:
            logger.info(f"Placing TP1/TP2/TP3 for trade {trade_id}, symbol: {symbol}")
            
            # Tính số lượng cho mỗi TP (10 USDT)
            tp1_quantity = 150 / entry_price  # Số lượng cho 10 USDT
            tp1_quantity = round(math.floor(tp1_quantity / float(self.client.get_instruments_info(category="linear", symbol=symbol)["result"]["list"][0]['lotSizeFilter']['qtyStep'])) * float(self.client.get_instruments_info(category="linear", symbol=symbol)["result"]["list"][0]['lotSizeFilter']['qtyStep']), 8)

            tp2_quantity = 90 / entry_price  # Số lượng cho 10 USDT
            tp2_quantity = round(math.floor(tp2_quantity / float(self.client.get_instruments_info(category="linear", symbol=symbol)["result"]["list"][0]['lotSizeFilter']['qtyStep'])) * float(self.client.get_instruments_info(category="linear", symbol=symbol)["result"]["list"][0]['lotSizeFilter']['qtyStep']), 8)

            print("is place tp ", tp1_quantity, tp2_quantity)
            # Đặt lệnh TP1
            tp1_order = self.client.place_order(
                category='linear',
                symbol=symbol,
                side='Sell' if side == 'Buy' else 'Buy',
                orderType='Limit',
                qty=f"{tp1_quantity}",
                price=f"{tp1_price}",
                timeInForce='GTC',
                positionIdx=position_idx,
                reduceOnly=True
            )
            tp1_order_id = None
            if tp1_order['retCode'] == 0:
                tp1_order_id = tp1_order['result']['orderId']
                self.execute_query(
                    "UPDATE trades SET tp1_order_id = %s WHERE id = %s",
                    (tp1_order_id, trade_id),
                    commit=True
                )
                logger.info(f"TP1 order placed: {tp1_order_id}, Symbol: {symbol}, Price: {tp1_price}")
            else:
                logger.warning(f"Failed to place TP1 order: {tp1_order.get('retMsg', 'Unknown error')}")
            
            print("order id tp1", tp1_order_id)
            # Đặt lệnh TP2
            tp2_order = self.client.place_order(
                category='linear',
                symbol=symbol,
                side='Sell' if side == 'Buy' else 'Buy',
                orderType='Limit',
                qty=f"{tp2_quantity}",
                price=f"{tp2_price}",
                timeInForce='GTC',
                positionIdx=position_idx,
                reduceOnly=True
            )
            tp2_order_id = None
            if tp2_order['retCode'] == 0:
                tp2_order_id = tp2_order['result']['orderId']
                self.execute_query(
                    "UPDATE trades SET tp2_order_id = %s WHERE id = %s",
                    (tp2_order_id, trade_id),
                    commit=True
                )
                logger.info(f"TP2 order placed: {tp2_order_id}, Symbol: {symbol}, Price: {tp2_price}")
            else:
                logger.warning(f"Failed to place TP2 order: {tp2_order.get('retMsg', 'Unknown error')}")
            
            print("order id tp2", tp2_order_id)
            # Đặt lệnh TP3

            return {'tp1_order_id': tp1_order_id, 'tp2_order_id': tp2_order_id}
        except Exception as e:
            logger.error(f"Error placing TP orders: {str(e)}")
            return {'error': str(e)}
    def check_order_status(self, trade_id: int) -> str:
        """Kiểm tra trạng thái lệnh trên Bybit."""
        try:
            trade = self.get_trade_by_id(trade_id)
            if not trade:
                logger.error(f"Trade {trade_id} not found")
                return 'NOT_FOUND'
                
            order = self.client.get_order_history(category='linear', orderId=trade['order_id'])
            status = order['result']['list'][0]['orderStatus'] if order['retCode'] == 0 else 'CANCELLED'
            
            if status == 'Filled':
                self.execute_query(
                    "UPDATE trades SET filled_at = %s WHERE id = %s",
                    (datetime.now(), trade_id),
                    commit=True
                )
                logger.info(f"Trade {trade_id}: Order filled")
                
            return status
        except Exception as e:
            logger.error(f"Error checking order status for trade {trade_id}: {str(e)}")
            return 'ERROR'

    def update_position(self, trade_id: int, current_price: float) -> Dict[str, Any]:
        """Cập nhật trạng thái vị thế dựa trên giá thị trường."""
        try:
            trade = self.get_trade_by_id(trade_id)
            if not trade:
                logger.error(f"Trade {trade_id} not found")
                return {'error': 'Trade not found'}

            if not trade['filled_at']:
                # logger.info(f"Trade {trade_id}: Order not yet filled, status: {trade['status']}")
                return {'error': f"Order not yet filled, current status: {trade['status']}"}

            if trade['status'] not in ['FILLED', 'TP1_HIT', 'TP2_HIT']:
                return {'status': trade['status'], 'message': 'Position not in valid state for updating (must be FILLED, TP1_HIT, or TP2_HIT)'}

            if trade['side'] == 'Buy':
                pnl = (current_price - trade['entry_price']) * trade['quantity'] * trade['leverage']
            else:
                pnl = (trade['entry_price'] - current_price) * trade['quantity'] * trade['leverage']
            pnl_percent = (pnl / trade['position_size']) * 100

            if trade['side'] == 'Buy':
                hit_tp1 = current_price >= trade['tp1_price']
                hit_tp2 = current_price >= trade['tp2_price']
                hit_sl = current_price <= trade['sl_price']
            else:
                hit_tp1 = current_price <= trade['tp1_price']
                hit_tp2 = current_price <= trade['tp2_price']
                hit_sl = current_price >= trade['sl_price']

            if hit_tp1 and trade['status'] == 'FILLED':
                self.update_stoploss(trade_id, trade['entry_price'])
           
                update_tp1_query = """
                    UPDATE trades 
                    SET status = 'TP1_HIT', 
                        current_sl = %s, 
                        pnl = %s, 
                        pnl_percent = %s, 
                        updated_at = %s
                    WHERE id = %s
                """
                self.execute_query(
                    query=update_tp1_query,
                    params=(trade['entry_price'], pnl, pnl_percent, datetime.now(), trade_id),
                    fetch=False,
                    commit=True
                )
                logger.info(f"Trade {trade_id}: TP1 hit, SL moved to entry")
                return {'status': 'TP1_HIT', 'message': 'Stoploss moved to entry', 'pnl': pnl}
            
            if hit_tp2 and trade['status'] == 'TP1_HIT':
                self.update_stoploss(trade_id, trade['tp1_price'])
                
                update_tp2_query = """
                    UPDATE trades 
                    SET status = 'TP2_HIT', 
                        current_sl = %s, 
                        pnl = %s, 
                        pnl_percent = %s, 
                        updated_at = %s
                    WHERE id = %s
                """
                self.execute_query(
                    query=update_tp2_query,
                    params=(trade['tp1_price'], pnl, pnl_percent, datetime.now(), trade_id),
                    fetch=False,
                    commit=True
                )
                logger.info(f"Trade {trade_id}: TP2 hit, SL moved to TP1")
                return {'status': 'TP2_HIT', 'message': 'Stoploss moved to TP1', 'pnl': pnl}

            if hit_sl:
                self.close_position(trade_id, 1.0, current_price)
                update_closed_query = """
                    UPDATE trades 
                    SET status = 'CLOSED', 
                        closed_at = %s, 
                        pnl = %s, 
                        pnl_percent = %s 
                    WHERE id = %s
                """
                self.execute_query(
                    query=update_closed_query,
                    params=(datetime.now(), pnl, pnl_percent, trade_id),
                    fetch=False,
                    commit=True
                )
                logger.info(f"Trade {trade_id}: Hit stoploss, position closed")
                return {'status': 'CLOSED', 'message': 'Position closed at stoploss', 'pnl': pnl}

            
            return {'status': trade['status'], 'message': 'No update required', 'pnl': pnl}

        except Exception as e:
            logger.error(f"Error updating position {trade_id}: {str(e)}")
            return {'error': str(e)}

    def update_stoploss(self, trade_id: int, new_sl: float) -> bool:
        """Cập nhật stoploss cho giao dịch."""
        try:
            trade = self.get_trade_by_id(trade_id)
            if not trade:
                logger.error(f"Trade {trade_id} not found")
                return False

            self.client.set_trading_stop(
                category='linear',
                symbol=trade['symbol'],
                stopLoss=str(new_sl),
                side=trade['side'],
                positionIdx=1 if trade['side'] == "Buy" else 2
            )

            self.execute_query(
                query="""
                    UPDATE trades SET current_sl = %s WHERE id = %s
                """,
                params=(new_sl, trade_id),
                fetch=False,
                commit=True
            )
            logger.info(f"Trade {trade_id}: Stoploss updated to {new_sl}")
            return True

        except Exception as e:
            logger.error(f"Error updating stoploss for trade {trade_id}: {str(e)}")
            return False

    def close_position(self, trade_id: int, percentage: float, current_price: float) -> bool:
        """
        Đóng một phần hoặc toàn bộ vị thế.
        
        Args:
            trade_id (int): ID của giao dịch cần đóng
            percentage (float): Tỷ lệ đóng vị thế (từ 0.0 đến 1.0)
            current_price (float): Giá hiện tại để tính lãi/lỗ
            
        Returns:
            bool: True nếu đóng vị thế thành công, False nếu có lỗi
        """
        try:
            # Lấy thông tin giao dịch
            trade = self.get_trade_by_id(trade_id)
            if not trade:
                logger.error(f"Không tìm thấy giao dịch {trade_id}")
                return False

            from decimal import Decimal, ROUND_DOWN
            
            # Chuyển đổi tất cả giá trị số sang Decimal để đảm bảo tính toán chính xác
            quantity = Decimal(str(trade['quantity'])).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
            entry_price = Decimal(str(trade['entry_price'])).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
            current_price_dec = Decimal(str(current_price)).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
            leverage = Decimal(str(trade.get('leverage', 1))).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            
            # Tính toán số lượng cần đóng
            close_qty = float((quantity * Decimal(str(percentage))).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))
            opposite_side = 'Sell' if trade['side'].lower() == 'buy' else 'Buy'
            # Lấy thông tin vị thế hiện tại
            try:
                position_info = self.client.get_positions(
                    category='linear',
                    symbol=trade['symbol']
                )
            except Exception as e:
                logger.error(f"Lỗi khi lấy thông tin vị thế từ Bybit: {str(e)}")
                return False
            
            position_idx = 0  # Mặc định là One-Way Mode
            position_size = 0.0
            
            if position_info.get('retCode') == 0 and position_info.get('result'):
                positions = position_info['result'].get('list', [])
                if positions:
                    # Lấy position_idx và kích thước vị thế hiện tại
                    for position in positions:
                        if position.get('side') == trade['side'] and float(Decimal(str(position.get('size', 0)))) > 0:
                            position_idx = int(position.get('positionIdx', 0))
                            position_size = float(Decimal(str(position.get('size', 0))).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))
                           
                            break
            # Kiểm tra nếu vị thế đã về 0 hoặc không tồn tại
            if position_size <= 0 or close_qty <= 0:
                logger.warning(f"Vị thế {trade['symbol']} đã đóng hoặc không tồn tại. Đang cập nhật trạng thái...")
                # Cập nhật trạng thái giao dịch là đã đóng
                return self.update_trade_status(trade_id, 'CLOSED', datetime.now())
                
            # Đảm bảo không đóng nhiều hơn số lượng hiện có
            close_qty = min(close_qty, position_size)
            
            # Đặt lệnh đóng vị thế với position_idx
            try:
                order_result = self.client.place_order(
                    category='linear',
                    symbol=trade['symbol'],
                    side=opposite_side,
                    orderType='Market',
                    qty=str(round(close_qty, 8)),
                    reduceOnly=True,
                    positionIdx=position_idx
                )
                logger.info(f"Đã đặt lệnh đóng vị thế: {order_result}")
            except Exception as e:
                if '110017' in str(e):  # Lỗi position is zero
                    logger.warning(f"Vị thế {trade['symbol']} đã đóng. Đang cập nhật trạng thái...")
                    return self.update_trade_status(trade_id, 'CLOSED', datetime.now())
                logger.error(f"Lỗi khi đặt lệnh đóng vị thế: {str(e)}")
                return False

            # Tính toán lợi nhuận
            try:
                if trade['side'].lower() == 'buy':
                    pnl = float(((current_price_dec - entry_price) * quantity * leverage * Decimal(str(percentage))).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))
                else:
                    pnl = float(((entry_price - current_price_dec) * quantity * leverage * Decimal(str(percentage))).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))
            except Exception as e:
                logger.error(f"Lỗi khi tính toán lợi nhuận: {str(e)}")
                pnl = 0.0

            # Chuyển đổi tất cả giá trị sang Decimal để tính toán
            try:
                current_pnl = Decimal(str(trade.get('pnl', 0))).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
                position_size = Decimal(str(trade.get('position_size', 0))).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
                
                # Tính toán số lượng và kích thước còn lại
                remaining_percentage = (Decimal('1') - Decimal(str(percentage))).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
                remaining_qty = float((Decimal(str(trade['quantity'])) * remaining_percentage).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))
                remaining_size = float((position_size * remaining_percentage).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))
                
                # Cập nhật trạng thái
                status = 'CLOSED' if float(percentage) >= 1.0 else trade['status']
                closed_at = datetime.now() if float(percentage) >= 1.0 else None
                
                # Tính toán PnL mới
                new_pnl = (current_pnl + Decimal(str(pnl))).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
                pnl_percent = float((new_pnl / position_size * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)) if position_size != 0 else 0.0
                
                # Cập nhật cơ sở dữ liệu sử dụng execute_query
                update_query = """
                    UPDATE trades 
                    SET quantity = %s, 
                        position_size = %s, 
                        status = %s, 
                        closed_at = %s, 
                        pnl = %s, 
                        pnl_percent = %s, 
                        updated_at = %s 
                    WHERE id = %s
                """
                update_params = (
                    remaining_qty, 
                    remaining_size, 
                    status, 
                    closed_at,
                    float(new_pnl),
                    pnl_percent,
                    datetime.now(), 
                    trade_id
                )
                
                # Thực thi câu lệnh UPDATE
                rows_affected = self.execute_query(
                    query=update_query,
                    params=update_params,
                    fetch=False,
                    commit=True
                )
                
                if not rows_affected or rows_affected <= 0:
                    logger.error(f"Không thể cập nhật thông tin giao dịch {trade_id}")
                    return False
                    
                
                logger.info(f"Đã đóng {float(percentage)*100:.2f}% vị thế cho giao dịch {trade_id}")
                
                # Nếu đã đóng toàn bộ vị thế, xóa khỏi danh sách giao dịch đang hoạt động
                if float(percentage) >= 1.0:
                    self.active_trades.pop(trade_id, None)
                    
                return True
                
            except Exception as e:
                logger.error(f"Lỗi khi cập nhật cơ sở dữ liệu: {str(e)}", exc_info=True)
                return False
                
        except Exception as e:
            logger.error(f"Lỗi khi đóng vị thế cho giao dịch {trade_id}: {str(e)}", exc_info=True)
            return False
    def update_trade_status(self, trade_id: int, status: str, closed_at: datetime = None) -> bool:
        """
        Cập nhật trạng thái giao dịch trong cơ sở dữ liệu.
        
        Args:
            trade_id (int): ID của giao dịch cần cập nhật
            status (str): Trạng thái mới của giao dịch
            closed_at (datetime, optional): Thời gian đóng giao dịch nếu có
            
        Returns:
            bool: True nếu cập nhật thành công, False nếu có lỗi
        """
        try:
            # Kiểm tra xem trade_id có tồn tại không
            trade = self.get_trade_by_id(trade_id)
            if not trade:
                logger.error(f"Cannot update status: Trade {trade_id} not found")
                return False
                
            # Xây dựng câu lệnh UPDATE động dựa trên tham số truyền vào
            update_fields = ["status = %s"]
            params = [status]
            
            if closed_at is not None:
                update_fields.append("closed_at = %s")
                params.append(closed_at)
                
            # Thêm updated_at
            update_fields.append("updated_at = %s")
            params.append(datetime.now())
            
            # Thêm trade_id vào params cho mệnh đề WHERE
            params.append(trade_id)
            
            # Thực hiện câu lệnh UPDATE
            query = f"""
                UPDATE trades 
                SET {', '.join(update_fields)}
                WHERE id = %s
            """
            
            rows_affected = self.execute_query(
                query=query,
                params=tuple(params),
                fetch=False,
                commit=True
            )
            
            if rows_affected and rows_affected > 0:
                logger.info(f"Successfully updated trade {trade_id} status to '{status}'")
            
                return True
                
            logger.warning(f"No rows affected when updating trade {trade_id} status")
            return False
            
        except Exception as e:
            logger.error(
                f"Error updating trade {trade_id} status to '{status}'. "
                f"Error: {str(e)}",
                exc_info=True
            )
            return False
    def get_trade(self):
        """
        Lấy danh sách tất cả các giao dịch từ Bybit API
        
        Returns:
            List[Dict[str, Any]]: Danh sách các giao dịch với thông tin chi tiết
        """
        try:
            # Sử dụng unified_trading để lấy lịch sử giao dịch
            if hasattr(self, 'unified_client'):
                response = self.unified_client.get_executions(
                    category="linear",
                    limit=100,
                    recv_window=5000
                )
            else:
                # Fallback nếu chưa khởi tạo unified_client
                from pybit.unified_trading import HTTP
                self.unified_client = HTTP(
                    testnet=self.testnet,
                    api_key=os.getenv('BYBIT_API_KEY'),
                    api_secret=os.getenv('BYBIT_API_SECRET')
                )
                response = self.unified_client.get_executions(
                    category="linear",
                    limit=100,
                    recv_window=5000
                )

            if response.get('retCode') != 0:
                logger.error(f"Error fetching trades from Bybit: {response.get('retMsg', 'Unknown error')}")
                return []

            trades = response.get('result', {}).get('list', [])
            trades_list = []

            for trade in trades:
                try:
                    # Chuyển đổi thời gian giao dịch từ timestamp (ms) sang ISO 8601
                    exec_time = trade.get('execTime')
                    if exec_time:
                        exec_time = datetime.fromtimestamp(int(exec_time) / 1000).isoformat()
                    else:
                        # Nếu không có execTime, sử dụng thời gian hiện tại
                        exec_time = datetime.now().isoformat()

                    # Xác định trạng thái giao dịch
                    status = trade.get('orderStatus', 'FILLED')
                    if status == 'Filled':
                        status = 'FILLED'
                    elif status in ['New', 'New ']:
                        status = 'OPEN'
                    elif status == 'Cancelled':
                        status = 'CANCELLED'
                    
                    # Lấy thông tin đòn bẩy từ position
                    leverage = 1  # Giá trị mặc định
                    try:
                        # Thử lấy từ trade data trước
                        leverage = int(trade.get('leverage', 1))
                        
                        # Nếu không có, thử lấy từ API positions
                        if leverage <= 1 and 'symbol' in trade:
                            pos_response = self.client.get_positions(
                                category="linear",
                                symbol=trade['symbol']
                            )
                            if pos_response.get('retCode') == 0 and pos_response.get('result', {}).get('list'):
                                for pos in pos_response['result']['list']:
                                    if pos.get('symbol') == trade['symbol']:
                                        leverage = int(float(pos.get('leverage', 1)))
                                        break
                    except Exception as e:
                        logger.warning(f"Could not get leverage for {trade.get('symbol')}: {str(e)}")
                    
                    trades_list.append({
                        'id': trade.get('execId') or str(uuid.uuid4())[:8],
                        'order_id': trade.get('orderId', ''),
                        'symbol': trade.get('symbol', 'UNKNOWN'),
                        'side': trade.get('side', 'BUY'),
                        'entry_price': float(trade.get('execPrice', 0)) if trade.get('execPrice') else 0,
                        'quantity': float(trade.get('execQty', 0)) if trade.get('execQty') else 0,
                        'status': status,
                        'pnl': float(trade.get('closedPnl', 0)) if trade.get('closedPnl') else 0,
                        'bot_name': trade.get('orderLinkId', 'N/A'),
                        'leverage': leverage,
                        'created_at': exec_time,
                        'updated_at': exec_time
                    })
                except Exception as e:
                    logger.error(f"Error processing trade: {str(e)}\nTrade data: {trade}", exc_info=True)
                    continue

            # Sắp xếp theo thời gian tạo mới nhất trước
            trades_list.sort(key=lambda x: x['created_at'], reverse=True)
            
            logger.info(f"Retrieved {len(trades_list)} trades from Bybit")
            return trades_list

        except Exception as e:
            logger.error(f"Error fetching trades from Bybit: {str(e)}", exc_info=True)
            return []

    def get_all_orders(self, symbol: str = None, order_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Lấy danh sách tất cả các lệnh (OPEN, FILLED, CANCELLED) từ Bybit API.

        Args:
            symbol (str, optional): Cặp giao dịch, ví dụ 'DOTUSDT'
            order_id (str, optional): ID của lệnh cụ thể
            limit (int, optional): Số lượng lệnh tối đa mỗi yêu cầu, mặc định 100

        Returns:
            List[Dict[str, Any]]: Danh sách các lệnh với thông tin chi tiết
        """
        try:
            if not hasattr(self, 'unified_client') or self.unified_client is None:
                self.unified_client = HTTP(
                    testnet=self.testnet,
                    api_key=os.getenv('BYBIT_API_KEY'),
                    api_secret=os.getenv('BYBIT_API_SECRET')
                )

            orders_list = []
            seen_order_ids = set()  # Tránh trùng lặp order_id

            # 1. Lấy lệnh mở từ /v5/order/realtime
            order_params = {'category': 'linear', 'limit': limit, 'settleCoin': 'USDT'}
            if symbol:
                order_params['symbol'] = symbol
            if order_id:
                order_params['orderId'] = order_id

            try:
                open_orders_response = self.unified_client.get_open_orders(**order_params)
            except Exception as e:
                logger.error(f"Error fetching open orders: {str(e)}")
                return []

            if open_orders_response.get('retCode') != 0:
                logger.error(f"Error fetching open orders: {open_orders_response.get('retMsg', 'Unknown error')}")
            else:
                open_orders = open_orders_response.get('result', {}).get('list', [])
                for order in open_orders:
                    created_time = datetime.fromtimestamp(int(order.get('createdTime', '0')) / 1000).isoformat()
                    updated_time = datetime.fromtimestamp(int(order.get('updatedTime', '0')) / 1000).isoformat()
                    leverage = 1
                    stop_loss = 0
                    pnl = 0
                    take_profit = 0
                    price = float(order.get('triggerPrice', 0)) if order.get('orderStatus') == 'Untriggered' else float(order.get('price', 0))
                    try:
                        # Sử dụng get_positions thay vì get_position_list
                        pos_response = self.unified_client.get_positions(category='linear', symbol=order.get('symbol'))

                        if pos_response.get('retCode') == 0:
                            for pos in pos_response.get('result', {}).get('list', []):
                                if pos.get('symbol') == order.get('symbol') and pos.get('positionIdx') == order.get('positionIdx'):
                                    leverage = int(float(pos.get('leverage', 1)))
                                    stop_loss = float(pos.get('stopLoss', 0)) if pos.get('stopLoss') else 0
                                    pnl = float(pos.get('unrealisedPnl', 0)) if pos.get('unrealisedPnl') else 0
                                    take_profit = float(pos.get('takeProfit', 0)) if pos.get('takeProfit') else 0
                                    break
                               
                    except Exception as e:
                        logger.warning(f"Could not get position info for {order.get('symbol')}: {str(e)}")

                    # Lấy stop loss từ order nếu có
                    if 'stopLoss' in order and order['stopLoss']:
                        stop_loss = float(order['stopLoss'])

                    status = 'OPEN' if order.get('orderStatus') in ['New', 'PartiallyFilled'] else order.get('orderStatus', 'OPEN')
                    orders_list.append({
                        'order_id': order.get('orderId', ''),
                        'symbol': order.get('symbol', 'UNKNOWN'),
                        'side': order.get('side', 'BUY'),
                        'entry_price': price,
                        'quantity': float(order.get('qty', 0)) if order.get('qty') else 0,
                        'status': status,
                        'order_type': order.get('orderType', 'UNKNOWN'),
                        'bot_name': order.get('orderLinkId', 'N/A'),
                        'take_profit': take_profit,
                        'leverage': leverage,
                        'stop_loss': stop_loss,
                        'pnl': pnl,
                        'created_at': created_time,
                        'updated_at': updated_time
                    })
                    seen_order_ids.add(order['orderId'])

            # 2. Lấy lịch sử lệnh từ /v5/order/history
            history_params = {'category': 'linear', 'limit': limit}
            if symbol:
                history_params['symbol'] = symbol
            if order_id:
                history_params['orderId'] = order_id

            history_response = self.unified_client.get_order_history(**history_params)
            if history_response.get('retCode') == 0:
                history_orders = history_response.get('result', {}).get('list', [])
                for order in history_orders:
                    if order['orderId'] not in seen_order_ids:
                        created_time = datetime.fromtimestamp(int(order.get('createdTime', '0')) / 1000).isoformat()
                        updated_time = datetime.fromtimestamp(int(order.get('updatedTime', '0')) / 1000).isoformat()
                        leverage = 1
                        stop_loss = 0
                        pnl = 0
                        take_profit = 0
                        try:
                            # Sử dụng get_positions thay vì get_position_list
                            pos_response = self.unified_client.get_positions(category='linear', symbol=order.get('symbol'))
                            if pos_response.get('retCode') == 0:
                                for pos in pos_response.get('result', {}).get('list', []):
                                    if pos.get('symbol') == order.get('symbol') and pos.get('positionIdx') == order.get('positionIdx'):
                                        leverage = int(float(pos.get('leverage', 1)))
                                        stop_loss = float(pos.get('stopLoss', 0)) if pos.get('stopLoss') else 0
                                        take_profit = float(pos.get('takeProfit', 0)) if pos.get('takeProfit') else 0
                                        pnl = float(pos.get('unrealisedPnl', 0)) if pos.get('unrealisedPnl') else 0
                                        break
                        except Exception as e:
                            logger.warning(f"Could not get position info for {order.get('symbol')}: {str(e)}")

                        # Lấy stop loss từ order nếu có
                        if 'stopLoss' in order and order['stopLoss']:
                            stop_loss = float(order['stopLoss'])

                        status = 'FILLED' if order.get('orderStatus') == 'Filled' else 'CANCELLED' if order.get('orderStatus') in ['Cancelled', 'Rejected'] else order.get('orderStatus', 'UNKNOWN')
                        orders_list.append({
                            'order_id': order.get('orderId', ''),
                            'symbol': order.get('symbol', 'UNKNOWN'),
                            'side': order.get('side', 'BUY'),
                            'entry_price': float(order.get('price', 0)) if order.get('price') else 0 ,
                            'stop_loss': stop_loss,
                            'quantity': float(order.get('qty', 0)) if order.get('qty') else 0,
                            'status': status,
                            'order_type': order.get('orderType', 'UNKNOWN'),
                            'bot_name': order.get('orderLinkId', 'N/A'),
                            'leverage': leverage,
                            'created_at': created_time,
                            'updated_at': updated_time,
                            'pnl': pnl,
                            'take_profit': take_profit,
                        })
                        seen_order_ids.add(order['orderId'])
            else:
                logger.error(f"Error fetching order history: {history_response.get('retMsg', 'Unknown error')}")

            # Sắp xếp theo thời gian cập nhật mới nhất
            orders_list.sort(key=lambda x: x['updated_at'], reverse=True)
            logger.info(f"Retrieved {len(orders_list)} orders from Bybit")
            return orders_list

        except Exception as e:
            logger.error(f"Error fetching orders from Bybit: {str(e)}", exc_info=True)
            return []

    def get_trade_by_id(self, trade_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin giao dịch từ cơ sở dữ liệu.
        
        Args:
            trade_id (int): ID của giao dịch cần lấy thông tin
            
        Returns:
            Dict[str, Any]: Thông tin giao dịch dưới dạng dictionary nếu tìm thấy,
                          None nếu không tìm thấy hoặc có lỗi
        """
        try:
            result = self.execute_query(
                "SELECT * FROM trades WHERE id = %s",
                (trade_id,),
                fetch=True,
                commit=False
            )
            
            # Nếu có kết quả, trả về dòng đầu tiên dưới dạng dict
            if result and len(result) > 0:
                return dict(result[0])
                
            logger.warning(f"Trade with ID {trade_id} not found")
            return None
            
        except Exception as e:
            logger.error(f"Error getting trade by ID {trade_id}: {str(e)}")
            return None

    def log_update(self, trade_id: int, status: str, price: float = None, sl_price: float = None,
                   tp_price: float = None, pnl: float = None, notes: str = None) -> bool:
        """
        Ghi lịch sử cập nhật vào bảng trade_updates.
        
        Args:
            trade_id (int): ID của giao dịch
            status (str): Trạng thái cập nhật
            price (float, optional): Giá hiện tại
            sl_price (float, optional): Giá stop loss
            tp_price (float, optional): Giá take profit
            pnl (float, optional): Lợi nhuận/thua lỗ
            notes (str, optional): Ghi chú thêm
            
        Returns:
            bool: True nếu ghi log thành công, False nếu có lỗi
        """
        try:
            # Kiểm tra xem trade_id có tồn tại không
            trade = self.get_trade_by_id(trade_id)
            if not trade:
                logger.error(f"Cannot log update: Trade {trade_id} not found")
                return False
                
            # Thực hiện câu lệnh INSERT
            result = self.execute_query(
                """
                INSERT INTO trade_updates 
                (trade_id, status, price, sl_price, tp_price, pnl, notes, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    trade_id, 
                    status, 
                    price, 
                    sl_price, 
                    tp_price, 
                    pnl, 
                    notes[:255] if notes else None,  # Giới hạn độ dài ghi chú
                    datetime.now()
                ),
                fetch=False,
                commit=True
            )
            
            if result and result > 0:
                logger.info(f"Successfully logged update for trade {trade_id}: {status}")
                return True
                
            logger.warning(f"No rows affected when logging update for trade {trade_id}")
            return False
            
        except Exception as e:
            logger.error(
                f"Error logging update for trade {trade_id}. "
                f"Status: {status}, Error: {str(e)}",
                exc_info=True
            )
            return False

    def start_websocket(self):
        """Khởi động WebSocket để theo dõi giá và trạng thái lệnh."""
        try:
            def handle_order_message(msg):
                try:
                    data = msg.get('data', [])
                    print("data order", data)
                    
                    for order in data:
                        order_id = order.get('orderId')
                        status = order.get('orderStatus')
                        symbol = order.get('symbol')
                        side = order.get('side')
                        orderStoploss = order.get('stopOrderType')
                        time.sleep(15)
                        result = self.execute_query(
                            """
                            SELECT id, symbol, side, quantity, entry_price, 
                                   tp1_price, tp2_price, tp3_price, order_id,
                                   tp1_order_id, tp2_order_id, tp3_order_id, status,
                                   current_sl, filled_at
                            FROM trades
                            WHERE order_id = %s 
                               OR tp1_order_id = %s 
                               OR tp2_order_id = %s 
                               OR tp3_order_id = %s
                            """,
                            (order_id, order_id, order_id, order_id)
                        )

                        trade_order_id = None

                        if result:
                            trade = result[0]
                            trade_order_id = trade['order_id']

                        # Xử lý stop loss
                        if orderStoploss == 'StopLoss' and order_id == trade_order_id:
                            self.execute_query(
                                """
                                UPDATE trades 
                                SET status = %s 
                                WHERE symbol = %s 
                                AND status != 'CANCELLED' 
                                AND status != 'STOPLOSS'
                                """,
                                ('STOPLOSS', symbol),
                                commit=True
                            )
                            continue
                        
                        # Xử lý take profit
                        if orderStoploss == 'TakeProfit' and order_id == trade_order_id:
                            self.execute_query(
                                """
                                UPDATE trades 
                                SET status = %s 
                                WHERE symbol = %s 
                                AND status != 'CANCELLED' 
                                AND status != 'TAKEPROFIT'
                                """,
                                ('TAKEPROFIT', symbol),
                                commit=True
                            )
                            continue
                        
                        # Lấy thông tin trade từ database
                       
                        
                        if not result:
                            logger.info(f"No trade found for order_id {order_id}")
                            continue
                            
                        trade = result[0]
                        trade_id = trade['id']
                        print("trade_id", trade)
                        
                        if status == 'Filled':
                            if order_id == trade['order_id']:
                                if trade['filled_at'] is not None:
                                    logger.info(f"Trade {trade_id}: Order {order_id} already processed as FILLED")
                                    continue
                                
                                # Lệnh chính (entry) đã khớp
                                filled_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                self.execute_query(
                                    "UPDATE trades SET status = %s, filled_at = %s WHERE id = %s",
                                    ('FILLED', filled_time, trade_id),
                                    commit=True
                                )
                                logger.info(f"Trade {trade_id}: Order {order_id} filled")

                                # Đặt lệnh TP1, TP2, TP3
                                position_idx = 1 if side == 'Buy' else 2
                                tp_result = self.place_tp_orders(
                                    trade_id=trade_id,
                                    symbol=symbol,
                                    side=side,
                                    quantity=float(trade['quantity']),
                                    tp1_price=float(trade['tp1_price']),
                                    tp2_price=float(trade['tp2_price']),
                                    tp3_price=float(trade['tp3_price']),
                                    position_idx=position_idx,
                                    entry_price=float(trade['entry_price'])
                                )
                                logger.info(f"TP orders placed for trade {trade_id}: {tp_result}")
                                continue

                            elif order_id == trade['tp1_order_id'] and trade['current_sl'] != trade['entry_price'] and trade['status'] == 'FILLED':
                                # TP1 đã khớp, dời stoploss lên entry price
                                self.update_stoploss(trade_id, trade['entry_price'])
                                self.execute_query(
                                    "UPDATE trades SET status = %s, current_tp = %s WHERE id = %s",
                                    ('TP1_HIT', trade['tp1_price'], trade_id),
                                    commit=True
                                )
                                logger.info(f"Trade {trade_id}: TP1 hit, SL moved to {trade['entry_price']}")
                                continue

                            elif order_id == trade['tp2_order_id'] and trade['status'] == 'TP1_HIT' and trade['current_sl'] != trade['tp1_price']:
                                # TP2 đã khớp, dời stoploss lên TP1
                                self.update_stoploss(trade_id, trade['tp1_price'])
                                self.execute_query(
                                    "UPDATE trades SET status = %s, current_tp = %s WHERE id = %s",
                                    ('TP2_HIT', trade['tp2_price'], trade_id),
                                    commit=True
                                )
                               
                                logger.info(f"Trade {trade_id}: TP2 hit, SL moved to {trade['tp1_price']}")
                                continue

                        elif status == 'Cancelled' and trade['order_id'] == order_id:
                            # Xử lý lệnh bị hủy
                            self.execute_query(
                                "UPDATE trades SET status = %s WHERE id = %s",
                                ('CANCELLED', trade_id),
                                commit=True
                            )
                            logger.info(f"Trade {trade_id}: Order {order_id} cancelled")

                except Exception as e:
                    logger.error(f"Error in order WebSocket: {str(e)}")

            self.ws_private.order_stream(callback=handle_order_message)

            logger.info("WebSocket started")
            while self.running:
                time.sleep(1)

        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}")
            raise
        finally:
            self.running = False
            if self.ws:
                self.ws.exit()
            if self.ws_private:
                self.ws_private.exit()
            logger.info("WebSocket connections closed")

    def shutdown(self, signum, frame):
        """Xử lý dừng bot an toàn."""
        logger.info("Shutting down bot...")
        self.running = False
        self.__del__()

    def __del__(self):
        """Đóng kết nối cơ sở dữ liệu, connection pool và WebSocket."""
        try:
            # Đóng kết nối WebSocket nếu có
            if hasattr(self, 'ws'):
                self.ws.exit()
            if hasattr(self, 'ws_private'):
                self.ws_private.exit()
                logger.info("WebSocket connections closed")
                
            # Đóng connection pool nếu có
            if hasattr(self, 'db_pool') and self.db_pool is not None:
                # Lấy tất cả các kết nối từ pool và đóng chúng
                try:
                    for _ in range(self.db_config.get('pool_size', 5)):
                        try:
                            conn = self.db_pool.get_connection()
                            conn.close()
                        except:
                            continue
                    logger.info("Database connection pool closed")
                except Exception as e:
                    logger.error(f"Error closing connection pool: {str(e)}")
                    
            # Đóng kết nối cũ nếu có
            if hasattr(self, 'cursor'):
                try:
                    self.cursor.close()
                except:
                    pass
                    
            if hasattr(self, 'db') and hasattr(self.db, 'is_connected') and self.db.is_connected():
                try:
                    self.db.close()
                    logger.info("Legacy database connection closed")
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
        finally:
            # Đánh dấu để chắc chắn các tài nguyên đã được giải phóng
            print(1234)
            self.running = False
    def check_and_cancel_old_orders(self):
        # Thời điểm hiện tại
            current_time = datetime.now()
            # Thời điểm 30 phút trước
            thirty_minutes_ago = current_time - timedelta(minutes=60)

            # Truy vấn các giao dịch có trạng thái OPEN và được tạo trước 30 phút
            query = """
                SELECT id, order_id, symbol, created_at, status
                FROM trades
                WHERE status = 'OPEN'
                AND created_at <= %s
            """
            print(f"Retrieved 0 trades with filters bot_name='', status='all'")
            trades = self.execute_query(
                query=query,
                params=(thirty_minutes_ago,),
                fetch=True,
                commit=False
            )

            print(f"Retrieved {len(trades) if trades else 0} trades with filters bot_name='', status='all'")

            if not trades:
                logger.info("No OPEN trades older than 30 minutes found")
                return
            for trade in trades:
                trade_id = trade['id']
                order_id = trade['order_id']
                symbol = trade['symbol']
                try:
                    # Hủy lệnh trên Bybit
                    cancel_response = self.cancel_order(symbol, order_id)
                    if cancel_response.get('retCode', -1) == 0:
                        # Cập nhật trạng thái giao dịch trong cơ sở dữ liệu
                        self.update_trade_status(trade_id, 'CANCELLED', datetime.now())
                       
                except Exception as e:
                    logger.error(f"Error processing trade {trade_id}: {str(e)}")
    def schedule_jobs(self):
        """Lên lịch các công việc định kỳ."""
        schedule.every(10).minutes.do(self.check_and_cancel_old_orders)
        logger.info("Scheduled job to check and cancel old orders every 5 minutes")

    def run_scheduled_jobs(self):
        """Chạy các công việc định kỳ trong một luồng riêng."""
        logger.info("Starting run_scheduled_jobs")
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)
            except Exception as e:
                logger.error(f"Error in run_scheduled_jobs: {str(e)}")

    def start_schedule_thread(self):
        """Khởi động luồng riêng cho lịch trình."""
        schedule_thread = threading.Thread(target=self.run_scheduled_jobs, daemon=True)
        schedule_thread.start()
        logger.info("Schedule thread started")
    def stop_websocket(self):
        """Dừng WebSocket an toàn."""
        self.running = False
        try:
            if self.ws:
                self.ws.exit()
                logger.info("Public WebSocket connection closed")
            if self.ws_private:
                self.ws_private.exit()
                logger.info("Private WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error closing WebSocket connections: {str(e)}")
        finally:
            self.ws = None
            self.ws_private = None
            logger.info("WebSocket connections fully closed")
    def safe_float(self, value, default=0.0):
        """Chuyển đổi an toàn giá trị sang float, thrtrả về giá trị mặc định nếu lỗi."""
        if value is None or value == '':
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def get_account_info(self) -> Dict[str, Any]:
        """Lấy thông tin tài khoản từ Bybit."""
        try:
            response = self.client.get_wallet_balance(accountType="UNIFIED")
            if response.get('retCode') == 0:
                result = response.get('result', {})
                usdt_balance = next(
                    (item for item in result.get('list', []) 
                     if item.get('accountType') == 'UNIFIED' and item.get('coin', [{}])[0].get('coin') == 'USDT'),
                    {}
                )
                if usdt_balance and 'coin' in usdt_balance and usdt_balance['coin']:
                    coin_info = usdt_balance['coin'][0]
                    return {
                        'available_balance': self.safe_float(coin_info.get('availableToWithdraw')),
                        'wallet_balance': self.safe_float(coin_info.get('walletBalance')),
                        'total_equity': self.safe_float(coin_info.get('equity')),
                        'total_margin_balance': self.safe_float(coin_info.get('totalPositionIM')),
                        'total_position_value': self.safe_float(coin_info.get('totalPositionMM')),
                        'total_initial_margin': self.safe_float(coin_info.get('totalInitialMargin')),
                        'total_maintenance_margin': self.safe_float(coin_info.get('totalMaintenanceMargin')),
                        'total_position_im': self.safe_float(coin_info.get('totalPositionIM')),
                        'total_position_margin': self.safe_float(coin_info.get('totalPositionMM')),
                        'total_available_balance': self.safe_float(coin_info.get('availableToWithdraw')),
                        'total_percent_available': self.safe_float(coin_info.get('totalPerpUPL')),
                        'total_unrealised_pnl': self.safe_float(coin_info.get('totalUnrealisedPnl')),
                        'total_realised_pnl': self.safe_float(coin_info.get('totalRealisedPnl'))
                    }
                logger.warning("Không tìm thấy thông tin số dư USDT")
                return {}
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                logger.error(f"Lỗi khi lấy thông tin tài khoản: {error_msg}")
                return {}
        except Exception as e:
            logger.error(f"Lỗi trong get_account_info: {str(e)}", exc_info=True)
            return {}

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các vị thế đang mở
        
        Returns:
            List[Dict[str, Any]]: Danh sách các vị thế với thông tin chi tiết
        """
        def safe_float(value, default=0.0):
            """Chuyển đổi an toàn giá trị sang float"""
            if value is None or value == '':
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
                
        try:
            response = self.client.get_positions(
                category="linear",  # Spot/linear/option
                settleCoin="USDT"   # Chỉ lấy vị thế USDT
            )
            
            if response.get('retCode') == 0 and 'result' in response:
                positions = []
                for pos in response['result'].get('list', []):
                    size = safe_float(pos.get('size'))
                    if size > 0:  # Chỉ lấy các vị thế đang mở
                        positions.append({
                            'symbol': pos.get('symbol'),
                            'side': pos.get('side'),
                            'size': size,
                            'position_value': safe_float(pos.get('positionValue')),
                            'entry_price': safe_float(pos.get('avgPrice')),
                            'liq_price': safe_float(pos.get('liqPrice')),
                            'mark_price': safe_float(pos.get('markPrice')),
                            'leverage': safe_float(pos.get('leverage'), 1),
                            'unrealised_pnl': safe_float(pos.get('unrealisedPnl')),
                            'realised_pnl': safe_float(pos.get('realisedPnl')),
                            'take_profit': safe_float(pos.get('takeProfit')),
                            'stop_loss': safe_float(pos.get('stopLoss')),
                            'timestamp': int(safe_float(pos.get('updatedTime'), 0))
                        })
                return positions
            else:
                self.logger.error(f"Lỗi khi lấy danh sách vị thế: {response}")
                return []
                
        except Exception as e:
            self.logger.error(f"Lỗi trong get_positions: {str(e)}", exc_info=True)
            return []
    # def job():
    #     """Hàm này sẽ được gọi mỗi giờ"""
    #     try:
    #         current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #         print(f"Chạy công việc lúc: {current_time}")
            
    #         # Thêm logic của bạn vào đây
    #         # Ví dụ: kiểm tra điều kiện, gọi API, xử lý dữ liệu...
            
    #     except Exception as e:
    #         print(f"Lỗi khi chạy công việc: {str(e)}")

    # # Lên lịch chạy mỗi giờ
    # schedule.every().hour.at(":00").do(job)