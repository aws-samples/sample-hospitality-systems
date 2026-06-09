"""Unit tests for utils.database.

psycopg and boto3 are mocked — no real connection is made. Covers the
cached-connection reuse, the leaked-transaction rollback guard (the fix
for the Aurora-pinned-to-ACU-floor incident), and the execute_query
commit/rollback behavior.
"""

from unittest.mock import MagicMock

import pytest

import utils.database as database


@pytest.fixture(autouse=True)
def reset_cached_connection():
    """Each test starts with no cached connection."""
    database._connection = None
    yield
    database._connection = None


@pytest.fixture
def mock_psycopg(monkeypatch):
    """Patch psycopg.connect and the IAM token generator."""
    monkeypatch.setattr(database, "_generate_iam_token", lambda: "fake-token")

    created = []

    def _connect(**kwargs):
        conn = MagicMock()
        conn.closed = False
        conn.info.transaction_status = database.psycopg.pq.TransactionStatus.IDLE
        conn._connect_kwargs = kwargs
        created.append(conn)
        return conn

    monkeypatch.setattr(database.psycopg, "connect", _connect)
    return created


class TestGetConn:
    def test_creates_connection_first_call(self, mock_psycopg):
        conn = database.get_conn()
        assert conn is not None
        assert len(mock_psycopg) == 1

    def test_connect_uses_iam_auth_params(self, mock_psycopg):
        database.get_conn()
        kwargs = mock_psycopg[0]._connect_kwargs
        assert kwargs["user"] == "anycompany_admin"
        assert kwargs["password"] == "fake-token"
        assert kwargs["sslmode"] == "require"
        assert kwargs["autocommit"] is False

    def test_reuses_cached_connection(self, mock_psycopg):
        c1 = database.get_conn()
        c2 = database.get_conn()
        assert c1 is c2
        assert len(mock_psycopg) == 1  # only created once

    def test_recreates_when_closed(self, mock_psycopg):
        c1 = database.get_conn()
        c1.closed = True
        c2 = database.get_conn()
        assert c1 is not c2
        assert len(mock_psycopg) == 2

    def test_rolls_back_stale_in_transaction_connection(self, mock_psycopg):
        """The leaked-transaction guard: a cached conn left in INTRANS gets
        rolled back before reuse."""
        conn = database.get_conn()
        conn.info.transaction_status = database.psycopg.pq.TransactionStatus.INTRANS
        reused = database.get_conn()
        assert reused is conn
        conn.rollback.assert_called_once()

    def test_recovers_when_cached_conn_dead_on_rollback(self, mock_psycopg):
        """A cached conn that looks open but is server-terminated mid-txn:
        rollback raises psycopg.Error -> discard + reconnect (self-healing)."""
        conn = database.get_conn()
        conn.info.transaction_status = database.psycopg.pq.TransactionStatus.INTRANS
        conn.rollback.side_effect = database.psycopg.OperationalError("server closed")
        fresh = database.get_conn()
        assert fresh is not conn          # reconnected
        assert len(mock_psycopg) == 2

    def test_recovers_when_cached_conn_dead_on_probe(self, mock_psycopg):
        """A cached conn that's idle but server-recycled: the SELECT 1 liveness
        probe raises -> discard + reconnect."""
        conn = database.get_conn()
        # IDLE so rollback is skipped; the probe cursor raises instead.
        conn.info.transaction_status = database.psycopg.pq.TransactionStatus.IDLE
        conn.cursor.side_effect = database.psycopg.OperationalError("conn dead")
        fresh = database.get_conn()
        assert fresh is not conn
        assert len(mock_psycopg) == 2

    def test_idle_connection_not_rolled_back(self, mock_psycopg):
        conn = database.get_conn()
        conn.info.transaction_status = database.psycopg.pq.TransactionStatus.IDLE
        database.get_conn()
        conn.rollback.assert_not_called()


def _conn_with_cursor(rows=None, description=True):
    """Build a mock connection whose cursor returns the given rows."""
    conn = MagicMock()
    conn.closed = False
    conn.info.transaction_status = database.psycopg.pq.TransactionStatus.IDLE
    cursor = MagicMock()
    cursor.description = ["col"] if description else None
    cursor.fetchall.return_value = rows or []
    cursor.fetchone.return_value = (rows or [None])[0]
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


class TestExecuteQuery:
    def test_returns_rows_and_commits(self, monkeypatch):
        conn, cursor = _conn_with_cursor(rows=[{"id": 1}, {"id": 2}])
        monkeypatch.setattr(database, "get_conn", lambda: conn)
        result = database.execute_query("SELECT 1")
        assert result == [{"id": 1}, {"id": 2}]
        conn.commit.assert_called_once()

    def test_no_description_commits_and_returns_empty(self, monkeypatch):
        conn, cursor = _conn_with_cursor(description=False)
        monkeypatch.setattr(database, "get_conn", lambda: conn)
        assert database.execute_query("UPDATE t SET x=1") == []
        conn.commit.assert_called_once()

    def test_rolls_back_on_exception(self, monkeypatch):
        conn, cursor = _conn_with_cursor()
        cursor.execute.side_effect = RuntimeError("boom")
        monkeypatch.setattr(database, "get_conn", lambda: conn)
        with pytest.raises(RuntimeError):
            database.execute_query("SELECT 1")
        conn.rollback.assert_called_once()


class TestExecuteQueryOne:
    def test_returns_first_row(self, monkeypatch):
        conn, cursor = _conn_with_cursor(rows=[{"id": 7}])
        monkeypatch.setattr(database, "get_conn", lambda: conn)
        assert database.execute_query_one("SELECT 1") == {"id": 7}
        conn.commit.assert_called_once()

    def test_no_description_commits_and_returns_none(self, monkeypatch):
        conn, cursor = _conn_with_cursor(description=False)
        monkeypatch.setattr(database, "get_conn", lambda: conn)
        assert database.execute_query_one("UPDATE t SET x=1") is None
        conn.commit.assert_called_once()

    def test_rolls_back_on_exception(self, monkeypatch):
        conn, cursor = _conn_with_cursor()
        cursor.execute.side_effect = RuntimeError("boom")
        monkeypatch.setattr(database, "get_conn", lambda: conn)
        with pytest.raises(RuntimeError):
            database.execute_query_one("SELECT 1")
        conn.rollback.assert_called_once()
