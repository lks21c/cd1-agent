-- Seed detection patterns for BDP Agent testing
-- These patterns are used for pattern_anomaly detection tests

USE cd1_agent;

-- Auth failure patterns
INSERT INTO detection_patterns (pattern_id, pattern_name, pattern_type, regex_pattern, severity, threshold, time_window_minutes, description) VALUES
('auth_failed_login', 'Failed Login Attempts', 'auth_failure',
 '(Failed login|Authentication failed|Invalid credentials|Login attempt failed)',
 'high', 5, 30, 'Detects multiple failed login attempts'),

('auth_account_lockout', 'Account Lockout', 'auth_failure',
 '(Account locked|Too many failed attempts|User account disabled)',
 'critical', 3, 60, 'Detects account lockout events'),

('auth_invalid_token', 'Invalid Token Access', 'auth_failure',
 '(Invalid token|Token expired|JWT validation failed|Unauthorized access)',
 'high', 10, 15, 'Detects invalid token access attempts');

-- Exception patterns
INSERT INTO detection_patterns (pattern_id, pattern_name, pattern_type, regex_pattern, severity, threshold, time_window_minutes, description) VALUES
('exc_null_pointer', 'NullPointerException', 'exception',
 '(NullPointerException|null reference|NoneType)',
 'medium', 5, 30, 'Detects null pointer exceptions'),

('exc_out_of_memory', 'OutOfMemoryError', 'exception',
 '(OutOfMemory|heap space|memory exhausted|OOM)',
 'critical', 1, 60, 'Detects out of memory errors'),

('exc_stack_overflow', 'StackOverflow', 'exception',
 '(StackOverflow|stack depth exceeded|recursive call)',
 'high', 3, 30, 'Detects stack overflow errors'),

('exc_general', 'General Exception', 'exception',
 '(Exception:|Error:|FATAL:|CRITICAL:)',
 'medium', 10, 15, 'Detects general exceptions and errors');

-- Timeout patterns
INSERT INTO detection_patterns (pattern_id, pattern_name, pattern_type, regex_pattern, severity, threshold, time_window_minutes, description) VALUES
('timeout_connection', 'Connection Timeout', 'timeout',
 '(Connection timeout|connection timed out|connect timeout|ConnectTimeoutException)',
 'high', 5, 30, 'Detects connection timeout errors'),

('timeout_read', 'Read Timeout', 'timeout',
 '(Read timeout|read timed out|socket timeout|SocketTimeoutException)',
 'high', 5, 30, 'Detects read timeout errors'),

('timeout_db', 'Database Timeout', 'timeout',
 '(Database timeout|query timeout|Lock wait timeout|deadlock)',
 'critical', 3, 30, 'Detects database timeout errors');

-- Resource exhaustion patterns
INSERT INTO detection_patterns (pattern_id, pattern_name, pattern_type, regex_pattern, severity, threshold, time_window_minutes, description) VALUES
('res_conn_pool', 'Connection Pool Exhausted', 'resource_exhaustion',
 '(Connection pool exhausted|no available connections|pool size exceeded)',
 'critical', 3, 30, 'Detects connection pool exhaustion'),

('res_disk_full', 'Disk Space Full', 'resource_exhaustion',
 '(No space left|disk full|storage quota exceeded)',
 'critical', 1, 60, 'Detects disk space issues'),

('res_thread_pool', 'Thread Pool Exhausted', 'resource_exhaustion',
 '(Thread pool exhausted|no available threads|task rejected)',
 'high', 5, 30, 'Detects thread pool exhaustion');

-- Security patterns
INSERT INTO detection_patterns (pattern_id, pattern_name, pattern_type, regex_pattern, severity, threshold, time_window_minutes, description) VALUES
('sec_sql_injection', 'SQL Injection Attempt', 'security',
 '(SQL injection|sqlmap|union select|OR 1=1)',
 'critical', 1, 60, 'Detects SQL injection attempts'),

('sec_xss_attempt', 'XSS Attempt', 'security',
 '(<script>|javascript:|onerror=|onload=)',
 'high', 3, 30, 'Detects XSS attempts'),

('sec_path_traversal', 'Path Traversal Attempt', 'security',
 '(\\.\\./|%2e%2e%2f|directory traversal)',
 'high', 3, 30, 'Detects path traversal attempts');

-- Insert some baseline normal logs
INSERT INTO logs (service_name, log_level, message, context) VALUES
('auth-service', 'INFO', 'Service started successfully', '{"version": "1.0.0"}'),
('auth-service', 'INFO', 'Health check passed', '{"status": "healthy"}'),
('api-gateway', 'INFO', 'Request processed', '{"latency_ms": 50}'),
('api-gateway', 'INFO', 'Cache hit', '{"cache_key": "user_123"}'),
('data-processor', 'INFO', 'Batch job completed', '{"records": 1000}');

-- Insert some baseline auth logs (successful)
INSERT INTO auth_logs (username, ip_address, success, failure_reason) VALUES
('user@example.com', '192.168.1.1', TRUE, NULL),
('admin@example.com', '192.168.1.2', TRUE, NULL),
('test@example.com', '192.168.1.3', TRUE, NULL);

-- Verify seed data
SELECT 'Detection patterns created: ' AS status, COUNT(*) AS count FROM detection_patterns;
SELECT 'Log entries created: ' AS status, COUNT(*) AS count FROM logs;
SELECT 'Auth log entries created: ' AS status, COUNT(*) AS count FROM auth_logs;
