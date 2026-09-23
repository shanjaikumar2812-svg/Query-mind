"""Tests for app.utils.security SQL validation."""

from app.utils.security import sanitize_filename, sanitize_identifier, validate_sql

TABLE = "tbl_ds_abc123"


def test_valid_select_passes():
    ok, err = validate_sql(f'SELECT * FROM "{TABLE}"', TABLE)
    assert ok is True
    assert err == ""


def test_rejects_insert():
    ok, err = validate_sql(f"INSERT INTO {TABLE} VALUES (1)", TABLE)
    assert ok is False
    assert "SELECT" in err


def test_rejects_drop_table():
    ok, err = validate_sql(f"DROP TABLE {TABLE}", TABLE)
    assert ok is False


def test_rejects_forbidden_keyword_inside_select():
    ok, err = validate_sql(f"SELECT * FROM {TABLE}; DROP TABLE {TABLE}", TABLE)
    assert ok is False


def test_rejects_sql_comments():
    ok, err = validate_sql(f"SELECT * FROM {TABLE} -- sneaky", TABLE)
    assert ok is False


def test_rejects_wrong_table():
    ok, err = validate_sql("SELECT * FROM some_other_table", TABLE)
    assert ok is False
    assert TABLE in err


def test_rejects_empty_sql():
    ok, err = validate_sql("", TABLE)
    assert ok is False


def test_sanitize_identifier_strips_special_chars():
    assert sanitize_identifier("Sale Date!!") == "sale_date"


def test_sanitize_identifier_handles_leading_digit():
    assert sanitize_identifier("2024_sales").startswith("col_")


def test_sanitize_filename_strips_path_traversal():
    assert sanitize_filename("../../etc/passwd.csv") == "passwd.csv"
