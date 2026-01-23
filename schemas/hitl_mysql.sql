-- HITL Requests Table Schema for MySQL/RDS
-- Version: 1.0.0
-- Compatible with: MySQL 8.0+, Amazon RDS MySQL

CREATE TABLE IF NOT EXISTS hitl_requests (
    -- Primary identifier
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID v4 format',

    -- Request classification
    agent_type ENUM('cost', 'bdp', 'hdsp', 'drift') NOT NULL COMMENT 'Agent type that created the request',
    request_type VARCHAR(50) NOT NULL COMMENT 'Type of HITL request',
    status ENUM('pending', 'approved', 'rejected', 'expired', 'cancelled') DEFAULT 'pending' COMMENT 'Current request status',

    -- Request content
    title VARCHAR(255) NOT NULL COMMENT 'Human-readable title',
    description TEXT COMMENT 'Detailed description of the request',
    payload JSON NOT NULL COMMENT 'Request payload with agent-specific data',
    response JSON COMMENT 'Response data after approval/rejection',

    -- Timestamps (UTC)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Request creation time',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update time',
    expires_at TIMESTAMP NOT NULL COMMENT 'Request expiration time',

    -- Audit fields
    created_by VARCHAR(100) COMMENT 'System/user that created the request',
    responded_by VARCHAR(100) COMMENT 'User that responded to the request',

    -- Indexes for common queries
    INDEX idx_status (status),
    INDEX idx_agent_status (agent_type, status),
    INDEX idx_expires (expires_at),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Optional: Add trigger for automatic expiration (alternative to scheduled job)
-- DELIMITER //
-- CREATE EVENT IF NOT EXISTS expire_hitl_requests
-- ON SCHEDULE EVERY 1 MINUTE
-- DO
--     UPDATE hitl_requests
--     SET status = 'expired', updated_at = CURRENT_TIMESTAMP
--     WHERE status = 'pending' AND expires_at < CURRENT_TIMESTAMP;
-- //
-- DELIMITER ;
