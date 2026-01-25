-- ============================================================
-- BDP Cost Agent - Cost Baseline Configuration Schema
-- ============================================================
-- 서비스별 비용 임계치 및 탐지 설정을 저장하는 베이스라인 테이블
--
-- Usage:
--   MySQL/RDS: mysql -u user -p database < cost_baselines.sql
--   LocalStack: docker exec mysql mysql -u root -p cd1_agent < cost_baselines.sql
-- ============================================================

-- 비용 베이스라인 설정 테이블
-- 각 AWS 계정/서비스별 비용 기준선 설정을 저장
CREATE TABLE IF NOT EXISTS cost_baselines (
    -- Primary Key (복합키)
    account_id VARCHAR(12) NOT NULL COMMENT 'AWS 계정 ID',
    service_name VARCHAR(128) NOT NULL COMMENT 'AWS 서비스명 (Amazon Athena, AWS Lambda 등)',

    -- Account Info
    account_name VARCHAR(128) COMMENT '계정 별칭',

    -- Cost Thresholds
    expected_daily_cost DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '예상 일일 비용 (USD)',
    cost_threshold_ratio DECIMAL(4, 2) NOT NULL DEFAULT 1.50 COMMENT '임계 비율 (기본 1.5x)',
    absolute_threshold DECIMAL(12, 2) COMMENT '절대 임계값 (USD, NULL이면 비율만 사용)',

    -- Detection Settings
    sensitivity DECIMAL(3, 2) NOT NULL DEFAULT 0.50 COMMENT '탐지 민감도 (0.00-1.00)',
    min_cost_for_alert DECIMAL(10, 2) NOT NULL DEFAULT 1.00 COMMENT '알림 최소 비용 (노이즈 방지)',

    -- Known Patterns (예외 처리용)
    known_patterns JSON COMMENT '알려진 비용 패턴 (월초/월말, 배치 작업 등)',
    -- Example: {
    --   "monthly_patterns": ["month_start", "month_end"],
    --   "batch_jobs": ["daily_etl", "weekly_report"],
    --   "seasonal": ["q4_peak"],
    --   "excluded_hours": [0, 1, 2, 3, 4, 5]
    -- }

    -- Status
    enabled BOOLEAN NOT NULL DEFAULT TRUE COMMENT '활성화 여부',

    -- Metadata
    description TEXT COMMENT '베이스라인 설명',
    tags JSON COMMENT '태그 (JSON)',
    -- Example: {"team": "data-platform", "env": "prod", "cost_center": "CC001"}

    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
    created_by VARCHAR(128) COMMENT '생성자',
    updated_by VARCHAR(128) COMMENT '수정자',

    -- Constraints
    PRIMARY KEY (account_id, service_name),
    INDEX idx_account_id (account_id),
    INDEX idx_service_name (service_name),
    INDEX idx_enabled (enabled),
    INDEX idx_updated_at (updated_at),

    -- Validation
    CONSTRAINT chk_sensitivity CHECK (sensitivity >= 0.00 AND sensitivity <= 1.00),
    CONSTRAINT chk_threshold_ratio CHECK (cost_threshold_ratio > 0),
    CONSTRAINT chk_expected_cost CHECK (expected_daily_cost >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='비용 이상 탐지 베이스라인 설정';


-- 비용 베이스라인 변경 이력 테이블
-- 모든 베이스라인 변경 사항을 추적
CREATE TABLE IF NOT EXISTS cost_baseline_history (
    -- Primary Key
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID',

    -- Resource Reference
    account_id VARCHAR(12) NOT NULL COMMENT 'AWS 계정 ID',
    service_name VARCHAR(128) NOT NULL COMMENT 'AWS 서비스명',

    -- Change Info
    change_type ENUM('CREATE', 'UPDATE', 'DELETE') NOT NULL COMMENT '변경 유형',
    previous_config JSON COMMENT '이전 설정 (CREATE 시 NULL)',
    current_config JSON NOT NULL COMMENT '현재 설정',
    change_reason TEXT COMMENT '변경 사유',

    -- Audit
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '변경 시각',
    changed_by VARCHAR(128) NOT NULL COMMENT '변경자',

    -- Indexes
    INDEX idx_account_service (account_id, service_name),
    INDEX idx_changed_at (changed_at),
    INDEX idx_change_type (change_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='비용 베이스라인 변경 이력';


-- ============================================================
-- AWS Service Name Reference (참조용)
-- ============================================================
--
-- | Service Category | Service Name                    | Description              |
-- |------------------|---------------------------------|--------------------------|
-- | Compute          | Amazon EC2                      | EC2 인스턴스             |
-- | Compute          | AWS Lambda                      | Lambda 함수              |
-- | Storage          | Amazon S3                       | S3 스토리지              |
-- | Database         | Amazon RDS                      | RDS 데이터베이스         |
-- | Database         | Amazon DynamoDB                 | DynamoDB                 |
-- | Analytics        | Amazon Athena                   | Athena 쿼리              |
-- | Analytics        | Amazon EMR                      | EMR 클러스터             |
-- | Analytics        | AWS Glue                        | Glue 작업                |
-- | ML               | Amazon SageMaker                | SageMaker                |
-- | Streaming        | Amazon MSK                      | Managed Kafka            |
-- | Workflow         | Amazon MWAA                     | Managed Airflow          |
-- | Network          | Amazon CloudFront               | CDN                      |
-- | Network          | AWS Data Transfer               | 데이터 전송              |
-- ============================================================


-- ============================================================
-- Example Data (Optional - 개발/테스트용)
-- ============================================================

-- Athena 비용 베이스라인 예시
-- INSERT INTO cost_baselines (
--     account_id,
--     service_name,
--     account_name,
--     expected_daily_cost,
--     cost_threshold_ratio,
--     sensitivity,
--     min_cost_for_alert,
--     known_patterns,
--     enabled,
--     description,
--     tags,
--     created_by,
--     updated_by
-- ) VALUES (
--     '123456789012',
--     'Amazon Athena',
--     'data-platform-prod',
--     150.00,
--     1.5,
--     0.7,
--     5.00,
--     '{"monthly_patterns": ["month_end"], "batch_jobs": ["daily_report", "weekly_aggregation"]}',
--     TRUE,
--     'Production Athena workload - daily analytics queries',
--     '{"team": "data-platform", "env": "prod", "cost_center": "DP001"}',
--     'admin@company.com',
--     'admin@company.com'
-- );

-- Lambda 비용 베이스라인 예시
-- INSERT INTO cost_baselines (
--     account_id,
--     service_name,
--     account_name,
--     expected_daily_cost,
--     cost_threshold_ratio,
--     sensitivity,
--     min_cost_for_alert,
--     known_patterns,
--     enabled,
--     description,
--     tags,
--     created_by,
--     updated_by
-- ) VALUES (
--     '123456789012',
--     'AWS Lambda',
--     'data-platform-prod',
--     45.00,
--     2.0,
--     0.5,
--     2.00,
--     '{"batch_jobs": ["hourly_etl"], "excluded_hours": [0, 1, 2, 3]}',
--     TRUE,
--     'Production Lambda functions for data processing',
--     '{"team": "data-platform", "env": "prod"}',
--     'admin@company.com',
--     'admin@company.com'
-- );
