-- ============================================================
-- BDP Drift Agent - Baseline Configuration Schema
-- ============================================================
-- 드리프트 탐지를 위한 베이스라인 설정 저장 테이블
--
-- Usage:
--   MySQL/RDS: mysql -u user -p database < drift_baselines.sql
--   LocalStack: docker exec mysql mysql -u root -p cd1_agent < drift_baselines.sql
-- ============================================================

-- 베이스라인 설정 테이블
-- 각 AWS 리소스의 기준 설정을 저장
CREATE TABLE IF NOT EXISTS drift_baselines (
    -- Primary Key (복합키)
    resource_type VARCHAR(64) NOT NULL COMMENT '리소스 타입 (lambda, s3, glue, athena, emr, sagemaker, mwaa, msk)',
    resource_id VARCHAR(255) NOT NULL COMMENT '리소스 식별자 (함수명, 버킷명, 클러스터명 등)',

    -- Version Control
    version INT NOT NULL DEFAULT 1 COMMENT '베이스라인 버전 (자동 증가)',

    -- Configuration
    config JSON NOT NULL COMMENT '베이스라인 설정 (JSON)',
    config_hash VARCHAR(64) NOT NULL COMMENT '설정의 SHA256 해시 (변경 감지용)',

    -- Metadata
    resource_arn VARCHAR(512) COMMENT 'AWS ARN',
    description TEXT COMMENT '베이스라인 설명',
    tags JSON COMMENT '태그 (JSON)',

    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
    created_by VARCHAR(128) COMMENT '생성자',
    updated_by VARCHAR(128) COMMENT '수정자',

    -- Constraints
    PRIMARY KEY (resource_type, resource_id),
    INDEX idx_resource_type (resource_type),
    INDEX idx_config_hash (config_hash),
    INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='드리프트 탐지 베이스라인 설정';


-- 베이스라인 변경 이력 테이블
-- 모든 베이스라인 변경 사항을 추적
CREATE TABLE IF NOT EXISTS drift_baseline_history (
    -- Primary Key
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID',

    -- Resource Reference
    resource_type VARCHAR(64) NOT NULL COMMENT '리소스 타입',
    resource_id VARCHAR(255) NOT NULL COMMENT '리소스 식별자',
    version INT NOT NULL COMMENT '변경 후 버전',

    -- Change Info
    change_type ENUM('CREATE', 'UPDATE', 'DELETE') NOT NULL COMMENT '변경 유형',
    previous_config JSON COMMENT '이전 설정 (CREATE 시 NULL)',
    current_config JSON NOT NULL COMMENT '현재 설정',
    config_hash VARCHAR(64) NOT NULL COMMENT '현재 설정 해시',
    change_reason TEXT COMMENT '변경 사유',

    -- Audit
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '변경 시각',
    changed_by VARCHAR(128) NOT NULL COMMENT '변경자',

    -- Indexes
    INDEX idx_resource (resource_type, resource_id),
    INDEX idx_version (resource_type, resource_id, version),
    INDEX idx_changed_at (changed_at),
    INDEX idx_change_type (change_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='드리프트 베이스라인 변경 이력';


-- ============================================================
-- Resource Type Reference (참조용 - 실제 테이블 아님)
-- ============================================================
--
-- | Type      | Value     | Description                    | Key Fields                              |
-- |-----------|-----------|--------------------------------|-----------------------------------------|
-- | Glue      | glue      | Glue Catalogue                 | columns, table_schema, parameters       |
-- | Athena    | athena    | Athena Workgroup               | encryption_configuration, engine_version|
-- | EMR       | emr       | EMR Cluster                    | release_label, instance_type, security  |
-- | SageMaker | sagemaker | SageMaker Endpoint             | endpoint_config, instance_type          |
-- | S3        | s3        | S3 Bucket                      | encryption, public_access_block         |
-- | MWAA      | mwaa      | MWAA Environment               | airflow_version, environment_class      |
-- | MSK       | msk       | MSK Cluster                    | kafka_version, number_of_broker_nodes   |
-- | Lambda    | lambda    | Lambda Function                | runtime, memory_size, timeout, layers   |
-- ============================================================


-- ============================================================
-- Example Data (Optional - 개발/테스트용)
-- ============================================================

-- Lambda 함수 베이스라인 예시
-- INSERT INTO drift_baselines (
--     resource_type,
--     resource_id,
--     version,
--     config,
--     config_hash,
--     resource_arn,
--     description,
--     created_by,
--     updated_by
-- ) VALUES (
--     'lambda',
--     'data-processor-prod',
--     1,
--     '{"function_name": "data-processor-prod", "runtime": "python3.11", "memory_size": 512, "timeout": 60, "role": "arn:aws:iam::123456789012:role/lambda-role"}',
--     SHA2('{"function_name": "data-processor-prod", "runtime": "python3.11", "memory_size": 512, "timeout": 60, "role": "arn:aws:iam::123456789012:role/lambda-role"}', 256),
--     'arn:aws:lambda:ap-northeast-2:123456789012:function:data-processor-prod',
--     'Production data processor Lambda',
--     'admin@company.com',
--     'admin@company.com'
-- );
