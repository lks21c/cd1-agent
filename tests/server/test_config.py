"""Tests for server configuration module."""

import os
from unittest.mock import patch

import pytest

from src.common.server.config import ServerSettings, get_settings


class TestServerSettings:
    """Tests for ServerSettings class."""

    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            settings = ServerSettings()

            assert settings.environment == "dev"
            assert settings.debug is False
            assert settings.port == 8000
            assert settings.host == "0.0.0.0"
            assert settings.log_level == "INFO"
            assert settings.aws_provider == "mock"
            assert settings.llm_provider == "mock"

    def test_environment_variables(self):
        """Test loading from environment variables."""
        env_vars = {
            "ENVIRONMENT": "production",
            "DEBUG": "true",
            "PORT": "9000",
            "AWS_PROVIDER": "real",
            "LLM_PROVIDER": "vllm",
            "RDS_HOST": "db.example.com",
            "RDS_PORT": "3307",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = ServerSettings()

            assert settings.environment == "production"
            assert settings.debug is True
            assert settings.port == 9000
            assert settings.aws_provider == "real"
            assert settings.llm_provider == "vllm"
            assert settings.rds_host == "db.example.com"
            assert settings.rds_port == 3307

    def test_is_production(self):
        """Test is_production property."""
        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}, clear=True):
            settings = ServerSettings()
            assert settings.is_production is True

        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            settings = ServerSettings()
            assert settings.is_production is True

        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}, clear=True):
            settings = ServerSettings()
            assert settings.is_production is False

    def test_is_localstack(self):
        """Test is_localstack property."""
        with patch.dict(os.environ, {"AWS_PROVIDER": "localstack"}, clear=True):
            settings = ServerSettings()
            assert settings.is_localstack is True

        with patch.dict(os.environ, {"AWS_PROVIDER": "real"}, clear=True):
            settings = ServerSettings()
            assert settings.is_localstack is False

    def test_rds_connection_string(self):
        """Test RDS connection string generation."""
        env_vars = {
            "RDS_HOST": "db.example.com",
            "RDS_PORT": "3306",
            "RDS_DATABASE": "testdb",
            "RDS_USER": "testuser",
            "RDS_PASSWORD": "testpass",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = ServerSettings()
            conn_str = settings.get_rds_connection_string()

            assert conn_str is not None
            assert "mysql+pymysql://" in conn_str
            assert "testuser:testpass" in conn_str
            assert "db.example.com:3306" in conn_str
            assert "/testdb" in conn_str

    def test_rds_connection_string_missing_values(self):
        """Test RDS connection string returns None when values missing."""
        with patch.dict(os.environ, {}, clear=True):
            settings = ServerSettings()
            assert settings.get_rds_connection_string() is None

    def test_get_settings_cached(self):
        """Test get_settings returns cached instance."""
        get_settings.cache_clear()  # Clear cache for test

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

        get_settings.cache_clear()  # Clean up


class TestAgentSpecificSettings:
    """Tests for agent-specific settings."""

    def test_cost_agent_settings(self):
        """Test Cost agent specific settings."""
        env_vars = {
            "COST_PROVIDER": "localstack",
            "COST_SENSITIVITY": "0.8",
            "COST_HISTORY_TABLE": "custom-history",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = ServerSettings()

            assert settings.cost_provider == "localstack"
            assert settings.cost_sensitivity == 0.8
            assert settings.cost_history_table == "custom-history"

    def test_hdsp_agent_settings(self):
        """Test HDSP agent specific settings."""
        env_vars = {
            "PROMETHEUS_URL": "http://prometheus:9090",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = ServerSettings()

            assert settings.prometheus_url == "http://prometheus:9090"

    def test_drift_agent_settings(self):
        """Test Drift agent specific settings."""
        env_vars = {
            "ENABLE_DRIFT_ANALYSIS": "true",
            "MAX_DRIFTS_TO_ANALYZE": "15",
            "ANALYSIS_CONFIDENCE_THRESHOLD": "0.8",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = ServerSettings()

            assert settings.enable_drift_analysis is True
            assert settings.max_drifts_to_analyze == 15
            assert settings.analysis_confidence_threshold == 0.8
