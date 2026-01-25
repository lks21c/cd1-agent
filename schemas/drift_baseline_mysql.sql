-- Drift Baselines Table Schema for MySQL/RDS
-- Version: 1.0.0
-- Compatible with: MySQL 8.0+, Amazon RDS MySQL
--
-- Purpose: Store configuration baselines for drift detection
-- Features:
--   - Version management with automatic history tracking
--   - JSON configuration storage with hash for change detection
--   - Triggers for automatic history recording

-- ============================================================================
-- Main Baselines Table (Current Active Version)
-- ============================================================================

CREATE TABLE IF NOT EXISTS drift_baselines (
    -- Composite Primary Key
    resource_type VARCHAR(50) NOT NULL COMMENT 'Resource type (glue, athena, emr, etc.)',
    resource_id VARCHAR(255) NOT NULL COMMENT 'Resource identifier',

    -- Version Information
    version INT NOT NULL DEFAULT 1 COMMENT 'Current version number',

    -- Baseline Configuration (JSON)
    config JSON NOT NULL COMMENT 'Expected configuration as JSON',
    config_hash VARCHAR(64) NOT NULL COMMENT 'SHA256 hash for change detection',

    -- Metadata
    resource_arn VARCHAR(512) COMMENT 'Full AWS ARN of the resource',
    description TEXT COMMENT 'Human-readable description',
    tags JSON COMMENT 'Resource tags as JSON',

    -- Timestamps (UTC)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update time',

    -- Audit Fields
    created_by VARCHAR(100) COMMENT 'User/system that created the baseline',
    updated_by VARCHAR(100) COMMENT 'User/system that last updated the baseline',

    -- Primary Key
    PRIMARY KEY (resource_type, resource_id),

    -- Indexes for Common Queries
    INDEX idx_resource_type (resource_type),
    INDEX idx_updated_at (updated_at),
    INDEX idx_config_hash (config_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- Baseline History Table (All Version History for Auditing)
-- ============================================================================

CREATE TABLE IF NOT EXISTS drift_baseline_history (
    -- Primary Key
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID v4 format',

    -- Resource Identification
    resource_type VARCHAR(50) NOT NULL COMMENT 'Resource type',
    resource_id VARCHAR(255) NOT NULL COMMENT 'Resource identifier',

    -- Version Information
    version INT NOT NULL COMMENT 'Version number at time of change',

    -- Change Type
    change_type ENUM('CREATE', 'UPDATE', 'DELETE') NOT NULL COMMENT 'Type of change',

    -- Configuration Diff
    previous_config JSON COMMENT 'Configuration before change (NULL for CREATE)',
    current_config JSON NOT NULL COMMENT 'Configuration after change',
    config_hash VARCHAR(64) NOT NULL COMMENT 'Hash of current config',

    -- Change Metadata
    change_reason TEXT COMMENT 'Why was this change made?',

    -- Timestamp
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When the change occurred',

    -- Audit
    changed_by VARCHAR(100) NOT NULL COMMENT 'Who made this change',

    -- Indexes
    INDEX idx_resource (resource_type, resource_id),
    INDEX idx_resource_version (resource_type, resource_id, version),
    INDEX idx_changed_at (changed_at),
    INDEX idx_changed_by (changed_by),
    INDEX idx_change_type (change_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- Triggers for Automatic History Recording
-- ============================================================================

DELIMITER //

-- Trigger: Record INSERT to history
CREATE TRIGGER drift_baselines_after_insert
AFTER INSERT ON drift_baselines
FOR EACH ROW
BEGIN
    INSERT INTO drift_baseline_history (
        id,
        resource_type,
        resource_id,
        version,
        change_type,
        previous_config,
        current_config,
        config_hash,
        change_reason,
        changed_by
    ) VALUES (
        UUID(),
        NEW.resource_type,
        NEW.resource_id,
        NEW.version,
        'CREATE',
        NULL,
        NEW.config,
        NEW.config_hash,
        'Initial baseline creation',
        COALESCE(NEW.created_by, 'system')
    );
END//

-- Trigger: Record UPDATE to history
CREATE TRIGGER drift_baselines_after_update
AFTER UPDATE ON drift_baselines
FOR EACH ROW
BEGIN
    -- Only record if config actually changed
    IF OLD.config_hash != NEW.config_hash THEN
        INSERT INTO drift_baseline_history (
            id,
            resource_type,
            resource_id,
            version,
            change_type,
            previous_config,
            current_config,
            config_hash,
            changed_by
        ) VALUES (
            UUID(),
            NEW.resource_type,
            NEW.resource_id,
            NEW.version,
            'UPDATE',
            OLD.config,
            NEW.config,
            NEW.config_hash,
            COALESCE(NEW.updated_by, 'system')
        );
    END IF;
END//

-- Trigger: Record DELETE to history
CREATE TRIGGER drift_baselines_after_delete
AFTER DELETE ON drift_baselines
FOR EACH ROW
BEGIN
    INSERT INTO drift_baseline_history (
        id,
        resource_type,
        resource_id,
        version,
        change_type,
        previous_config,
        current_config,
        config_hash,
        changed_by
    ) VALUES (
        UUID(),
        OLD.resource_type,
        OLD.resource_id,
        OLD.version + 1,
        'DELETE',
        OLD.config,
        JSON_OBJECT('_deleted', true, '_deleted_at', NOW()),
        OLD.config_hash,
        'system'
    );
END//

DELIMITER ;


-- ============================================================================
-- Drift Detection Results Table (Optional - for tracking detection history)
-- ============================================================================

CREATE TABLE IF NOT EXISTS drift_detection_results (
    -- Primary Key
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID v4 format',

    -- Detection Context
    detection_run_id VARCHAR(36) NOT NULL COMMENT 'ID of the detection run',
    resource_type VARCHAR(50) NOT NULL COMMENT 'Resource type',
    resource_id VARCHAR(255) NOT NULL COMMENT 'Resource identifier',

    -- Detection Result
    has_drift BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Whether drift was detected',
    severity ENUM('critical', 'high', 'medium', 'low') COMMENT 'Drift severity',

    -- Configuration Comparison
    baseline_config JSON NOT NULL COMMENT 'Expected configuration',
    current_config JSON NOT NULL COMMENT 'Actual current configuration',
    drift_details JSON COMMENT 'Detailed drift information',

    -- Timestamps
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Detection time',

    -- Resolution
    resolved_at TIMESTAMP COMMENT 'When drift was resolved',
    resolved_by VARCHAR(100) COMMENT 'Who resolved the drift',
    resolution_action ENUM('updated_baseline', 'reverted_resource', 'ignored', 'auto_resolved') COMMENT 'How it was resolved',
    resolution_notes TEXT COMMENT 'Notes about resolution',

    -- Indexes
    INDEX idx_detection_run (detection_run_id),
    INDEX idx_resource (resource_type, resource_id),
    INDEX idx_has_drift (has_drift),
    INDEX idx_severity (severity),
    INDEX idx_detected_at (detected_at),
    INDEX idx_unresolved (has_drift, resolved_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- Helper Views
-- ============================================================================

-- View: Current baselines with version count
CREATE OR REPLACE VIEW v_baselines_summary AS
SELECT
    b.resource_type,
    b.resource_id,
    b.version,
    b.config_hash,
    b.updated_at,
    b.updated_by,
    (SELECT COUNT(*) FROM drift_baseline_history h
     WHERE h.resource_type = b.resource_type
     AND h.resource_id = b.resource_id) as total_versions
FROM drift_baselines b;

-- View: Recent changes (last 7 days)
CREATE OR REPLACE VIEW v_recent_changes AS
SELECT
    h.id,
    h.resource_type,
    h.resource_id,
    h.version,
    h.change_type,
    h.changed_at,
    h.changed_by,
    h.change_reason
FROM drift_baseline_history h
WHERE h.changed_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY h.changed_at DESC;

-- View: Unresolved drifts
CREATE OR REPLACE VIEW v_unresolved_drifts AS
SELECT
    d.id,
    d.resource_type,
    d.resource_id,
    d.severity,
    d.detected_at,
    d.drift_details,
    TIMESTAMPDIFF(HOUR, d.detected_at, NOW()) as hours_unresolved
FROM drift_detection_results d
WHERE d.has_drift = TRUE
AND d.resolved_at IS NULL
ORDER BY
    FIELD(d.severity, 'critical', 'high', 'medium', 'low'),
    d.detected_at ASC;
