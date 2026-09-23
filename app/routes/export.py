"""CSV, Excel, and PDF download routes, keyed off a stored query-history record."""

from flask import Blueprint, jsonify, send_file, session

from app.models.history import QueryHistory
from app.services import export_service
from app.services.sql_service import SQLExecutionError, execute_sql
from app.utils.helpers import rows_to_dicts
from app.utils.logger import get_logger

export_bp = Blueprint("export", __name__)
logger = get_logger(__name__)


def _rerun_history(history_id):
    record = QueryHistory.query.get(history_id)
    # Treat "doesn't exist" and "belongs to someone else's session" the same
    # way, so a guessed/enumerated history_id can't be used to pull another
    # session's export.
    if not record or record.session_id != session.get("qm_session_id"):
        return None, None, None, None

    dataset = record.dataset  # backref from Dataset.query_history
    try:
        columns, rows = execute_sql(dataset.db_path, record.generated_sql, dataset.table_name)
    except SQLExecutionError as exc:
        logger.error("Could not re-run stored query for export: %s", exc)
        return None, None, None, record
    return columns, rows, dataset, record


@export_bp.route("/csv/<history_id>")
def csv_export(history_id):
    columns, rows, dataset, record = _rerun_history(history_id)
    if not record:
        return jsonify({"error": "Query history not found."}), 404
    if columns is None:
        return jsonify({"error": "Could not regenerate results for export."}), 500

    path = export_service.export_csv(columns, rows)
    return send_file(path, as_attachment=True, download_name="querymind_results.csv")


@export_bp.route("/excel/<history_id>")
def excel_export(history_id):
    columns, rows, dataset, record = _rerun_history(history_id)
    if not record:
        return jsonify({"error": "Query history not found."}), 404
    if columns is None:
        return jsonify({"error": "Could not regenerate results for export."}), 500

    path = export_service.export_excel(columns, rows)
    return send_file(path, as_attachment=True, download_name="querymind_results.xlsx")


@export_bp.route("/pdf/<history_id>")
def pdf_export(history_id):
    columns, rows, dataset, record = _rerun_history(history_id)
    if not record:
        return jsonify({"error": "Query history not found."}), 404
    if columns is None:
        return jsonify({"error": "Could not regenerate results for export."}), 500

    try:
        path = export_service.export_pdf(
            title="QueryMind Report",
            question=record.natural_query,
            sql=record.generated_sql,
            columns=columns,
            rows=rows_to_dicts(columns, rows),
        )
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    return send_file(path, as_attachment=True, download_name="querymind_report.pdf")
