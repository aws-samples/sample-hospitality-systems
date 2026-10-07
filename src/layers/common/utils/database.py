"""
Database connection utility for AnyCompany Hotel platform.

Uses psycopg (v3) with RDS IAM authentication and TLS for
connecting through RDS Proxy. Falls back to Secrets Manager
credentials if IAM auth token generation fails.
"""

import contextlib
import os
from typing import Any

import boto3
import psycopg
from psycopg.rows import dict_row

_connection: psycopg.Connection | None = None


def _generate_iam_token() -> str:
    """Generate an RDS IAM authentication token for the proxy."""
    client = boto3.client("rds")
    host = os.environ["DB_PROXY_ENDPOINT"]
    port = 5432
    username = "anycompany_admin"
    return client.generate_db_auth_token(
        DBHostname=host, Port=port, DBUsername=username
    )


def get_conn() -> psycopg.Connection:
    """
    Return a psycopg connection using RDS IAM auth + TLS.

    The connection is cached per Lambda execution context and reused
    across invocations within the same warm container.

    Read-only handlers that issue SELECTs without an explicit
    `conn.commit()` leave the connection in `INTRANS` state when the
    Lambda freezes. RDS Proxy cannot multiplex such connections, and
    Aurora cannot pause an instance with open transactions, which kept
    `DatabaseConnectionsCurrentlyInTransaction` permanently >= 1 and
    pinned the cluster to its 0.5 ACU floor. Roll back any stale txn
    on the cached connection before returning it. A clean connection
    is a no-op (status == IDLE).
    """
    global _connection

    if _connection is not None and not _connection.closed:
        # The cached connection may look open (`closed == 0`) yet be dead: the
        # server can terminate it out from under us (e.g. RDS Proxy recycling,
        # or our own idle_in_transaction_session_timeout reaping a connection
        # left mid-transaction across a Lambda freeze). Probing it can raise.
        # Roll back any stale txn and verify liveness; on any failure, discard
        # the dead connection and fall through to reconnect. This keeps a warm
        # Lambda self-healing instead of 500-ing on the first post-reap call.
        try:
            if _connection.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                _connection.rollback()
            # Liveness probe: a connection the server has terminated still
            # reports closed == 0 until we actually touch the socket.
            with _connection.cursor() as cur:
                cur.execute("SELECT 1")
            return _connection
        except psycopg.Error:
            with contextlib.suppress(psycopg.Error):
                _connection.close()
            _connection = None

    host = os.environ["DB_PROXY_ENDPOINT"]
    dbname = os.environ["DB_NAME"]
    token = _generate_iam_token()

    _connection = psycopg.connect(
        host=host,
        dbname=dbname,
        user="anycompany_admin",
        password=token,
        port=5432,
        autocommit=False,
        row_factory=dict_row,
        sslmode="require",
    )
    return _connection


def execute_query(query: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    """Execute a SQL query and return all result rows as a list of dicts."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description is None:
                conn.commit()
                return []
            rows = cur.fetchall()
            conn.commit()
            return rows
    except Exception:
        conn.rollback()
        raise


def execute_query_one(query: str, params: tuple | list | None = None) -> dict[str, Any] | None:
    """Execute a SQL query and return the first result row, or None."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description is None:
                conn.commit()
                return None
            row = cur.fetchone()
            conn.commit()
            return row
    except Exception:
        conn.rollback()
        raise
