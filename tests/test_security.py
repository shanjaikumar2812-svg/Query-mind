"""Security-hardening tests: SQL/table allowlisting, IDOR, error-message
leakage, rate limiting, and Groq-failure handling.

These complement (not replace) tests/test_sql_validator.py, which already
covers the regex-based validator in app.utils.security.
"""

import io
import os
import sqlite3
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest
from groq import RateLimitError

from app import create_app
from app.config import TestingConfig
from app.services import ai_service
from app.services.sql_service import SQLExecutionError, ask_and_run, execute_sql


# ---------------------------------------------------------------------------
# SQL injection / self-healing (validator + engine-level authorizer)
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_table_db(tmp_path):
    """A dataset db with the "real" table plus a second table representing
    another dataset's data that must never be reachable from this one.
    """
    db_path = os.path.join(tmp_path, "ds.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE tbl_mine (id INTEGER, name TEXT)")
    conn.execute("CREATE TABLE tbl_other (id INTEGER, ssn TEXT)")
    conn.executemany("INSERT INTO tbl_mine VALUES (?, ?)", [(1, "a"), (2, "b")])
    conn.execute("INSERT INTO tbl_other VALUES (1, '999-99-9999')")
    conn.commit()
    conn.close()
    return db_path


def test_classic_injection_rejected(two_table_db):
    with pytest.raises(SQLExecutionError):
        execute_sql(two_table_db, "SELECT * FROM tbl_mine; DROP TABLE tbl_mine;", "tbl_mine")


def test_prompt_injection_style_request_still_produces_rejected_sql(two_table_db):
    # Even if the LLM were tricked into emitting a destructive statement,
    # the backend validator/authorizer must reject it regardless of the
    # natural-language wording that produced it.
    with pytest.raises(SQLExecutionError):
        execute_sql(two_table_db, "DELETE FROM tbl_mine", "tbl_mine")


def test_valid_select_still_works(two_table_db):
    columns, rows = execute_sql(two_table_db, "SELECT * FROM tbl_mine", "tbl_mine")
    assert columns == ["id", "name"]
    assert rows == [(1, "a"), (2, "b")]


def test_authorizer_blocks_join_into_other_table(two_table_db):
    """The regex validator alone would allow this (it only checks that the
    allowed table appears after FROM/JOIN); the sqlite3 authorizer added in
    execute_sql() is the backstop that actually enforces the table allowlist.
    """
    with pytest.raises(SQLExecutionError):
        execute_sql(
            two_table_db,
            "SELECT * FROM tbl_mine JOIN tbl_other ON tbl_mine.id = tbl_other.id",
            "tbl_mine",
        )


def test_authorizer_blocks_subquery_into_other_table(two_table_db):
    with pytest.raises(SQLExecutionError):
        execute_sql(
            two_table_db,
            "SELECT * FROM tbl_mine WHERE id IN (SELECT id FROM tbl_other)",
            "tbl_mine",
        )


def test_authorizer_blocks_attach(two_table_db):
    with pytest.raises(SQLExecutionError):
        execute_sql(two_table_db, "ATTACH DATABASE ':memory:' AS x", "tbl_mine")


def test_query_timeout_stops_runaway_query(tmp_path):
    db_path = os.path.join(tmp_path, "big.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE tbl_big (id INTEGER)")
    conn.executemany("INSERT INTO tbl_big VALUES (?)", [(i,) for i in range(1500)])
    conn.commit()
    conn.close()

    app = create_app("testing")
    app.config["SQL_QUERY_TIMEOUT_SECONDS"] = 1
    with app.app_context():
        start = time.monotonic()
        with pytest.raises(SQLExecutionError, match="execution limit"):
            # Forces full materialization (aggregate) over a large cartesian
            # product before any row can be returned.
            execute_sql(
                db_path,
                "SELECT COUNT(*) FROM tbl_big a, tbl_big b, tbl_big c",
                "tbl_big",
            )
        assert time.monotonic() - start < 5  # didn't hang


