"""
HITL Store for RDS-based Request Management.

Provides CRUD operations for HITL requests using MySQL/RDS.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

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


# SQL Schema for HITL table
HITL_TABLE_SCHEMA = """
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


class HITLStore:
    """RDS-based store for HITL requests."""

    def __init__(
        self,
        rds_host: Optional[str] = None,
        rds_port: int = 3306,
        rds_database: Optional[str] = None,
        rds_user: Optional[str] = None,
        rds_password: Optional[str] = None,
        use_mock: bool = False,
    ):
        """Initialize the HITL store.

        Args:
            rds_host: RDS hostname
            rds_port: RDS port (default: 3306)
            rds_database: Database name
            rds_user: Database username
            rds_password: Database password
            use_mock: Use in-memory mock store instead of RDS
        """
        self.rds_host = rds_host or os.getenv("RDS_HOST")
        self.rds_port = rds_port or int(os.getenv("RDS_PORT", "3306"))
        self.rds_database = rds_database or os.getenv("RDS_DATABASE", "cd1_agent")
        self.rds_user = rds_user or os.getenv("RDS_USER")
        self.rds_password = rds_password or os.getenv("RDS_PASSWORD")
        self.use_mock = use_mock or os.getenv("RDS_PROVIDER", "").lower() == "mock"

        self._connection = None

        # Mock store for testing
        self._mock_store: dict[str, HITLRequest] = {}

    def _get_connection(self):
        """Get or create database connection."""
        if self.use_mock:
            return None

        if not PYMYSQL_AVAILABLE:
            raise ImportError(
                "pymysql is required for RDS connection. Install with: pip install pymysql"
            )

        if self._connection is None or not self._connection.open:
            self._connection = pymysql.connect(
                host=self.rds_host,
                port=self.rds_port,
                database=self.rds_database,
                user=self.rds_user,
                password=self.rds_password,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
                read_timeout=30,
            )
        return self._connection

    def ensure_table(self) -> None:
        """Ensure the HITL table exists."""
        if self.use_mock:
            return

        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(HITL_TABLE_SCHEMA)
            connection.commit()
            logger.info("HITL table ensured")
        except Exception as e:
            logger.error(f"Failed to ensure HITL table: {e}")
            raise

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

        if self.use_mock:
            self._mock_store[request_id] = hitl_request
            return hitl_request

        connection = self._get_connection()
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
            logger.info(f"Created HITL request: {request_id}")
            return hitl_request
        except Exception as e:
            connection.rollback()
            logger.error(f"Failed to create HITL request: {e}")
            raise

    def get(self, request_id: str) -> Optional[HITLRequest]:
        """Get a HITL request by ID.

        Args:
            request_id: Request ID

        Returns:
            HITL request or None if not found
        """
        if self.use_mock:
            return self._mock_store.get(request_id)

        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM hitl_requests WHERE id = %s"
                cursor.execute(sql, (request_id,))
                row = cursor.fetchone()
                if row:
                    return self._row_to_request(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get HITL request: {e}")
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

        if self.use_mock:
            return self._mock_list_requests(filter)

        connection = self._get_connection()
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
            logger.error(f"Failed to list HITL requests: {e}")
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

        if self.use_mock:
            if request_id not in self._mock_store:
                return None
            request = self._mock_store[request_id]
            request.status = status
            request.response = response.response
            request.responded_by = response.responded_by
            request.updated_at = datetime.utcnow()
            return request

        connection = self._get_connection()
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
            logger.error(f"Failed to respond to HITL request: {e}")
            raise

    def cancel(self, request_id: str) -> Optional[HITLRequest]:
        """Cancel a pending HITL request.

        Args:
            request_id: Request ID

        Returns:
            Updated HITL request or None if not found
        """
        if self.use_mock:
            if request_id not in self._mock_store:
                return None
            request = self._mock_store[request_id]
            if request.status != HITLRequestStatus.PENDING:
                return None
            request.status = HITLRequestStatus.CANCELLED
            request.updated_at = datetime.utcnow()
            return request

        connection = self._get_connection()
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
            logger.error(f"Failed to cancel HITL request: {e}")
            raise

    def expire_stale_requests(self) -> int:
        """Mark expired requests as expired.

        Returns:
            Number of requests marked as expired
        """
        if self.use_mock:
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

        connection = self._get_connection()
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
                logger.info(f"Expired {count} stale HITL requests")
            return count
        except Exception as e:
            connection.rollback()
            logger.error(f"Failed to expire stale requests: {e}")
            raise

    def get_pending_count(self, agent_type: Optional[HITLAgentType] = None) -> int:
        """Get count of pending requests.

        Args:
            agent_type: Optional filter by agent type

        Returns:
            Number of pending requests
        """
        if self.use_mock:
            return sum(
                1
                for r in self._mock_store.values()
                if r.status == HITLRequestStatus.PENDING
                and (agent_type is None or r.agent_type == agent_type)
            )

        connection = self._get_connection()
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
            logger.error(f"Failed to get pending count: {e}")
            raise

    def _row_to_request(self, row: dict) -> HITLRequest:
        """Convert database row to HITLRequest model."""
        payload = row.get("payload", "{}")
        if isinstance(payload, str):
            payload = json.loads(payload)

        response = row.get("response")
        if isinstance(response, str):
            response = json.loads(response)

        return HITLRequest(
            id=row["id"],
            agent_type=HITLAgentType(row["agent_type"]),
            request_type=row["request_type"],
            status=HITLRequestStatus(row["status"]),
            title=row["title"],
            description=row.get("description"),
            payload=payload,
            response=response,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
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
        if self._connection and self._connection.open:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
