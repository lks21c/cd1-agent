-- MySQL Schema for BDP Agent (RDS substitute for LocalStack testing)
-- Creates tables for detection patterns and related data

USE cd1_agent;

-- Detection patterns table (main pattern storage)
CREATE TABLE IF NOT EXISTS detection_patterns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pattern_id VARCHAR(64) NOT NULL UNIQUE,
    pattern_name VARCHAR(255) NOT NULL,
    pattern_type ENUM('auth_failure', 'exception', 'timeout', 'resource_exhaustion', 'security') NOT NULL,
    regex_pattern TEXT NOT NULL,
    severity ENUM('low', 'medium', 'high', 'critical') NOT NULL DEFAULT 'medium',
    threshold INT NOT NULL DEFAULT 5,
    time_window_minutes INT NOT NULL DEFAULT 60,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_pattern_type (pattern_type),
    INDEX idx_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Application logs table (for log anomaly testing)
CREATE TABLE IF NOT EXISTS logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    service_name VARCHAR(128) NOT NULL,
    log_level ENUM('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL') NOT NULL,
    message TEXT NOT NULL,
    context JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_timestamp (timestamp),
    INDEX idx_service (service_name),
    INDEX idx_level (log_level),
    INDEX idx_service_level_time (service_name, log_level, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Authentication logs table (for auth failure pattern testing)
CREATE TABLE IF NOT EXISTS auth_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    username VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    success BOOLEAN NOT NULL,
    failure_reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_timestamp (timestamp),
    INDEX idx_username (username),
    INDEX idx_success (success),
    INDEX idx_failure_time (success, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Slow query log table (for DB timeout pattern testing)
CREATE TABLE IF NOT EXISTS slow_query_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    query_hash VARCHAR(64) NOT NULL,
    query_text TEXT NOT NULL,
    execution_time_ms INT NOT NULL,
    rows_examined BIGINT,
    rows_returned BIGINT,
    database_name VARCHAR(128),
    user_host VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_timestamp (timestamp),
    INDEX idx_execution_time (execution_time_ms),
    INDEX idx_query_hash (query_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Detection results table (for storing detection history)
CREATE TABLE IF NOT EXISTS detection_results (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    detection_id VARCHAR(64) NOT NULL UNIQUE,
    detection_type ENUM('log_anomaly', 'metric_anomaly', 'pattern_anomaly') NOT NULL,
    severity ENUM('low', 'medium', 'high', 'critical') NOT NULL,
    service_name VARCHAR(128),
    pattern_id VARCHAR(64),
    anomaly_details JSON NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_detection_type (detection_type),
    INDEX idx_severity (severity),
    INDEX idx_detected_at (detected_at),
    INDEX idx_service (service_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