def test_self_healing_retry_still_goes_through_validator(tmp_path):
    """The corrected SQL from a self-healing retry must be validated exactly
    like the first attempt — never executed directly.
    """
    db_path = os.path.join(tmp_path, "heal.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE tbl_x (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO tbl_x VALUES (1, 'a')")
    conn.commit()
    conn.close()

    class FakeDataset:
        table_name = "tbl_x"
        columns = [{"name": "id", "dtype": "INTEGER"}, {"name": "name", "dtype": "TEXT"}]

    dataset = FakeDataset()
    dataset.db_path = db_path

    app = create_app("testing")
    app.config["GROQ_API_KEY"] = "test"
    with app.app_context():
        calls = {"n": 0}

        def fake_create(*args, **kwargs):
            calls["n"] += 1
            msg = MagicMock()
            # First attempt: an injection-style statement that must be
            # rejected. Second attempt: a corrected, valid SELECT.
            msg.message.content = (
                "DROP TABLE tbl_x" if calls["n"] == 1 else "SELECT * FROM tbl_x"
            )
            resp = MagicMock()
            resp.choices = [msg]
            return resp

        with patch.object(ai_service, "_get_client") as get_client:
            fake_client = MagicMock()
            fake_client.chat.completions.create.side_effect = fake_create
            get_client.return_value = fake_client

            result = ask_and_run("anything", dataset, {}, [])

        assert result["success"] is True
        assert result["retries"] == 1
        assert result["sql"] == "SELECT * FROM tbl_x"
        assert result["rows"] == [(1, "a")]


# ---------------------------------------------------------------------------
# Groq 429 / provider-error handling
# ---------------------------------------------------------------------------

def test_groq_rate_limit_does_not_crash_and_does_not_leak_details():
    app = create_app("testing")
    app.config["GROQ_API_KEY"] = "test"
    with app.app_context():
        with patch.object(ai_service, "_get_client") as get_client:
            fake_client = MagicMock()
            fake_client.chat.completions.create.side_effect = RateLimitError(
                "rate limited", response=MagicMock(headers={}), body=None
            )
            get_client.return_value = fake_client

            with pytest.raises(ai_service.AIServiceError) as excinfo:
                ai_service.generate_sql("q", "t", [{"name": "id", "dtype": "INTEGER"}], [])
            assert "rate limit" in str(excinfo.value).lower()

            # summarize_result must fall back instead of raising.
            summary = ai_service.summarize_result("q", ["id"], [(1,)])
            assert summary == "Query returned 1 row(s) across 1 column(s)."


def test_groq_generic_failure_does_not_leak_internals():
    app = create_app("testing")
    app.config["GROQ_API_KEY"] = "test"
    with app.app_context():
        with patch.object(ai_service, "_get_client") as get_client:
            fake_client = MagicMock()
            fake_client.chat.completions.create.side_effect = RuntimeError(
                "internal detail: connection to 10.0.0.5:9999 secret=abc123"
            )
            get_client.return_value = fake_client

            with pytest.raises(ai_service.AIServiceError) as excinfo:
                ai_service.generate_sql("q", "t", [{"name": "id", "dtype": "INTEGER"}], [])
            assert "10.0.0.5" not in str(excinfo.value)
            assert "secret=abc123" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Broken access control (IDOR) — dataset/history ownership across sessions
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_clients(app):
    """Two independent cookie jars (sessions) against the same app."""
    return app.test_client(), app.test_client()


