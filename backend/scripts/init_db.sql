-- 在 DataGrip 中连接腾讯云 MySQL 后执行
-- 1. 创建数据库（若尚未创建）
CREATE DATABASE IF NOT EXISTS carmate DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE carmate;

-- 2. 后端启动时会自动建表；也可手动执行以下语句
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  phone VARCHAR(11) UNIQUE,
  email VARCHAR(100) UNIQUE,
  role VARCHAR(10) NOT NULL DEFAULT 'user',
  wechat_openid VARCHAR(64) UNIQUE,
  wechat_unionid VARCHAR(64) UNIQUE,
  nickname VARCHAR(64),
  avatar_url VARCHAR(255),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS verification_codes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  target VARCHAR(120) NOT NULL,
  code VARCHAR(6) NOT NULL,
  scene VARCHAR(20) NOT NULL,
  expires_at DATETIME NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_target (target)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_operation_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  username VARCHAR(50) NULL,
  role VARCHAR(10) NULL,
  action VARCHAR(40) NOT NULL,
  success TINYINT(1) NOT NULL DEFAULT 1,
  message VARCHAR(255) NULL,
  detail TEXT NULL,
  ip_address VARCHAR(45) NULL,
  user_agent VARCHAR(255) NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id),
  INDEX idx_username (username),
  INDEX idx_action (action),
  INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS history_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  type VARCHAR(20) NOT NULL,
  image_url VARCHAR(500) NULL,
  result_json TEXT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id),
  INDEX idx_type (type),
  INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS recognition_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  type VARCHAR(20) NOT NULL,
  result_summary VARCHAR(255) NULL,
  confidence FLOAT NULL,
  success TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id),
  INDEX idx_type (type),
  INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS alert_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  level VARCHAR(20) NOT NULL,
  title VARCHAR(200) NOT NULL,
  summary TEXT NULL,
  source VARCHAR(100) NULL,
  acknowledged TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_level (level),
  INDEX idx_acknowledged (acknowledged),
  INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS plate_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  history_record_id INT NOT NULL,
  session_id VARCHAR(36) NULL,
  user_id INT NULL,
  plate_no VARCHAR(20) NOT NULL,
  color VARCHAR(10) NULL,
  vehicle_type VARCHAR(20) NULL,
  confidence FLOAT NULL,
  first_seen FLOAT NULL,
  last_seen FLOAT NULL,
  appearances INT DEFAULT 1,
  source_type VARCHAR(10) NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_plate_no (plate_no),
  INDEX idx_history_record_id (history_record_id),
  INDEX idx_user_id (user_id),
  INDEX idx_session_id (session_id),
  INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
