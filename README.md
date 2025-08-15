# Auto Trading System for Bybit

Hệ thống tự động giao dịch trên sàn Bybit với 2 chiến lược chính:
1. Chiến lược 1: Đặt lệnh 100 USD, khi đạt TP1 thì dời SL lên entry và TP lên TP2
2. Chiến lược 2: Đặt lệnh 200 USD, khi đạt TP1 thì chốt 100 USD và giữ 100 USD còn lại

## Yêu cầu hệ thống

- Python 3.8+
- Node.js 16+
- MySQL 8.0+
- Redis (tùy chọn, cho caching)

## Cài đặt

### 1. Cài đặt Backend

```bash
# Tạo và kích hoạt môi trường ảo
python -m venv venv
.\venv\Scripts\activate  # Trên Windows
source venv/bin/activate  # Trên macOS/Linux

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

### 2. Cấu hình cơ sở dữ liệu

1. Tạo database mới trong MySQL
2. Chạy file schema.sql để tạo bảng:

```bash
mysql -u your_username -p your_database_name < database/schema.sql
```

### 3. Cấu hình biến môi trường

Tạo file `.env` trong thư mục gốc với nội dung:

```env
# Database
DB_HOST=localhost
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=auto_trader

# Bybit API
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_api_secret
BYBIT_TESTNET=true  # Sử dụng testnet (true/false)

# JWT (cho xác thực)
JWT_SECRET=your_jwt_secret
JWT_ALGORITHM=HS256

# Cấu hình khác
CHECK_INTERVAL=60  # Thời gian kiểm tra lệnh (giây)
```

### 4. Cài đặt Frontend

```bash
cd frontend
npm install
```

## Chạy ứng dụng

### 1. Khởi động Backend

```bash
# Trong thư mục backend
uvicorn main:app --reload
```

### 2. Khởi động Worker kiểm tra lệnh

```bash
python backend/check_orders_worker.py
```

### 3. Khởi động Frontend

```bash
cd frontend
npm run dev
```

Truy cập ứng dụng tại: http://localhost:3000

## API Endpoints

### Tạo lệnh mới

```
POST /api/trade
```

**Body:**

```json
{
  "symbol": "BTCUSDT",
  "entry": 50000.0,
  "tp1": 50500.0,
  "tp2": 51000.0,
  "tp3": 51500.0,
  "sl": 49500.0,
  "position_size": 100.0,
  "strategy_type": "strategy1",
  "side": "Buy",
  "leverage": 10
}
```

### Lấy danh sách lệnh

```
GET /api/trades?limit=10&status=OPEN
```

### Cập nhật trạng thái lệnh

```
PUT /api/trade/{trade_id}
```

**Body:**

```json
{
  "status": "TP1_HIT",
  "pnl": 50.0,
  "current_price": 50500.0,
  "current_sl": 50000.0,
  "current_tp": 51000.0
}
```

### Kiểm tra và cập nhật lệnh tự động

```
POST /api/check-orders
```

## Các bước triển khai lên production

1. Tắt chế độ debug trong FastAPI
2. Sử dụng ASGI server như uvicorn với gunicorn
3. Cấu hình HTTPS với reverse proxy (Nginx/Apache)
4. Sử dụng PM2 hoặc systemd để quản lý tiến trình
5. Bật chế độ mainnet khi đã test xong

## Bảo mật

- Không commit file .env lên git
- Sử dụng API key với quyền hạn tối thiểu
- Bật xác thực 2 yếu tố cho tài khoản API
- Giới hạn địa chỉ IP được phép gọi API

## Giấy phép

MIT
