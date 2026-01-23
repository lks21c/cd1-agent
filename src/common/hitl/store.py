"""
HITL Store for RDS-based Request Management.

Provides CRUD operations for HITL requests using MySQL/RDS, SQLite, or mock storage.
Supports dual DB deployment: MySQL for internal networks, SQLite for public networks.
"""

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Literal, Optional, Union

from src.common.hitl.schemas import (
    HITLAgentType,
    HITLRequest,
    HITLRequestCreate,
    HITLRequestFilter,
    HITLRequestResponse,
    HITLRequestStatus,
)

try:
    import pymysql

    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False


logger = logging.getLogger(__name__)


# Provider type definition
ProviderType = Literal["mock", "sqlite", "mysql"]


# SQL Schema for MySQL HITL table
MYSQL_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS hitl_requests (
    id VARCHAR(36) PRIMARY KEY,
    agent_type ENUM('cost', 'bdp', 'hdsp', 'drift') NOT NULL,
    request_type VARCHAR(50) NOT NULL,
    status ENUM('pending', 'approved', 'rejected', 'expired', 'cancelled') DEFAULT 'pending',
    title VARCHAR(255) NOT NULL,
    description TEXT,
    payload JSON NOT NULL,
    response JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    created_by VARCHAR(100),
    responded_by VARCHAR(100),
    INDEX idx_status (status),
    INDEX idx_agent_status (agent_type, status),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# SQL Schema for SQLite HITL table
SQLITE_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS hitl_requests (
    id TEXT PRIMARY KEY CHECK(length(id) = 36),
    agent_type TEXT NOT NULL CHECK(agent_type IN ('cost', 'bdp', 'hdsp', 'drift')),
    request_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled')),
    title TEXT NOT NULL,
    description TEXT,
    payload TEXT NOT NULL,
    response TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    expires_at TEXT NOT NULL,
    created_by TEXT,
    responded_by TEXT
);
"""

SQLITE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_requests(status);
CREATE INDEX IF NOT EXISTS idx_hitl_agent_status ON hitl_requests(agent_type, status);
CREATE INDEX IF NOT EXISTS idx_hitl_expires ON hitl_requests(expires_at);
"""

SQLITE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS hitl_requests_updated_at
AFTER UPDATE ON hitl_requests
FOR EACH ROW
BEGIN
    UPDATE hitl_requests
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE id = NEW.id;
END;
"""


class HITLStore:
    """Multi-provider store for HITL requests.

    Supports three providers:
    - mock: In-memory dict for testing
    - sqlite: SQLite3 for public network deployments
    - mysql: MySQL/RDS for internal network deployments
    """

    def __init__(
        self,
        provider: Optional[ProviderType] = None,
        # MySQL-specific options
        rds_host: Optional[str] = None,
        rds_port: int = 3306,
        rds_database: Optional[str] = None,
        rds_user: Optional[str] = None,
        rds_password: Optional[str] = None,
        # SQLite-specific options
        sqlite_path: Optional[str] = None,
        # Legacy option (deprecated, use provider instead)
        use_mock: bool = False,
    ):
        """Initialize the HITL store.

        Args:
            provider: Database provider ("mock", "sqlite", "mysql")
            rds_host: RDS hostname (MySQL)
            rds_port: RDS port (default: 3306)
            rds_database: Database name (MySQL)
            rds_user: Database username (MySQL)
            rds_password: Database password (MySQL)
            sqlite_path: Path to SQLite database file
            use_mock: Legacy option - use provider="mock" instead
        """
        # Determine provider from arguments or environment
        self.provider = self._resolve_provider(provider, use_mock)

        # MySQL configuration
        self.rds_host = rds_host or os.getenv("RDS_HOST")
        self.rds_port = rds_port or int(os.getenv("RDS_PORT", "3306"))
        self.rds_database = rds_database or os.getenv("RDS_DATABASE", "cd1_agent")
        self.rds_user = rds_user or os.getenv("RDS_USER")
        self.rds_password = rds_password or os.getenv("RDS_PASSWORD")

        # SQLite configuration
        self.sqlite_path = sqlite_path or os.getenv("SQLITE_PATH", "./data/hitl.db")

        # Connection state
        self._mysql_connection = None
        self._sqlite_connection: Optional[sqlite3.Connection] = None

        # Mock store for testing
        self._mock_store: dict[str, HITLRequest] = {}

        logger.info(f"HITLStore initialized with provider: {self.provider}")

    def _resolve_provider(
        self, provider: Optional[ProviderType], use_mock: bool
    ) -> ProviderType:
        """Resolve the provider from arguments and environment.

        Priority: explicit provider > use_mock flag > RDS_PROVIDER env > default
        """
        if provider:
            return provider

        if use_mock:
            return "mock"

        env_provider = os.getenv("RDS_PROVIDER", "").lower()
        if env_provider in ("mock", "sqlite", "mysql"):
            return env_provider  # type: ignore

        # Default to mock if no provider specified
        return "mock"

    @property
    def use_mock(self) -> bool:
        """Legacy property for backward compatibility."""
        return self.provider == "mock"

    def _get_mysql_connection(self):
        """Get or create MySQL database connection."""
        if not PYMYSQL_AVAILABLE:
            raise ImportError(
                "pymysql is required for MySQL connection. Install with: pip install pymysql"
            )

        if self._mysql_connection is None or not self._mysql_connection.open:
            self._mysql_connection = pymysql.connect(
                host=self.rds_host,
                port=self.rds_port,
                database=self.rds_database,
                user=self.rds_user,
                password=self.rds_password,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
                read_timeout=30,
            )
        return self._mysql_connection

    def _get_sqlite_connection(self) -> sqlite3.Connection:
        """Get or create SQLite database connection."""
        if self._sqlite_connection is None:
            # Ensure directory exists
            db_path = Path(self.sqlite_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

            self._sqlite_connection = sqlite3.connect(
                str(db_path),
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                check_same_thread=False,
            )
            # Enable dict-like row access
            self._sqlite_connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._sqlite_connection.execute("PRAGMA foreign_keys = ON")

        return self._sqlite_connection

    def _get_connection(self) -> Union[None, sqlite3.Connection, "pymysql.Connection"]:
        """Get database connection based on provider."""
        if self.provider == "mock":
            return None
        elif self.provider == "sqlite":
            return self._get_sqlite_connection()
        elif self.provider == "mysql":
            return self._get_mysql_connection()
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def ensure_table(self) -> None:
        """Ensure the HITL table exists."""
        if self.provider == "mock":
            return

        if self.provider == "sqlite":
            connection = self._get_sqlite_connection()
            try:
                cursor = connection.cursor()
                cursor.execute(SQLITE_TABLE_SCHEMA)
                # Create indexes separately (SQLite doesn't support multiple statements)
                for index_sql in SQLITE_INDEXES.strip().split(";"):
                    if index_sql.strip():
                        cursor.execute(index_sql)
                # Create trigger
                cursor.execute(SQLITE_TRIGGER)
                connection.commit()
                logger.info("HITL SQLite table ensured")
            except Exception as e:
                logger.error(f"Failed to ensure HITL SQLite table: {e}")
                raise
        elif self.provider == "mysql":
            connection = self._get_mysql_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(MYSQL_TABLE_SCHEMA)
                connection.commit()
                logger.info("HITL MySQL table ensured")
            except Exception as e:
                logger.error(f"Failed to ensure HITL MySQL table: {e}")
                raise

    def _datetime_to_iso(self, dt: datetime) -> str:
        """Convert datetime to ISO8601 string for SQLite."""
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _iso_to_datetime(self, iso_str: str) -> datetime:
        """Convert ISO8601 string to datetime."""
        if iso_str is None:
            return None
        # Handle various ISO8601 formats
        for fmt in [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ]:
            try:
                return datetime.strptime(iso_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Unable to parse datetime: {iso_str}")

    def create(self, request: HITLRequestCreate) -> HITLRequest:
        """Create a new HITL request.

        Args:
            request: HITL request creation data

        Returns:
            Created HITL request
        """
        request_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=request.expires_in_minutes)

        hitl_request = HITLRequest(
            id=request_id,
            agent_type=request.agent_type,
            request_type=request.request_type,
            status=HITLRequestStatus.PENDING,
            title=request.title,
            description=request.description,
            payload=request.payload,
            response=None,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            created_by=request.created_by,
            responded_by=None,
        )

        if self.provider == "mock":
            self._mock_store[request_id] = hitl_request
            return hitl_request

        if self.provider == "sqlite":
            connection = self._get_sqlite_connection()
            try:
                cursor = connection.cursor()
                sql = """
                    INSERT INTO hitl_requests
                    (id, agent_type, request_type, status, title, description, payload,
                     created_at, updated_at, expires_at, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                cursor.execute(
                    sql,
                    (
                        request_id,
                        request.agent_type.value,
                        request.request_type.value,
                        HITLRequestStatus.PENDING.value,
                        request.title,
                        request.description,
                        json.dumps(request.payload),
                        self._datetime_to_iso(now),
                        self._datetime_to_iso(now),
                        self._datetime_to_iso(expires_at),
                        request.created_by,
                    ),
                )
                connection.commit()
                logger.info(f"Created HITL request (SQLite): {request_id}")
                return hitl_request
            except Exception as e:
                connection.rollback()
                logger.error(f"Failed to create HITL request (SQLite): {e}")
                raise

        # MySQL provider
        connection = self._get_mysql_connection()
        try:
            with connection.cursor() as cursor:
                sql = """
                    INSERT INTO hitl_requests
                    (id, agent_type, request_type, status, title, description, payload,
                     created_at, updated_at, expires_at, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(
                    sql,
                    (
                        request_id,
                        request.agent_type.value,
                        request.request_type.value,
                        HITLRequestStatus.PENDING.value,
                        request.title,
                        request.description,
                        json.dumps(request.payload),
                        now,
                        now,
                        expires_at,
                        request.created_by,
                    ),
                )
            connection.commit()
            logger.info(f"Created HITL request (MySQL): {request_id}")
            return hitl_request
        except Exception as e:
            connection.rollback()
            logger.error(f"Failed to create HITL request (MySQL): {e}")
            raise

    def get(self, request_id: str) -> Optional[HITLRequest]:
        """Get a HITL request by ID.

        Args:
            request_id: Request ID

        Returns:
            HITL request or None if not found
        """
        if self.provider == "mock":
            return self._mock_store.get(request_id)

        if self.provider == "sqlite":
            connection = self._get_sqlite_connection()
            try:
                cursor = connection.cursor()
                sql = "SELECT * FROM hitl_requests WHERE id = ?"
                cursor.execute(sql, (request_id,))
                row = cursor.fetchone()
                if row:
                    return self._row_to_request(dict(row))
                return None
            except Exception as e:
                logger.error(f"Failed to get HITL request (SQLite): {e}")
                raise

        # MySQL provider
        connection = self._get_mysql_connection()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM hitl_requests WHERE id = %s"
                cursor.execute(sql, (request_id,))
                row = cursor.fetchone()
                if row:
                    return self._row_to_request(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get HITL request (MySQL): {e}")
            raise

    def list_requests(
        self,
        filter: Optional[HITLRequestFilter] = None,
    ) -> List[HITLRequest]:
        """List HITL requests with optional filtering.

        Args:
            filter: Filter parameters

        Returns:
            List of HITL requests
        """
        filter = filter or HITLRequestFilter()

        if self.provider == "mock":
            return self._mock_list_requests(filter)

        if self.provider == "sqlite":
            return self._sqlite_list_requests(filter)

        # MySQL provider
        return self._mysql_list_requests(filter)

    def _sqlite_list_requests(self, filter: HITLRequestFilter) -> List[HITLRequest]:
        """SQLite implementation of list_requests."""
        connection = self._get_sqlite_connection()
        try:
            cursor = connection.cursor()
            sql = "SELECT * FROM hitl_requests WHERE 1=1"
            params: list = []

            if filter.agent_type:
                sql += " AND agent_type = ?"
                params.append(filter.agent_type.value)

            if filter.status:
                sql += " AND status = ?"
                params.append(filter.status.value)

            if filter.request_type:
                sql += " AND request_type = ?"
                params.append(filter.request_type.value)

            if filter.created_after:
                sql += " AND created_at >= ?"
                params.append(self._datetime_to_iso(filter.created_after))

            if filter.created_before:
                sql += " AND created_at <= ?"
                params.append(self._datetime_to_iso(filter.created_before))

            sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([filter.limit, filter.offset])

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [self._row_to_request(dict(row)) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list HITL requests (SQLite): {e}")
            raise

    def _mysql_list_requests(self, filter: HITLRequestFilter) -> List[HITLRequest]:
        """MySQL implementation of list_requests."""
        connection = self._get_mysql_connection()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM hitl_requests WHERE 1=1"
                params: list = []

                if filter.agent_type:
                    sql += " AND agent_type = %s"
                    params.append(filter.agent_type.value)

                if filter.status:
                    sql += " AND status = %s"
                    params.append(filter.status.value)

                if filter.request_type:
                    sql += " AND request_type = %s"
                    params.append(filter.request_type.value)

                if filter.created_after:
                    sql += " AND created_at >= %s"
                    params.append(filter.created_after)

                if filter.created_before:
                    sql += " AND created_at <= %s"
                    params.append(filter.created_before)

                sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.extend([filter.limit, filter.offset])

                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return [self._row_to_request(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list HITL requests (MySQL): {e}")
            raise

    def respond(
        self,
        request_id: str,
        response: HITLRequestResponse,
    ) -> Optional[HITLRequest]:
        """Respond to (approve/reject) a HITL request.

        Args:
            request_id: Request ID
            response: Response data

        Returns:
            Updated HITL request or None if not found
        """
        status = (
            HITLRequestStatus.APPROVED
            if response.approved
            else HITLRequestStatus.REJECTED
        )

        if self.provider == "mock":
            if request_id not in self._mock_store:
                return None
            request = self._mock_store[request_id]
            request.status = status
            request.response = response.response
            request.responded_by = response.responded_by
            request.updated_at = datetime.utcnow()
            return request

        if self.provider == "sqlite":
            connection = self._get_sqlite_connection()
            try:
                cursor = connection.cursor()
                sql = """
                    UPDATE hitl_requests
                    SET status = ?, response = ?, responded_by = ?, updated_at = ?
                    WHERE id = ? AND status = 'pending'
                """
                now = datetime.utcnow()
                cursor.execute(
                    sql,
                    (
                        status.value,
                        json.dumps(response.response) if response.response else None,
                        response.responded_by,
                        self._datetime_to_iso(now),
                        request_id,
                    ),
                )
                if cursor.rowcount == 0:
                    return None
                connection.commit()
                return self.get(request_id)
            except Exception as e:
                connection.rollback()
                logger.error(f"Failed to respond to HITL request (SQLite): {e}")
                raise

        # MySQL provider
        connection = self._get_mysql_connection()
        try:
            with connection.cursor() as cursor:
                sql = """
                    UPDATE hitl_requests
                    SET status = %s, response = %s, responded_by = %s, updated_at = %s
                    WHERE id = %s AND status = 'pending'
                """
                now = datetime.utcnow()
                cursor.execute(
                    sql,
                    (
                        status.value,
                        json.dumps(response.response) if response.response else None,
                        response.responded_by,
                        now,
                        request_id,
                    ),
                )
                if cursor.rowcount == 0:
                    return None
            connection.commit()
            return self.get(request_id)
        except Exception as e:
            connection.rollback()
            logger.error(f"Failed to respond to HITL request (MySQL): {e}")
            raise

    def cancel(self, request_id: str) -> Optional[HITLRequest]:
        """Cancel a pending HITL request.

        Args:
            request_id: Request ID

        Returns:
            Updated HITL request or None if not found
        """
        if self.provider == "mock":
            if request_id not in self._mock_store:
                return None
            request = self._mock_store[request_id]
            if request.status != HITLRequestStatus.PENDING:
                return None
            request.status = HITLRequestStatus.CANCELLED
            request.updated_at = datetime.utcnow()
            return request

        if self.provider == "sqlite":
            connection = self._get_sqlite_connection()
            try:
                cursor = connection.cursor()
                sql = """
                    UPDATE hitl_requests
                    SET status = 'cancelled', updated_at = ?
                    WHERE id = ? AND status = 'pending'
                """
                cursor.execute(sql, (self._datetime_to_iso(datetime.utcnow()), request_id))
                if cursor.rowcount == 0:
                    return None
                connection.commit()
                return self.get(request_id)
            except Exception as e:
                connection.rollback()
                logger.error(f"Failed to cancel HITL request (SQLite): {e}")
                raise

        # MySQL provider
        connection = self._get_mysql_connection()
        try:
            with connection.cursor() as cursor:
                sql = """
                    UPDATE hitl_requests
                    SET status = 'cancelled', updated_at = %s
                    WHERE id = %s AND status = 'pending'
                """
                cursor.execute(sql, (datetime.utcnow(), request_id))
                if cursor.rowcount == 0:
                    return None
            connection.commit()
            return self.get(request_id)
        except Exception as e:
            connection.rollback()
            logger.error(f"Failed to cancel HITL request (MySQL): {e}")
            raise

    def expire_stale_requests(self) -> int:
        """Mark expired requests as expired.

        Returns:
            Number of requests marked as expired
        """
        if self.provider == "mock":
            count = 0
            now = datetime.utcnow()
            for request in self._mock_store.values():
                if (
                    request.status == HITLRequestStatus.PENDING
                    and request.expires_at < now
                ):
                    request.status = HITLRequestStatus.EXPIRED
                    request.updated_at = now
                    count += 1
            return count

        if self.provider == "sqlite":
            connection = self._get_sqlite_connection()
            try:
                cursor = connection.cursor()
                sql = """
                    UPDATE hitl_requests
                    SET status = 'expired', updated_at = ?
                    WHERE status = 'pending' AND expires_at < ?
                """
                now = datetime.utcnow()
                now_iso = self._datetime_to_iso(now)
                cursor.execute(sql, (now_iso, now_iso))
                count = cursor.rowcount
                connection.commit()
                if count > 0:
                    logger.info(f"Expired {count} stale HITL requests (SQLite)")
                return count
            except Exception as e:
                connection.rollback()
                logger.error(f"Failed to expire stale requests (SQLite): {e}")
                raise

        # MySQL provider
        connection = self._get_mysql_connection()
        try:
            with connection.cursor() as cursor:
                sql = """
                    UPDATE hitl_requests
                    SET status = 'expired', updated_at = %s
                    WHERE status = 'pending' AND expires_at < %s
                """
                now = datetime.utcnow()
                cursor.execute(sql, (now, now))
                count = cursor.rowcount
            connection.commit()
            if count > 0:
                logger.info(f"Expired {count} stale HITL requests (MySQL)")
            return count
        except Exception as e:
            connection.rollback()
            logger.error(f"Failed to expire stale requests (MySQL): {e}")
            raise

    def get_pending_count(self, agent_type: Optional[HITLAgentType] = None) -> int:
        """Get count of pending requests.

        Args:
            agent_type: Optional filter by agent type

        Returns:
            Number of pending requests
        """
        if self.provider == "mock":
            return sum(
                1
                for r in self._mock_store.values()
                if r.status == HITLRequestStatus.PENDING
                and (agent_type is None or r.agent_type == agent_type)
            )

        if self.provider == "sqlite":
            connection = self._get_sqlite_connection()
            try:
                cursor = connection.cursor()
                if agent_type:
                    sql = """
                        SELECT COUNT(*) as count FROM hitl_requests
                        WHERE status = 'pending' AND agent_type = ?
                    """
                    cursor.execute(sql, (agent_type.value,))
                else:
                    sql = "SELECT COUNT(*) as count FROM hitl_requests WHERE status = 'pending'"
                    cursor.execute(sql)
                row = cursor.fetchone()
                return row[0] if row else 0
            except Exception as e:
                logger.error(f"Failed to get pending count (SQLite): {e}")
                raise

        # MySQL provider
        connection = self._get_mysql_connection()
        try:
            with connection.cursor() as cursor:
                if agent_type:
                    sql = """
                        SELECT COUNT(*) as count FROM hitl_requests
                        WHERE status = 'pending' AND agent_type = %s
                    """
                    cursor.execute(sql, (agent_type.value,))
                else:
                    sql = "SELECT COUNT(*) as count FROM hitl_requests WHERE status = 'pending'"
                    cursor.execute(sql)
                row = cursor.fetchone()
                return row["count"] if row else 0
        except Exception as e:
            logger.error(f"Failed to get pending count (MySQL): {e}")
            raise

    def _row_to_request(self, row: dict) -> HITLRequest:
        """Convert database row to HITLRequest model."""
        payload = row.get("payload", "{}")
        if isinstance(payload, str):
            payload = json.loads(payload)

        response = row.get("response")
        if isinstance(response, str):
            response = json.loads(response)

        # Handle datetime conversion for SQLite (stored as ISO8601 strings)
        created_at = row["created_at"]
        updated_at = row["updated_at"]
        expires_at = row["expires_at"]

        if isinstance(created_at, str):
            created_at = self._iso_to_datetime(created_at)
        if isinstance(updated_at, str):
            updated_at = self._iso_to_datetime(updated_at)
        if isinstance(expires_at, str):
            expires_at = self._iso_to_datetime(expires_at)

        return HITLRequest(
            id=row["id"],
            agent_type=HITLAgentType(row["agent_type"]),
            request_type=row["request_type"],
            status=HITLRequestStatus(row["status"]),
            title=row["title"],
            description=row.get("description"),
            payload=payload,
            response=response,
            created_at=created_at,
            updated_at=updated_at,
            expires_at=expires_at,
            created_by=row.get("created_by"),
            responded_by=row.get("responded_by"),
        )

    def _mock_list_requests(self, filter: HITLRequestFilter) -> List[HITLRequest]:
        """Mock implementation of list_requests."""
        requests = list(self._mock_store.values())

        if filter.agent_type:
            requests = [r for r in requests if r.agent_type == filter.agent_type]

        if filter.status:
            requests = [r for r in requests if r.status == filter.status]

        if filter.request_type:
            requests = [r for r in requests if r.request_type == filter.request_type]

        if filter.created_after:
            requests = [r for r in requests if r.created_at >= filter.created_after]

        if filter.created_before:
            requests = [r for r in requests if r.created_at <= filter.created_before]

        # Sort by created_at descending
        requests.sort(key=lambda r: r.created_at, reverse=True)

        # Apply pagination
        return requests[filter.offset : filter.offset + filter.limit]

    def close(self):
        """Close database connection."""
        if self._mysql_connection and self._mysql_connection.open:
            self._mysql_connection.close()
            self._mysql_connection = None

        if self._sqlite_connection:
            self._sqlite_connection.close()
            self._sqlite_connection = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
