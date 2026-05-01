"""SQLite connection management for micro ORM."""

import sqlite3
import threading


class Database:
    """SQLite database connection manager with context manager and transaction support."""

    def __init__(self, db_path=":memory:"):
        self.db_path = db_path
        self._conn = None
        self._lock = threading.Lock()

    def connect(self):
        """Open the database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self

    @property
    def connected(self):
        return self._conn is not None

    def execute(self, sql, params=None):
        """Execute a SQL statement."""
        with self._lock:
            cursor = self._conn.execute(sql, params or ())
            return cursor

    def fetchall(self, sql, params=None):
        """Execute a query and return all rows as dicts."""
        cursor = self.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def fetchone(self, sql, params=None):
        """Execute a query and return one row as dict."""
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def begin(self):
        """Begin a transaction."""
        self.execute("BEGIN")

    def commit(self):
        """Commit the current transaction."""
        self._conn.commit()

    def rollback(self):
        """Rollback the current transaction."""
        self._conn.rollback()

    def close(self):
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False
