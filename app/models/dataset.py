"""Dataset model — metadata for an uploaded CSV and its backing SQLite table."""

import json
from datetime import datetime

from app.extensions import db


class Dataset(db.Model):
    """One uploaded CSV, materialized as a table inside its own SQLite DB file."""

    __tablename__ = "datasets"

    id = db.Column(db.String(32), primary_key=True)
    session_id = db.Column(db.String(32), db.ForeignKey("sessions.id"), nullable=False)

    original_filename = db.Column(db.String(255), nullable=False)
    table_name = db.Column(db.String(64), nullable=False)
    db_path = db.Column(db.String(500), nullable=False)

    row_count = db.Column(db.Integer, default=0)
    column_count = db.Column(db.Integer, default=0)
    columns_json = db.Column(db.Text, default="[]")  # [{"name":..,"dtype":..}, ...]
    file_size_bytes = db.Column(db.Integer, default=0)

    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    query_history = db.relationship(
        "QueryHistory", backref="dataset", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def columns(self) -> list:
        try:
            return json.loads(self.columns_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @columns.setter
    def columns(self, value: list) -> None:
        self.columns_json = json.dumps(value)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "filename": self.original_filename,
            "table_name": self.table_name,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": self.columns,
            "file_size_bytes": self.file_size_bytes,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }
