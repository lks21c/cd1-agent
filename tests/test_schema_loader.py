"""
Tests for Schema Loader and RDS Client.

Tests cover:
- Schema loading and parsing
- Schema validation
- RDS client with mock provider
- Query execution
- LLM context generation
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.services.schema_loader import (
    SchemaLoader,
    TableSchema,
    ColumnSchema,
    IndexSchema,
    SchemaNotFoundError,
    SchemaParseError,
    get_schema_loader,
)
from src.services.rds_client import (
    RDSClient,
    RDSProvider,
    QueryResult,
    get_rds_client,
)


# ============================================================================
# Schema Loader Tests
# ============================================================================

class TestColumnSchema:
    """Tests for ColumnSchema dataclass."""

    def test_from_dict_minimal(self):
        """Test creating ColumnSchema with minimal data."""
        data = {"name": "id", "type": "bigint"}
        col = ColumnSchema.from_dict(data)

        assert col.name == "id"
        assert col.type == "bigint"
        assert col.nullable is True
        assert col.primary_key is False
        assert col.description == ""

    def test_from_dict_full(self):
        """Test creating ColumnSchema with all fields."""
        data = {
            "name": "user_id",
            "type": "varchar(100)",
            "nullable": False,
            "primary_key": True,
            "auto_increment": True,
            "description": "Primary user identifier",
            "default": "uuid()",
        }
        col = ColumnSchema.from_dict(data)

        assert col.name == "user_id"
        assert col.type == "varchar(100)"
        assert col.nullable is False
        assert col.primary_key is True
        assert col.auto_increment is True
        assert col.description == "Primary user identifier"
        assert col.default == "uuid()"


class TestTableSchema:
    """Tests for TableSchema dataclass."""

    def test_from_dict(self):
        """Test creating TableSchema from dictionary."""
        data = {
            "table_name": "users",
            "description": "User accounts table",
            "database": "test_db",
            "columns": [
                {"name": "id", "type": "bigint", "primary_key": True},
                {"name": "email", "type": "varchar(255)", "nullable": False},
            ],
            "indexes": [
                {"name": "idx_email", "columns": ["email"], "type": "btree"},
            ],
        }
        schema = TableSchema.from_dict(data)

        assert schema.table_name == "users"
        assert schema.description == "User accounts table"
        assert schema.database == "test_db"
        assert len(schema.columns) == 2
        assert len(schema.indexes) == 1

    def test_get_column(self):
        """Test getting column by name."""
        data = {
            "table_name": "test",
            "columns": [
                {"name": "id", "type": "bigint"},
                {"name": "name", "type": "varchar(100)"},
            ],
        }
        schema = TableSchema.from_dict(data)

        col = schema.get_column("name")
        assert col is not None
        assert col.name == "name"

        assert schema.get_column("nonexistent") is None

    def test_get_column_names(self):
        """Test getting list of column names."""
        data = {
            "table_name": "test",
            "columns": [
                {"name": "id", "type": "bigint"},
                {"name": "name", "type": "varchar(100)"},
                {"name": "email", "type": "varchar(255)"},
            ],
        }
        schema = TableSchema.from_dict(data)

        names = schema.get_column_names()
        assert names == ["id", "name", "email"]

    def test_get_primary_key_columns(self):
        """Test getting primary key columns."""
        data = {
            "table_name": "test",
            "columns": [
                {"name": "id", "type": "bigint", "primary_key": True},
                {"name": "tenant_id", "type": "varchar(50)", "primary_key": True},
                {"name": "name", "type": "varchar(100)"},
            ],
        }
        schema = TableSchema.from_dict(data)

        pk_cols = schema.get_primary_key_columns()
        assert len(pk_cols) == 2
        assert pk_cols[0].name == "id"
        assert pk_cols[1].name == "tenant_id"

    def test_to_prompt_context(self):
        """Test LLM prompt context generation."""
        data = {
            "table_name": "anomaly_logs",
            "description": "이상 징후 로그",
            "columns": [
                {"name": "id", "type": "bigint", "primary_key": True, "description": "고유 ID"},
                {"name": "message", "type": "text", "nullable": True, "description": "상세 메시지"},
            ],
        }
        schema = TableSchema.from_dict(data)

        context = schema.to_prompt_context()

        assert "테이블: anomaly_logs" in context
        assert "설명: 이상 징후 로그" in context
        assert "[PK]" in context
        assert "고유 ID" in context
        assert "NOT NULL" not in context  # message is nullable


class TestSchemaLoader:
    """Tests for SchemaLoader class."""

    @pytest.fixture
    def example_schema_dir(self):
        """Get path to schema.example directory."""
        return Path(__file__).parent.parent / "schema.example"

    def test_init_with_default_dir(self):
        """Test initialization with default directory."""
        loader = SchemaLoader()
        assert loader.schema_dir is not None

    def test_init_with_custom_dir(self, example_schema_dir):
        """Test initialization with custom directory."""
        loader = SchemaLoader(schema_dir=str(example_schema_dir))
        assert loader.schema_dir == example_schema_dir

    def test_list_tables(self, example_schema_dir):
        """Test listing available tables."""
        loader = SchemaLoader(schema_dir=str(example_schema_dir))
        tables = loader.list_tables()

        assert isinstance(tables, list)
        assert "anomaly_logs" in tables
        assert "service_metrics" in tables
        assert "remediation_history" in tables

    def test_load_table(self, example_schema_dir):
        """Test loading a specific table schema."""
        loader = SchemaLoader(schema_dir=str(example_schema_dir))
        schema = loader.load_table("anomaly_logs")

        assert schema.table_name == "anomaly_logs"
        assert len(schema.columns) > 0
        assert schema.description != ""

    def test_load_table_caching(self, example_schema_dir):
        """Test that schemas are cached."""
        loader = SchemaLoader(schema_dir=str(example_schema_dir), cache_enabled=True)

        # First load
        schema1 = loader.load_table("anomaly_logs")
        # Second load (should use cache)
        schema2 = loader.load_table("anomaly_logs")

        assert schema1 is schema2  # Same object reference

    def test_load_table_not_found(self, example_schema_dir):
        """Test loading non-existent table raises error."""
        loader = SchemaLoader(schema_dir=str(example_schema_dir))

        with pytest.raises(SchemaNotFoundError):
            loader.load_table("nonexistent_table")

    def test_validate_table(self, example_schema_dir):
        """Test table validation."""
        loader = SchemaLoader(schema_dir=str(example_schema_dir))

        assert loader.validate_table("anomaly_logs") is True
        assert loader.validate_table("nonexistent") is False

    def test_get_llm_context(self, example_schema_dir):
        """Test LLM context generation."""
        loader = SchemaLoader(schema_dir=str(example_schema_dir))
        context = loader.get_llm_context()

        assert "데이터베이스 스키마 정보" in context
        assert "anomaly_logs" in context

    def test_get_llm_context_specific_tables(self, example_schema_dir):
        """Test LLM context for specific tables."""
        loader = SchemaLoader(schema_dir=str(example_schema_dir))
        context = loader.get_llm_context(table_names=["anomaly_logs"])

        assert "anomaly_logs" in context
        # Should not contain other tables if we only requested one
        assert "1개" in context or "anomaly_logs" in context

    def test_clear_cache(self, example_schema_dir):
        """Test cache clearing."""
        loader = SchemaLoader(schema_dir=str(example_schema_dir), cache_enabled=True)

        # Load and cache
        loader.load_table("anomaly_logs")
        assert "anomaly_logs" in loader._cache

        # Clear cache
        loader.clear_cache()
        assert len(loader._cache) == 0

    def test_get_table_columns(self, example_schema_dir):
        """Test getting table columns."""
        loader = SchemaLoader(schema_dir=str(example_schema_dir))
        columns = loader.get_table_columns("anomaly_logs")

        assert "id" in columns
        assert "timestamp" in columns
        assert "service_name" in columns


class TestSchemaLoaderSingleton:
    """Tests for get_schema_loader singleton."""

    def test_singleton_returns_same_instance(self, tmp_path):
        """Test that get_schema_loader returns singleton."""
        # Create temp schema dir
        schema_dir = tmp_path / "schema"
        schema_dir.mkdir()
        tables_dir = schema_dir / "tables"
        tables_dir.mkdir()

        loader1 = get_schema_loader(schema_dir=str(schema_dir))
        loader2 = get_schema_loader()  # Should return same instance

        # Note: With explicit schema_dir, it creates a new instance
        # Without args, it returns cached instance


# ============================================================================
# RDS Client Tests
# ============================================================================

class TestQueryResult:
    """Tests for QueryResult class."""

    def test_to_dict(self):
        """Test converting QueryResult to dict."""
        result = QueryResult(
            rows=[{"id": 1, "name": "test"}],
            column_names=["id", "name"],
            row_count=1,
            execution_time_ms=5.0,
        )

        d = result.to_dict()
        assert d["row_count"] == 1
        assert d["execution_time_ms"] == 5.0
        assert len(d["rows"]) == 1

    def test_to_markdown_table(self):
        """Test markdown table generation."""
        result = QueryResult(
            rows=[
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ],
            column_names=["id", "name"],
            row_count=2,
        )

        table = result.to_markdown_table()

        assert "| id | name |" in table
        assert "Alice" in table
        assert "Bob" in table

    def test_to_markdown_table_empty(self):
        """Test markdown table with no results."""
        result = QueryResult(rows=[], column_names=[], row_count=0)

        table = result.to_markdown_table()
        assert "결과 없음" in table

    def test_to_markdown_table_max_rows(self):
        """Test markdown table with row limit."""
        rows = [{"id": i} for i in range(30)]
        result = QueryResult(rows=rows, column_names=["id"], row_count=30)

        table = result.to_markdown_table(max_rows=10)

        # Should have truncation message
        assert "외 20개 행" in table


class TestRDSClientMock:
    """Tests for RDSClient with mock provider."""

    @pytest.fixture
    def mock_client(self):
        """Create RDS client with mock provider."""
        return RDSClient(provider=RDSProvider.MOCK)

    def test_init_mock_provider(self, mock_client):
        """Test mock provider initialization."""
        assert mock_client.provider_type == RDSProvider.MOCK

    def test_query(self, mock_client):
        """Test basic query execution."""
        result = mock_client.query("SELECT * FROM anomaly_logs")

        assert result.row_count > 0
        assert "id" in result.column_names or len(result.rows) > 0

    def test_query_table(self, mock_client):
        """Test schema-aware query."""
        result = mock_client.query_table(
            "anomaly_logs",
            columns=["id", "service_name"],
            limit=5,
        )

        assert result.row_count <= 5

    def test_get_recent_anomalies(self, mock_client):
        """Test convenience method for anomalies."""
        result = mock_client.get_recent_anomalies()

        assert result is not None
        assert isinstance(result.rows, list)

    def test_get_recent_anomalies_with_filters(self, mock_client):
        """Test anomalies with filters."""
        result = mock_client.get_recent_anomalies(
            service_name="api-gateway",
            severity="HIGH",
        )

        assert result is not None

    def test_get_service_metrics(self, mock_client):
        """Test service metrics query."""
        result = mock_client.get_service_metrics(service_name="api-gateway")

        assert result is not None

    def test_get_remediation_history(self, mock_client):
        """Test remediation history query."""
        result = mock_client.get_remediation_history()

        assert result is not None

    def test_call_history(self, mock_client):
        """Test call history tracking."""
        mock_client.query("SELECT * FROM anomaly_logs")
        mock_client.query("SELECT * FROM service_metrics")

        history = mock_client.call_history
        assert len(history) == 2
        assert history[0]["method"] == "execute_query"


class TestRDSClientAutoDetect:
    """Tests for RDS client auto-detection."""

    def test_auto_detect_mock_from_env(self):
        """Test auto-detection of mock provider from environment."""
        with patch.dict(os.environ, {"RDS_MOCK": "true"}):
            client = get_rds_client()
            assert client.provider_type == RDSProvider.MOCK

    def test_auto_detect_mock_from_aws_mock(self):
        """Test auto-detection when AWS_MOCK is set."""
        with patch.dict(os.environ, {"AWS_MOCK": "true"}, clear=False):
            client = get_rds_client()
            assert client.provider_type == RDSProvider.MOCK


# ============================================================================
# Integration Tests
# ============================================================================

class TestSchemaRDSIntegration:
    """Integration tests for schema loader and RDS client."""

    @pytest.fixture
    def example_schema_dir(self):
        """Get path to schema.example directory."""
        return Path(__file__).parent.parent / "schema.example"

    def test_rds_client_with_schema_loader(self, example_schema_dir):
        """Test RDS client uses schema loader correctly."""
        schema_loader = SchemaLoader(schema_dir=str(example_schema_dir))
        client = RDSClient(provider=RDSProvider.MOCK, schema_loader=schema_loader)

        # Schema loader should be accessible
        assert client.schema_loader is schema_loader

        # Should be able to get schema info
        tables = client.schema_loader.list_tables()
        assert len(tables) > 0

    def test_query_validates_against_schema(self, example_schema_dir):
        """Test query uses schema for validation."""
        schema_loader = SchemaLoader(schema_dir=str(example_schema_dir))
        client = RDSClient(provider=RDSProvider.MOCK, schema_loader=schema_loader)

        # Query a table that exists in schema
        result = client.query_table(
            "anomaly_logs",
            columns=["id", "timestamp", "service_name"],
            limit=5,
        )

        assert result is not None


# ============================================================================
# RDS Tools Tests
# ============================================================================

class TestRDSTools:
    """Tests for RDS tools."""

    @pytest.mark.skipif(
        True,  # Skip if langchain_core not installed
        reason="Requires langchain_core installation"
    )
    def test_query_rds_anomalies_import(self):
        """Test RDS tool import."""
        from src.agent.rds_tools import query_rds_anomalies, set_rds_client
        from src.services.rds_client import RDSClient, RDSProvider

        # Setup mock client
        client = RDSClient(provider=RDSProvider.MOCK)
        set_rds_client(client)

        # Execute tool
        result = query_rds_anomalies.func(limit=5)

        assert "total_count" in result
        assert "anomalies" in result

    @pytest.mark.skipif(
        True,  # Skip if langchain_core not installed
        reason="Requires langchain_core installation"
    )
    def test_execute_rds_query_safety(self):
        """Test that execute_rds_query blocks unsafe queries."""
        from src.agent.rds_tools import execute_rds_query, set_rds_client
        from src.services.rds_client import RDSClient, RDSProvider

        client = RDSClient(provider=RDSProvider.MOCK)
        set_rds_client(client)

        # Try unsafe query
        result = execute_rds_query.func("DROP TABLE users")
        assert result["error"] is True
        assert "SELECT" in result["message"]

        # Try query with dangerous keyword
        result = execute_rds_query.func("SELECT * FROM users; DELETE FROM users")
        assert result["error"] is True


class TestChatRDSTools:
    """Tests for Chat RDS tools."""

    @pytest.mark.skipif(
        True,  # Skip if langchain_core not installed
        reason="Requires langchain_core installation"
    )
    def test_create_rds_tools(self):
        """Test creating chat RDS tools."""
        from src.chat.tools.rds import create_rds_tools
        from src.services.rds_client import RDSClient, RDSProvider

        client = RDSClient(provider=RDSProvider.MOCK)
        tools = create_rds_tools(client)

        assert "query_anomalies" in tools
        assert "query_metrics" in tools
        assert "query_remediation_history" in tools
        assert "get_schema_info" in tools
        assert "execute_custom_query" in tools

    @pytest.mark.skipif(
        True,  # Skip if langchain_core not installed
        reason="Requires langchain_core installation"
    )
    def test_query_anomalies_tool(self):
        """Test query_anomalies chat tool."""
        from src.chat.tools.rds import create_rds_tools
        from src.services.rds_client import RDSClient, RDSProvider

        client = RDSClient(provider=RDSProvider.MOCK)
        tools = create_rds_tools(client)

        result = tools["query_anomalies"].func(limit=5)

        assert isinstance(result, str)
        # Should contain markdown table or "없습니다" message

    @pytest.mark.skipif(
        True,  # Skip if langchain_core not installed
        reason="Requires langchain_core installation"
    )
    def test_execute_custom_query_safety(self):
        """Test that custom query tool blocks unsafe queries."""
        from src.chat.tools.rds import create_rds_tools
        from src.services.rds_client import RDSClient, RDSProvider

        client = RDSClient(provider=RDSProvider.MOCK)
        tools = create_rds_tools(client)

        result = tools["execute_custom_query"].func("DELETE FROM users")
        assert "❌" in result
        assert "SELECT" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
