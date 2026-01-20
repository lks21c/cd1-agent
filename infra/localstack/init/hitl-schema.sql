-- HITL (Human-in-the-Loop) Request Table Schema
-- This schema should be applied to the MySQL database used by all agents

CREATE TABLE IF NOT EXISTS hitl_requests (
    id VARCHAR(36) PRIMARY KEY,
    agent_type ENUM('cost', 'bdp', 'hdsp', 'drift') NOT NULL,
    request_type VARCHAR(50) NOT NULL,
    status ENUM('pending', 'approved', 'rejected', 'expired', 'cancelled') DEFAULT 'pending',
    title VARCHAR(255) NOT NULL,
    description TEXT,
    payload JSON NOT NULL,
    response JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    created_by VARCHAR(100),
    responded_by VARCHAR(100),
    INDEX idx_status (status),
    INDEX idx_agent_status (agent_type, status),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sample data for testing (optional)
-- INSERT INTO hitl_requests (id, agent_type, request_type, status, title, payload, expires_at, created_by)
-- VALUES (
--     UUID(),
--     'cost',
--     'action_approval',
--     'pending',
--     'High Cost Anomaly Detected - Approve Remediation',
--     '{"severity": "high", "service": "EC2", "cost_increase": 150.0}',
--     DATE_ADD(NOW(), INTERVAL 1 HOUR),
--     'cost-agent'
-- );
