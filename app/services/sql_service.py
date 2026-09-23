"""SQL execution service: validates and runs generated SQL against a dataset's
per-file SQLite database, with a self-healing retry loop against the AI service.
"""

import sqlite3
import time

from flask import current_app

from app.services import ai_service
from app.utils.helpers import rows_to_dicts
from app.utils.logger import get_logger
from app.utils.security import validate_sql

logger = get_logger(__name__)

# Functions that provide no read-only analytical value but do carry a real
# security risk (arbitrary native-code loading) if a future SQLite build or
# extension ever made them reachable. Denied unconditionally by the authorizer
# below, in addition to the existing keyword-based validator.
_DENIED_SQL_FUNCTIONS = {"load_extension"}


class SQLExecutionError(Exception):
    """Raised when SQL fails validation or execution after all retries."""


def _make_authorizer(allowed_table: str):
    """Build a sqlite3 authorizer callback that is the *engine-level* backstop
    behind `validate_sql`: it only allows reading `allowed_table` (and its
    columns), only allows a top-level SELECT, and denies every write/DDL/
    attach/pragma action regardless of how the SQL text was assembled. This
    catches things a regex validator can miss — e.g. a JOIN or subquery that
    pulls in a second table, or `sqlite_master` — without changing what a
    normal single-table query is allowed to do.
    """
    allowed = (allowed_table or "").lower()

    def authorizer(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            if (arg1 or "").lower() == allowed:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION:
            if (arg2 or "").lower() in _DENIED_SQL_FUNCTIONS:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        # Everything else — INSERT/UPDATE/DELETE, CREATE_*/DROP_*/ALTER_TABLE,
        # ATTACH/DETACH, PRAGMA, TRANSACTION/SAVEPOINT, TRIGGER/VIEW creation,
        # REINDEX/ANALYZE, VTABLE, etc. — is denied by default.
        return sqlite3.SQLITE_DENY

    return authorizer


def execute_sql(db_path: str, sql: str, table_name: str, limit: int = None):
    """Validate then run `sql` read-only against the dataset's SQLite file.

    Returns (columns, rows) on success. Raises SQLExecutionError otherwise.
    """
    is_valid, error = validate_sql(sql, table_name)
    if not is_valid:
        raise SQLExecutionError(error)

    try:
        limit = limit or current_app.config.get("SQL_STATEMENT_TIMEOUT_ROWS", 100000)
        query_timeout = current_app.config.get("SQL_QUERY_TIMEOUT_SECONDS", 10)
    except RuntimeError:
        limit = limit or 100000
        query_timeout = 10

    # Open read-only via URI to guarantee no writes happen even if a check
    # above were somehow bypassed.
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=10)
    except sqlite3.OperationalError as exc:
        raise SQLExecutionError(f"Could not open dataset database: {exc}") from exc

    # Engine-level allowlist: only `table_name` may be read, only SELECT is
    # permitted, no writes/DDL/ATTACH/PRAGMA of any kind — this is the final
    # security boundary even if the SQL text itself were crafted to slip past
    # the validator above.
    conn.set_authorizer(_make_authorizer(table_name))

    # Abort runaway queries (e.g. an accidental cross join) instead of letting
    # them tie up the process indefinitely. n=1000 checks the deadline roughly
    # every 1000 VM instructions, which is frequent enough to bound wall time
    # without adding meaningful overhead to normal queries.
    deadline = time.monotonic() + query_timeout

    def _progress_handler():
        return 1 if time.monotonic() > deadline else 0

    conn.set_progress_handler(_progress_handler, 1000)

    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(limit)
        return columns, rows
    except sqlite3.ProgrammingError as exc:
        # Raised by sqlite3 for actions the authorizer denied ("not authorized"),
        # in addition to genuine SQL errors.
        raise SQLExecutionError(str(exc)) from exc
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc).lower():
            raise SQLExecutionError(
                f"Query exceeded the {query_timeout}s execution limit and was stopped."
            ) from exc
        raise SQLExecutionError(str(exc)) from exc
    except sqlite3.Error as exc:
        raise SQLExecutionError(str(exc)) from exc
    finally:
        conn.close()


def ask_and_run(question: str, dataset, nlp_hints: dict, sample_rows: list) -> dict:
    """Full NL -> SQL -> execution pipeline with self-healing retries.

    `dataset` is an app.models.dataset.Dataset instance.
    Returns a dict: {sql, columns, rows, retries, success, error}.
    """
    max_retries = current_app.config.get("AI_MAX_RETRIES", 3)
    previous_error = None
    previous_sql = None
    last_sql = None

    for attempt in range(1, max_retries + 1):
        try:
            sql = ai_service.generate_sql(
                question=question,
                table_name=dataset.table_name,
                columns=dataset.columns,
                sample_rows=sample_rows,
                nlp_hints=nlp_hints,
                previous_error=previous_error,
                previous_sql=previous_sql,
            )
            last_sql = sql
            columns, rows = execute_sql(dataset.db_path, sql, dataset.table_name)
            return {
                "sql": sql,
                "columns": columns,
                "rows": rows,
                "results": rows_to_dicts(columns, rows),
                "retries": attempt - 1,
                "success": True,
                "error": None,
            }
        except (SQLExecutionError, ai_service.AIServiceError) as exc:
            logger.warning("Attempt %s/%s failed: %s", attempt, max_retries, exc)
            previous_error = str(exc)
            previous_sql = last_sql
            continue

    return {
        "sql": last_sql,
        "columns": [],
        "rows": [],
        "results": [],
        "retries": max_retries,
        "success": False,
        "error": previous_error or "Failed to generate a valid query.",
    }
