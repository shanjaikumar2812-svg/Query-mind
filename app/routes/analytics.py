"""Insights and forecasting routes."""

from flask import Blueprint, jsonify, request, session

from app.models.dataset import Dataset
from app.services import analytics_service
from app.utils.logger import get_logger

analytics_bp = Blueprint("analytics", __name__)
logger = get_logger(__name__)


def _get_dataset_or_404(dataset_id):
    """Look up a dataset, but only if it belongs to the caller's own session.

    Returns None both when the id doesn't exist at all and when it belongs to
    someone else — callers shouldn't be able to tell the two cases apart.
    """
    dataset = Dataset.query.get(dataset_id)
    if not dataset or dataset.session_id != session.get("qm_session_id"):
        return None
    return dataset


@analytics_bp.route("/profile/<dataset_id>")
def profile(dataset_id):
    dataset = _get_dataset_or_404(dataset_id)
    if not dataset:
        return jsonify({"error": "Dataset not found."}), 404
    try:
        result = analytics_service.profile_dataset(dataset.db_path, dataset.table_name)
        return jsonify(result)
    except Exception:
        logger.exception("Profiling failed")
        return jsonify({"error": "Profiling failed."}), 500


@analytics_bp.route("/correlation/<dataset_id>")
def correlation(dataset_id):
    dataset = _get_dataset_or_404(dataset_id)
    if not dataset:
        return jsonify({"error": "Dataset not found."}), 404
    try:
        result = analytics_service.correlation_matrix(dataset.db_path, dataset.table_name)
        return jsonify(result)
    except Exception:
        logger.exception("Correlation computation failed")
        return jsonify({"error": "Correlation computation failed."}), 500


@analytics_bp.route("/forecast", methods=["POST"])
def forecast():
    payload = request.get_json(silent=True) or {}
    dataset_id = payload.get("dataset_id")
    date_column = payload.get("date_column")
    value_column = payload.get("value_column")
    horizon = payload.get("horizon")

    dataset = _get_dataset_or_404(dataset_id)
    if not dataset:
        return jsonify({"error": "Dataset not found."}), 404
    if not date_column or not value_column:
        return jsonify({"error": "date_column and value_column are required."}), 400

    try:
        result = analytics_service.forecast_series(
            dataset.db_path, dataset.table_name, date_column, value_column, horizon
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        logger.exception("Forecasting failed")
        return jsonify({"error": "Forecasting failed."}), 500


@analytics_bp.route("/outliers", methods=["POST"])
def outliers():
    payload = request.get_json(silent=True) or {}
    dataset_id = payload.get("dataset_id")
    column = payload.get("column")

    dataset = _get_dataset_or_404(dataset_id)
    if not dataset:
        return jsonify({"error": "Dataset not found."}), 404
    if not column:
        return jsonify({"error": "column is required."}), 400

    try:
        result = analytics_service.detect_outliers(dataset.db_path, dataset.table_name, column)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        logger.exception("Outlier detection failed")
        return jsonify({"error": "Outlier detection failed."}), 500
