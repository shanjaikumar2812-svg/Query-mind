"""Session model — a lightweight, cookie-free workspace grouping."""

from datetime import datetime

from app.extensions import db


class Session(db.Model):
    """Represents one QueryMind workspace session (no login required)."""

    __tablename__ = "sessions"

    id = db.Column(db.String(32), primary_key=True)
    label = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    datasets = db.relationship(
        "Dataset", backref="session", lazy=True, cascade="all, delete-orphan"
    )
    history = db.relationship(
        "QueryHistory", backref="session", lazy=True, cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "dataset_count": len(self.datasets),
        }
