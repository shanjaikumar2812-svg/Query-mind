"""Tests for app.services.ingestion_service."""

import io

import pytest
from werkzeug.datastructures import FileStorage

from app.services.ingestion_service import IngestionError, allowed_file, ingest_csv

SAMPLE_CSV = b"""Product Name,Units Sold,Sale Date
Widget A,10,2024-01-01
Widget B,5,2024-01-02
Widget A,7,2024-01-03
"""


def _make_file(content=SAMPLE_CSV, filename="sales.csv"):
    return FileStorage(stream=io.BytesIO(content), filename=filename)


def test_allowed_file_accepts_csv(app):
    with app.app_context():
        assert allowed_file("sales.csv") is True
        assert allowed_file("sales.xlsx") is False
        assert allowed_file("noextension") is False


def test_ingest_csv_creates_table_and_metadata(app):
    with app.app_context():
        meta = ingest_csv(_make_file(), session_id="sess_test")

        assert meta["row_count"] == 3
        assert meta["column_count"] == 3
        assert meta["table_name"].startswith("tbl_")
        assert any(c["name"] == "product_name" for c in meta["columns"])

        import os
        assert os.path.exists(meta["db_path"])


def test_ingest_csv_rejects_empty_file(app):
    with app.app_context():
        with pytest.raises(IngestionError):
            ingest_csv(_make_file(content=b"", filename="empty.csv"), session_id="sess_test")


def test_ingest_csv_rejects_non_csv_extension(app):
    with app.app_context():
        with pytest.raises(IngestionError):
            ingest_csv(_make_file(filename="sales.txt"), session_id="sess_test")


def test_ingest_csv_column_names_are_sanitized(app):
    content = b"Weird Col!!,Another One\n1,2\n3,4\n"
    with app.app_context():
        meta = ingest_csv(_make_file(content=content, filename="weird.csv"), session_id="sess_test")
        names = [c["name"] for c in meta["columns"]]
        for name in names:
            assert name.replace("_", "").isalnum()
