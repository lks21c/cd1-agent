"""
Schema Loader for Dynamic RDS Query Generation.

Loads table schemas from JSON files at runtime to support:
- Public (외부): Mock schemas for fast development/testing
- Private (내부): Real production schemas

The schema/ directory is gitignored for security.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ColumnSchema:
    """Column schema definition."""

    name: str
    type: str
    description: str = ""
    nullable: bool = True
    primary_key: bool = False
    auto_increment: bool = False
    default: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ColumnSchema":
        """Create ColumnSchema from dictionary."""
        return cls(
            name=data["name"],
            type=data["type"],
            description=data.get("description", ""),
            nullable=data.get("nullable", True),
            primary_key=data.get("primary_key", False),
            auto_increment=data.get("auto_increment", False),
            default=data.get("default"),
        )


@dataclass
class IndexSchema:
    """Index schema definition."""

    name: str
    columns: List[str]
    type: str = "btree"
    unique: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndexSchema":
        """Create IndexSchema from dictionary."""
        return cls(
            name=data["name"],
            columns=data["columns"],
            type=data.get("type", "btree"),
            unique=data.get("unique", False),
        )


@dataclass
class ForeignKeySchema:
    """Foreign key schema definition."""

    name: str
    columns: List[str]
    ref_table: str
    ref_columns: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ForeignKeySchema":
        """Create ForeignKeySchema from dictionary."""
        references = data.get("references", {})
        return cls(
            name=data["name"],
            columns=data["columns"],
            ref_table=references.get("table", ""),
            ref_columns=references.get("columns", []),
        )


@dataclass
class TableSchema:
    """Table schema definition."""

    table_name: str
    columns: List[ColumnSchema]
    description: str = ""
    database: Optional[str] = None
    indexes: List[IndexSchema] = field(default_factory=list)
    foreign_keys: List[ForeignKeySchema] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TableSchema":
        """Create TableSchema from dictionary."""
        columns = [ColumnSchema.from_dict(c) for c in data.get("columns", [])]
        indexes = [IndexSchema.from_dict(i) for i in data.get("indexes", [])]
        foreign_keys = [ForeignKeySchema.from_dict(f) for f in data.get("foreign_keys", [])]

        return cls(
            table_name=data["table_name"],
            columns=columns,
            description=data.get("description", ""),
            database=data.get("database"),
            indexes=indexes,
            foreign_keys=foreign_keys,
        )

    def get_column(self, name: str) -> Optional[ColumnSchema]:
        """Get column by name."""
        for col in self.columns:
            if col.name == name:
                return col
        return None

    def get_column_names(self) -> List[str]:
        """Get list of column names."""
        return [col.name for col in self.columns]

    def get_primary_key_columns(self) -> List[ColumnSchema]:
        """Get primary key columns."""
        return [col for col in self.columns if col.primary_key]

    def to_prompt_context(self) -> str:
        """Generate LLM-friendly schema description for prompt context."""
        lines = [
            f"테이블: {self.table_name}",
            f"설명: {self.description}",
            "컬럼:",
        ]

        for col in self.columns:
            pk_marker = " [PK]" if col.primary_key else ""
            nullable = "" if col.nullable else " NOT NULL"
            lines.append(f"  - {col.name} ({col.type}){pk_marker}{nullable}: {col.description}")

        return "\n".join(lines)


class SchemaLoader:
    """
    Schema loader for dynamic RDS query generation.

    Loads table schemas from JSON files in the schema directory.
    Supports caching for performance.

    Usage:
        loader = SchemaLoader()

        # Load single table
        schema = loader.load_table("anomaly_logs")

        # Load all tables
        schemas = loader.load_all_tables()

        # Get LLM context
        context = loader.get_llm_context(["anomaly_logs", "service_metrics"])
    """

    def __init__(
        self,
        schema_dir: Optional[str] = None,
        cache_enabled: bool = True,
    ):
        """
        Initialize SchemaLoader.

        Args:
            schema_dir: Path to schema directory. Defaults to 'schema/' in project root.
            cache_enabled: Enable schema caching (default: True)
        """
        if schema_dir:
            self.schema_dir = Path(schema_dir)
        else:
            # Default: schema/ in project root
            self.schema_dir = Path(
                os.environ.get(
                    "SCHEMA_DIR",
                    Path(__file__).parent.parent.parent / "schema"
                )
            )

        self.tables_dir = self.schema_dir / "tables"
        self.views_dir = self.schema_dir / "views"
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, TableSchema] = {}

        logger.info(f"SchemaLoader initialized with schema_dir={self.schema_dir}")

    def _load_json_file(self, file_path: Path) -> Dict[str, Any]:
        """Load and parse JSON file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Schema file not found: {file_path}")
            raise SchemaNotFoundError(f"Schema file not found: {file_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in schema file {file_path}: {e}")
            raise SchemaParseError(f"Invalid JSON in schema file {file_path}: {e}")

    def load_table(self, table_name: str) -> TableSchema:
        """
        Load table schema by name.

        Args:
            table_name: Table name (without .json extension)

        Returns:
            TableSchema object

        Raises:
            SchemaNotFoundError: If schema file doesn't exist
            SchemaParseError: If schema file is invalid
        """
        # Check cache
        if self.cache_enabled and table_name in self._cache:
            logger.debug(f"Loading schema from cache: {table_name}")
            return self._cache[table_name]

        # Load from file
        file_path = self.tables_dir / f"{table_name}.json"
        data = self._load_json_file(file_path)

        schema = TableSchema.from_dict(data)

        # Cache if enabled
        if self.cache_enabled:
            self._cache[table_name] = schema

        logger.info(f"Loaded schema for table: {table_name}")
        return schema

    def load_all_tables(self) -> Dict[str, TableSchema]:
        """
        Load all table schemas.

        Returns:
            Dictionary of table_name -> TableSchema
        """
        schemas: Dict[str, TableSchema] = {}

        if not self.tables_dir.exists():
            logger.warning(f"Tables directory not found: {self.tables_dir}")
            return schemas

        for file_path in self.tables_dir.glob("*.json"):
            table_name = file_path.stem
            try:
                schemas[table_name] = self.load_table(table_name)
            except (SchemaNotFoundError, SchemaParseError) as e:
                logger.error(f"Failed to load schema {table_name}: {e}")
                continue

        return schemas

    def list_tables(self) -> List[str]:
        """
        List available table names.

        Returns:
            List of table names
        """
        if not self.tables_dir.exists():
            return []

        return [f.stem for f in self.tables_dir.glob("*.json")]

    def get_llm_context(
        self,
        table_names: Optional[List[str]] = None,
        max_tables: int = 10,
    ) -> str:
        """
        Generate LLM context string for query generation.

        Args:
            table_names: List of specific tables (or None for all)
            max_tables: Maximum number of tables to include

        Returns:
            Formatted context string for LLM prompt
        """
        if table_names:
            schemas = {name: self.load_table(name) for name in table_names[:max_tables]}
        else:
            schemas = self.load_all_tables()
            # Limit to max_tables
            schemas = dict(list(schemas.items())[:max_tables])

        if not schemas:
            return "스키마 정보가 없습니다."

        context_parts = [
            "=== 데이터베이스 스키마 정보 ===",
            f"사용 가능한 테이블: {len(schemas)}개\n",
        ]

        for name, schema in schemas.items():
            context_parts.append(schema.to_prompt_context())
            context_parts.append("")  # Empty line between tables

        return "\n".join(context_parts)

    def clear_cache(self) -> None:
        """Clear schema cache."""
        self._cache.clear()
        logger.info("Schema cache cleared")

    def validate_table(self, table_name: str) -> bool:
        """
        Check if table schema exists and is valid.

        Args:
            table_name: Table name to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            self.load_table(table_name)
            return True
        except (SchemaNotFoundError, SchemaParseError):
            return False

    def get_table_columns(self, table_name: str) -> List[str]:
        """
        Get column names for a table.

        Args:
            table_name: Table name

        Returns:
            List of column names
        """
        schema = self.load_table(table_name)
        return schema.get_column_names()


class SchemaNotFoundError(Exception):
    """Raised when a schema file is not found."""
    pass


class SchemaParseError(Exception):
    """Raised when a schema file cannot be parsed."""
    pass


# Module-level singleton
_default_loader: Optional[SchemaLoader] = None


def get_schema_loader(
    schema_dir: Optional[str] = None,
    cache_enabled: bool = True,
) -> SchemaLoader:
    """
    Get or create SchemaLoader singleton.

    Args:
        schema_dir: Optional schema directory path
        cache_enabled: Enable caching

    Returns:
        SchemaLoader instance
    """
    global _default_loader

    if schema_dir or _default_loader is None:
        _default_loader = SchemaLoader(
            schema_dir=schema_dir,
            cache_enabled=cache_enabled,
        )

    return _default_loader


if __name__ == "__main__":
    # Test with example schemas
    import sys

    # Use schema.example for testing
    example_dir = Path(__file__).parent.parent.parent / "schema.example"

    if not example_dir.exists():
        print(f"Example schema directory not found: {example_dir}")
        sys.exit(1)

    loader = SchemaLoader(schema_dir=str(example_dir))

    print("=== Available Tables ===")
    tables = loader.list_tables()
    print(f"Tables: {tables}")

    print("\n=== Loading anomaly_logs ===")
    try:
        schema = loader.load_table("anomaly_logs")
        print(f"Table: {schema.table_name}")
        print(f"Description: {schema.description}")
        print(f"Columns: {schema.get_column_names()}")
        print(f"Primary Keys: {[c.name for c in schema.get_primary_key_columns()]}")
    except SchemaNotFoundError as e:
        print(f"Error: {e}")

    print("\n=== LLM Context ===")
    context = loader.get_llm_context()
    print(context[:1000] + "..." if len(context) > 1000 else context)
