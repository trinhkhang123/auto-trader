-- Tạo database nếu chưa tồn tại
  CREATE DATABASE IF NOT EXISTS `auto_trader` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

  USE `auto_trader`;

  -- Bảng lưu thông tin các lệnh giao dịch
  CREATE TABLE IF NOT EXISTS `trades` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `order_id` varchar(100) DEFAULT NULL COMMENT 'ID lệnh từ sàn giao dịch',
    `symbol` varchar(20) NOT NULL COMMENT 'Mã giao dịch (Ví dụ: BTCUSDT, ETHUSDT)',
    `bot_name` varchar(20) NOT NULL COMMENT 'Tên bot',
    `side` enum('Buy','Sell') NOT NULL COMMENT 'Mua/Bán',
    `entry_price` decimal(20,8) NOT NULL COMMENT 'Giá vào lệnh',
    `quantity` decimal(20,8) NOT NULL COMMENT 'Số lượng',
    `position_size` decimal(20,8) NOT NULL COMMENT 'Giá trị vị thế (USD)',
    `leverage` int(11) NOT NULL DEFAULT '10' COMMENT 'Đòn bẩy',
    `tp1_price` decimal(20,8) DEFAULT NULL COMMENT 'Giá chốt lời 1',
    `tp2_price` decimal(20,8) DEFAULT NULL COMMENT 'Giá chốt lời 2',
    `tp3_price` decimal(20,8) DEFAULT NULL COMMENT 'Giá chốt lời 3',
    `sl_price` decimal(20,8) NOT NULL COMMENT 'Giá dừng lỗ',
    `current_sl` decimal(20,8) DEFAULT NULL,
    `current_tp` decimal(20,8) DEFAULT NULL,
    `strategy_type` enum('strategy1','strategy2') NOT NULL COMMENT 'Loại chiến lược',
    `status` varchar(50) NOT NULL DEFAULT 'OPEN',
    `tp1_order_id` varchar(100) DEFAULT NULL,
    `tp2_order_id` varchar(100) DEFAULT NULL,
    `tp3_order_id` varchar(100) DEFAULT NULL,
    `pnl` decimal(20,8) DEFAULT '0.00000000' COMMENT 'Lợi nhuận/lỗ',
    `pnl_percent` decimal(20,8) DEFAULT '0.0000' COMMENT 'Lợi nhuận/lỗ %',
    `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `closed_at` timestamp NULL DEFAULT NULL,
    `filled_at` timestamp NULL DEFAULT NULL COMMENT 'Thời gian lệnh được khớp',
    PRIMARY KEY (`id`),
    KEY `idx_symbol` (`symbol`),
    KEY `idx_status` (`status`),
    KEY `idx_created_at` (`created_at`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

  -- Bảng lưu lịch sử cập nhật lệnh
  CREATE TABLE IF NOT EXISTS `trade_updates` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `trade_id` bigint(20) NOT NULL,
    `status` varchar(50) NOT NULL COMMENT 'Trạng thái khi cập nhật',
    `price` decimal(20,8) DEFAULT NULL COMMENT 'Giá thị trường khi cập nhật',
    `sl_price` decimal(20,8) DEFAULT NULL COMMENT 'Giá SL hiện tại',
    `tp_price` decimal(20,8) DEFAULT NULL COMMENT 'Giá TP hiện tại',
    `pnl` decimal(20,8) DEFAULT NULL COMMENT 'Lợi nhuận/lỗ tại thời điểm đó',
    `notes` text COMMENT 'Ghi chú (nếu có)',
    `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_trade_id` (`trade_id`),
    KEY `idx_created_at` (`created_at`),
    CONSTRAINT `fk_trade_updates_trade` FOREIGN KEY (`trade_id`) REFERENCES `trades` (`id`) ON DELETE CASCADE
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

  -- Bảng cấu hình hệ thống
  CREATE TABLE IF NOT EXISTS `system_settings` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `setting_key` varchar(100) NOT NULL,
    `setting_value` text,
    `description` varchar(255) DEFAULT NULL,
    `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `idx_setting_key` (`setting_key`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

  -- Thêm một số cấu hình mặc định
  INSERT IGNORE INTO `system_settings` (`setting_key`, `setting_value`, `description`) VALUES
  ('api_key', '', 'API Key cho sàn giao dịch'),
  ('api_secret', '', 'API Secret cho sàn giao dịch'),
  ('testnet', '1', 'Sử dụng testnet (1) hoặc mainnet (0)'),
  ('max_position_size', '1000', 'Giá trị vị thế tối đa (USD)'),
  ('max_leverage', '10', 'Đòn bẩy tối đa'),
  ('default_leverage', '10', 'Đòn bẩy mặc định'),
  ('risk_per_trade', '1', 'Rủi ro mỗi lệnh (% tài khoản)');