def _upload(client, content=b"id,name,amount\n1,alice,10\n2,bob,20\n3,carol,30\n"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(content), "t.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    return resp.get_json()["dataset"]["id"]


def test_workspace_idor_blocked(two_clients):
    client_a, client_b = two_clients
    dataset_id = _upload(client_a)

    assert client_b.get(f"/workspace/{dataset_id}").status_code == 404
    assert client_a.get(f"/workspace/{dataset_id}").status_code == 200


def test_delete_dataset_idor_blocked(two_clients):
    client_a, client_b = two_clients
    dataset_id = _upload(client_a)

    resp = client_b.delete(f"/api/datasets/{dataset_id}")
    assert resp.status_code == 404

    # Confirm it wasn't actually deleted.
    assert client_a.get(f"/workspace/{dataset_id}").status_code == 200


def test_ask_and_history_idor_blocked(two_clients):
    client_a, client_b = two_clients
    dataset_id = _upload(client_a)

    resp = client_b.post("/query/ask", json={"dataset_id": dataset_id, "question": "how many rows?"})
    assert resp.status_code == 404

    resp = client_b.get(f"/query/history/{dataset_id}")
    assert resp.status_code == 404
    assert client_a.get(f"/query/history/{dataset_id}").status_code == 200


def test_analytics_idor_blocked(two_clients):
    client_a, client_b = two_clients
    dataset_id = _upload(client_a)

    assert client_b.get(f"/analytics/profile/{dataset_id}").status_code == 404
    assert client_b.get(f"/analytics/correlation/{dataset_id}").status_code == 404
    assert client_a.get(f"/analytics/profile/{dataset_id}").status_code == 200

    resp = client_b.post(
        "/analytics/forecast",
        json={"dataset_id": dataset_id, "date_column": "id", "value_column": "amount"},
    )
    assert resp.status_code == 404

    resp = client_b.post(
        "/analytics/outliers", json={"dataset_id": dataset_id, "column": "amount"}
    )
    assert resp.status_code == 404


def test_export_idor_blocked(two_clients, app):
    """A history record's export must not be downloadable from another
    session, even if the history_id is guessed/enumerated.
    """
    client_a, client_b = two_clients
    dataset_id = _upload(client_a)

    with app.app_context():
        from app.extensions import db
        from app.models.history import QueryHistory
        from app.utils.helpers import new_id

        history_id = new_id("hist_")
        db.session.add(
            QueryHistory(
                id=history_id,
                session_id=_session_id_of(client_a),
                dataset_id=dataset_id,
                natural_query="q",
                generated_sql=f'SELECT * FROM "{_table_name_of(dataset_id, app)}"',
                success=True,
            )
        )
        db.session.commit()

    assert client_b.get(f"/export/csv/{history_id}").status_code == 404
    assert client_a.get(f"/export/csv/{history_id}").status_code == 200


def _session_id_of(client):
    with client.session_transaction() as sess:
        return sess.get("qm_session_id")


def _table_name_of(dataset_id, app):
    with app.app_context():
        from app.models.dataset import Dataset

        return Dataset.query.get(dataset_id).table_name


# ---------------------------------------------------------------------------
# Error-message leakage
# ---------------------------------------------------------------------------

def test_upload_unexpected_error_does_not_leak_exception_text(client):
    with patch(
        "app.routes.main.ingest_csv",
        side_effect=RuntimeError("leaked /etc/passwd path or secret_token=xyz"),
    ):
        resp = client.post(
            "/upload",
            data={"file": (io.BytesIO(b"a,b\n1,2\n"), "t.csv")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 500
    body = resp.get_json()
    assert "secret_token" not in body["error"]
    assert "/etc/passwd" not in body["error"]


def test_analytics_unexpected_error_does_not_leak_exception_text(client):
    dataset_id = _upload(client)
    with patch(
        "app.routes.analytics.analytics_service.profile_dataset",
        side_effect=RuntimeError("leaked internal db path /srv/secret/data.db"),
    ):
        resp = client.get(f"/analytics/profile/{dataset_id}")
    assert resp.status_code == 500
    assert "/srv/secret" not in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# Question length limit
# ---------------------------------------------------------------------------

def test_oversized_question_rejected(client):
    dataset_id = _upload(client)
    app_config_limit = 2000
    too_long = "a" * (app_config_limit + 1)
    resp = client.post("/query/ask", json={"dataset_id": dataset_id, "question": too_long})
    assert resp.status_code == 400
    assert "too long" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def test_ask_endpoint_rate_limited(tmp_path, monkeypatch):
    """RATELIMIT_ENABLED must be True *before* create_app() runs (Flask-
    Limiter reads it once at init_app time), so this test builds its own app
    instead of using the shared `app` fixture (which is deliberately
    rate-limit-disabled for the rest of the suite).
    """
    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    try:
        app = create_app("testing")
        app.config["RATE_LIMIT_ASK"] = "2 per minute"
        app.config["DATA_DIR"] = str(tmp_path / "data")
        app.config["DATABASES_DIR"] = str(tmp_path / "data" / "databases")
        app.config["EXPORT_DIR"] = str(tmp_path / "exports")
        os.makedirs(app.config["DATABASES_DIR"], exist_ok=True)
        os.makedirs(app.config["EXPORT_DIR"], exist_ok=True)

        client = app.test_client()
        with patch("app.routes.query.ask_and_run") as fake_ask, patch.object(
            ai_service, "summarize_result", return_value=""
        ):
            fake_ask.return_value = {
                "sql": "SELECT 1", "columns": ["x"], "rows": [(1,)],
                "results": [{"x": 1}], "retries": 0, "success": True, "error": None,
            }
            dataset_id = _upload(client)
            codes = [
                client.post("/query/ask", json={"dataset_id": dataset_id, "question": "q"}).status_code
                for _ in range(4)
            ]
        assert codes[:2] == [200, 200]
        assert 429 in codes[2:]
    finally:
        monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", False)


# ---------------------------------------------------------------------------
# Security headers / CORS
# ---------------------------------------------------------------------------

def test_security_headers_present(client):
    resp = client.get("/")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_cors_does_not_allow_arbitrary_origins_by_default(client):
    resp = client.get("/", headers={"Origin": "https://evil.example.com"})
    assert resp.headers.get("Access-Control-Allow-Origin") is None
