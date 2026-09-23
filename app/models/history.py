"""QueryHistory model — an audit trail of natural-language questions asked."""

from datetime import datetime

from app.extensions import db


class QueryHistory(db.Model):
    """One natural-language question and the SQL/result it produced."""

    __tablename__ = "query_history"

    id = db.Column(db.String(32), primary_key=True)
    session_id = db.Column(db.String(32), db.ForeignKey("sessions.id"), nullable=False)
    dataset_id = db.Column(db.String(32), db.ForeignKey("datasets.id"), nullable=False)

    natural_query = db.Column(db.Text, nullable=False)
    generated_sql = db.Column(db.Text, nullable=True)
    intent = db.Column(db.String(40), nullable=True)  # aggregate/trend/filter/forecast/...
    chart_type = db.Column(db.String(40), nullable=True)
    row_count = db.Column(db.Integer, default=0)
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text, nullable=True)
    retries = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "dataset_id": self.dataset_id,
            "natural_query": self.natural_query,
            "generated_sql": self.generated_sql,
            "intent": self.intent,
            "chart_type": self.chart_type,
            "row_count": self.row_count,
            "success": self.success,
            "error_message": self.error_message,
            "retries": self.retries,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
