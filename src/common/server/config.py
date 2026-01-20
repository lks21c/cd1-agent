"""
Server Configuration using pydantic-settings.

Provides centralized configuration for all server components
with environment variable loading and validation.
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    """Server configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server Configuration
    environment: str = Field(default="dev", description="Deployment environment")
    debug: bool = Field(default=False, description="Enable debug mode")
    port: int = Field(default=8000, description="Server port")
    host: str = Field(default="0.0.0.0", description="Server host")
    workers: int = Field(default=1, description="Number of workers")
    log_level: str = Field(default="INFO", description="Logging level")

    # Agent Configuration
    agent_name: str = Field(default="generic", description="Agent name (cost, hdsp, bdp, drift)")

    # AWS Configuration
    aws_region: str = Field(default="ap-northeast-2", description="AWS region")
    aws_provider: str = Field(default="mock", description="AWS provider (mock, real, localstack)")
    aws_endpoint_url: Optional[str] = Field(default=None, description="AWS endpoint URL for LocalStack")

    # LLM Configuration
    llm_provider: str = Field(default="mock", description="LLM provider (mock, vllm, gemini)")
    llm_model: Optional[str] = Field(default=None, description="LLM model name")
    vllm_endpoint: str = Field(default="http://localhost:8000", description="vLLM endpoint URL")
    vllm_model: str = Field(default="gpt-oss-120b", description="vLLM model name")
    vllm_api_key: str = Field(default="", description="vLLM API key")
    gemini_model: str = Field(default="gemini-2.5-flash", description="Gemini model name")
    gemini_api_key: str = Field(default="", description="Gemini API key")

    # AWS Resources
    dynamodb_table: str = Field(default="cd1-agent-results", description="DynamoDB table name")
    event_bus: str = Field(default="cd1-agent-events", description="EventBridge event bus")
    knowledge_base_id: str = Field(default="", description="Bedrock knowledge base ID")

    # Agent Parameters
    max_iterations: int = Field(default=5, description="Max agent iterations")
    confidence_threshold: float = Field(default=0.85, description="Confidence threshold")

    # RDS Configuration (for BDP and HITL)
    rds_host: Optional[str] = Field(default=None, description="RDS host")
    rds_port: int = Field(default=3306, description="RDS port")
    rds_database: str = Field(default="cd1_agent", description="RDS database name")
    rds_user: Optional[str] = Field(default=None, description="RDS username")
    rds_password: Optional[str] = Field(default=None, description="RDS password")

    # Cost Agent Specific
    cost_provider: str = Field(default="mock", description="Cost provider (mock, real, localstack)")
    cost_sensitivity: float = Field(default=0.7, description="Cost anomaly sensitivity")
    cost_history_table: str = Field(default="bdp-cost-history", description="Cost history DynamoDB table")
    cost_anomaly_table: str = Field(default="bdp-cost-anomaly-tracking", description="Cost anomaly DynamoDB table")

    # HDSP Agent Specific
    prometheus_url: str = Field(default="http://localhost:9090", description="Prometheus URL")

    # Drift Agent Specific
    enable_drift_analysis: bool = Field(default=False, description="Enable LLM drift analysis")
    max_drifts_to_analyze: int = Field(default=10, description="Max drifts to analyze")
    analysis_confidence_threshold: float = Field(default=0.7, description="Analysis confidence threshold")

    # BDP Compact Agent Specific
    bdp_provider: str = Field(default="mock", description="BDP provider (mock, real, localstack)")
    bdp_sensitivity: float = Field(default=0.7, description="BDP cost drift sensitivity")
    bdp_currency: str = Field(default="KRW", description="BDP currency (KRW, USD)")
    bdp_min_cost_threshold: float = Field(default=10000, description="BDP minimum cost threshold")
    bdp_hitl_on_critical: bool = Field(default=True, description="Create HITL request on critical")

    # Metrics Configuration
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_prefix: str = Field(default="cd1_agent", description="Metrics name prefix")

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() in ("prod", "production")

    @property
    def is_localstack(self) -> bool:
        """Check if using LocalStack."""
        return self.aws_provider.lower() == "localstack"

    def get_rds_connection_string(self) -> Optional[str]:
        """Get RDS connection string if configured."""
        if not self.rds_host or not self.rds_user or not self.rds_password:
            return None
        return (
            f"mysql+pymysql://{self.rds_user}:{self.rds_password}@"
            f"{self.rds_host}:{self.rds_port}/{self.rds_database}"
        )


class AgentSettings(ServerSettings):
    """Agent-specific settings with validation."""

    agent_type: Literal["cost", "hdsp", "bdp", "drift"] = Field(
        default="cost",
        description="Type of agent server",
    )


@lru_cache
def get_settings() -> ServerSettings:
    """Get cached server settings instance."""
    return ServerSettings()


def get_agent_settings(agent_type: str) -> ServerSettings:
    """Get settings for specific agent type."""
    settings = ServerSettings()
    settings.agent_name = agent_type
    return settings
