-- Drift Baselines Table Schema for SQLite
-- Version: 1.0.0
-- Compatible with: SQLite 3.35+
--
-- Purpose: Store configuration baselines for drift detection (unit testing)
-- Features:
--   - Version management with automatic history tracking
--   - JSON configuration storage with hash for change detection
--   - Triggers for automatic history recording

-- ============================================================================
-- Main Baselines Table (Current Active Version)
-- ============================================================================

CREATE TABLE IF NOT EXISTS drift_baselines (
    -- Composite Primary Key
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,

    -- Version Information
    version INTEGER NOT NULL DEFAULT 1,

    -- Baseline Configuration (JSON)
    config TEXT NOT NULL CHECK(json_valid(config)),
    config_hash TEXT NOT NULL,

    -- Metadata
    resource_arn TEXT,
    description TEXT,
    tags TEXT CHECK(tags IS NULL OR json_valid(tags)),

    -- Timestamps (ISO 8601 format)
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    -- Audit Fields
    created_by TEXT,
    updated_by TEXT,

    -- Primary Key
    PRIMARY KEY (resource_type, resource_id)
);

-- Indexes for Common Queries
CREATE INDEX IF NOT EXISTS idx_baselines_type ON drift_baselines(resource_type);
CREATE INDEX IF NOT EXISTS idx_baselines_updated ON drift_baselines(updated_at);
CREATE INDEX IF NOT EXISTS idx_baselines_hash ON drift_baselines(config_hash);


-- ============================================================================
-- Baseline History Table (All Version History for Auditing)
-- ============================================================================

CREATE TABLE IF NOT EXISTS drift_baseline_history (
    -- Primary Key (UUID format check)
    id TEXT PRIMARY KEY CHECK(length(id) = 36),

    -- Resource Identification
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,

    -- Version Information
    version INTEGER NOT NULL,

    -- Change Type
    change_type TEXT NOT NULL CHECK(change_type IN ('CREATE', 'UPDATE', 'DELETE')),

    -- Configuration Diff
    previous_config TEXT CHECK(previous_config IS NULL OR json_valid(previous_config)),
    current_config TEXT NOT NULL CHECK(json_valid(current_config)),
    config_hash TEXT NOT NULL,

    -- Change Metadata
    change_reason TEXT,

    -- Timestamp
    changed_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    -- Audit
    changed_by TEXT NOT NULL
);

-- Indexes for History
CREATE INDEX IF NOT EXISTS idx_history_resource ON drift_baseline_history(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_history_version ON drift_baseline_history(resource_type, resource_id, version);
CREATE INDEX IF NOT EXISTS idx_history_changed ON drift_baseline_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_history_changed_by ON drift_baseline_history(changed_by);


-- ============================================================================
-- Triggers for Automatic Updates
-- ============================================================================

-- Trigger: Auto-update updated_at on UPDATE
CREATE TRIGGER IF NOT EXISTS drift_baselines_updated_at
AFTER UPDATE ON drift_baselines
FOR EACH ROW
WHEN OLD.config_hash != NEW.config_hash OR OLD.version != NEW.version
BEGIN
    UPDATE drift_baselines
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE resource_type = NEW.resource_type AND resource_id = NEW.resource_id;
END;


-- ============================================================================
-- Drift Detection Results Table (Optional)
-- ============================================================================

CREATE TABLE IF NOT EXISTS drift_detection_results (
    -- Primary Key
    id TEXT PRIMARY KEY CHECK(length(id) = 36),

    -- Detection Context
    detection_run_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,

    -- Detection Result
    has_drift INTEGER NOT NULL DEFAULT 0 CHECK(has_drift IN (0, 1)),
    severity TEXT CHECK(severity IN ('critical', 'high', 'medium', 'low')),

    -- Configuration Comparison
    baseline_config TEXT NOT NULL CHECK(json_valid(baseline_config)),
    current_config TEXT NOT NULL CHECK(json_valid(current_config)),
    drift_details TEXT CHECK(drift_details IS NULL OR json_valid(drift_details)),

    -- Timestamps
    detected_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    -- Resolution
    resolved_at TEXT,
    resolved_by TEXT,
    resolution_action TEXT CHECK(resolution_action IS NULL OR resolution_action IN ('updated_baseline', 'reverted_resource', 'ignored', 'auto_resolved')),
    resolution_notes TEXT
);

-- Indexes for Detection Results
CREATE INDEX IF NOT EXISTS idx_detection_run ON drift_detection_results(detection_run_id);
CREATE INDEX IF NOT EXISTS idx_detection_resource ON drift_detection_results(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_detection_drift ON drift_detection_results(has_drift);
CREATE INDEX IF NOT EXISTS idx_detection_severity ON drift_detection_results(severity);
CREATE INDEX IF NOT EXISTS idx_detection_detected ON drift_detection_results(detected_at);


-- ============================================================================
-- Helper Views
-- ============================================================================

-- View: Current baselines with version count
CREATE VIEW IF NOT EXISTS v_baselines_summary AS
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
CREATE VIEW IF NOT EXISTS v_recent_changes AS
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
WHERE h.changed_at >= datetime('now', '-7 days')
ORDER BY h.changed_at DESC;

-- View: Unresolved drifts
CREATE VIEW IF NOT EXISTS v_unresolved_drifts AS
SELECT
    d.id,
    d.resource_type,
    d.resource_id,
    d.severity,
    d.detected_at,
    d.drift_details,
    CAST((julianday('now') - julianday(d.detected_at)) * 24 AS INTEGER) as hours_unresolved
FROM drift_detection_results d
WHERE d.has_drift = 1
AND d.resolved_at IS NULL
ORDER BY
    CASE d.severity
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        WHEN 'low' THEN 4
    END,
    d.detected_at ASC;
