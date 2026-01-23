-- HITL Requests Table Schema for SQLite3
-- Version: 1.0.0
-- Compatible with: SQLite 3.35+
-- Purpose: Public network deployment (external environments)

CREATE TABLE IF NOT EXISTS hitl_requests (
    -- Primary identifier
    id TEXT PRIMARY KEY CHECK(length(id) = 36),  -- UUID v4 format

    -- Request classification
    agent_type TEXT NOT NULL CHECK(agent_type IN ('cost', 'bdp', 'hdsp', 'drift')),
    request_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled')),

    -- Request content
    title TEXT NOT NULL,
    description TEXT,
    payload TEXT NOT NULL CHECK(json_valid(payload)),  -- JSON stored as TEXT
    response TEXT CHECK(response IS NULL OR json_valid(response)),  -- JSON stored as TEXT

    -- Timestamps (ISO8601 format: YYYY-MM-DDTHH:MM:SS.sssZ)
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    expires_at TEXT NOT NULL,

    -- Audit fields
    created_by TEXT,
    responded_by TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_requests(status);
CREATE INDEX IF NOT EXISTS idx_hitl_agent_status ON hitl_requests(agent_type, status);
CREATE INDEX IF NOT EXISTS idx_hitl_expires ON hitl_requests(expires_at);
CREATE INDEX IF NOT EXISTS idx_hitl_created_at ON hitl_requests(created_at);

-- Trigger to auto-update updated_at on row modification
CREATE TRIGGER IF NOT EXISTS hitl_requests_updated_at
AFTER UPDATE ON hitl_requests
FOR EACH ROW
BEGIN
    UPDATE hitl_requests
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE id = NEW.id;
END;
