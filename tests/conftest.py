"""Shared pytest fixtures: an isolated Flask app + test client per test."""

import os

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Flask app configured for testing with all storage redirected to tmp_path."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-used")

    flask_app = create_app("testing")

    data_dir = tmp_path / "data"
    flask_app.config["DATA_DIR"] = str(data_dir)
    flask_app.config["DATABASES_DIR"] = str(data_dir / "databases")
    flask_app.config["EXPORT_DIR"] = str(tmp_path / "exports")
    flask_app.config["LOG_DIR"] = str(tmp_path / "logs")

    os.makedirs(flask_app.config["DATABASES_DIR"], exist_ok=True)
    os.makedirs(flask_app.config["EXPORT_DIR"], exist_ok=True)

    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db
