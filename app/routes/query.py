"""Natural-language query routes: ask a question, get SQL + results + chart."""

from flask import Blueprint, current_app, jsonify, request, session

from app.extensions import db, limiter
from app.models.dataset import Dataset
from app.models.history import QueryHistory
from app.services import ai_service, nlp_service
from app.services.ingestion_service import load_sample
from app.services.sql_service import ask_and_run
from app.utils.helpers import new_id
from app.utils.logger import get_logger

query_bp = Blueprint("query", __name__)
logger = get_logger(__name__)


@query_bp.route("/ask", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("RATE_LIMIT_ASK", "20 per minute"))
def ask():
    payload = request.get_json(silent=True) or {}
    dataset_id = payload.get("dataset_id")
    question = (payload.get("question") or "").strip()

    if not dataset_id or not question:
        return jsonify({"error": "dataset_id and question are required."}), 400

    max_question_length = current_app.config.get("MAX_QUESTION_LENGTH", 2000)
    if len(question) > max_question_length:
        return jsonify({
            "error": f"Question is too long (max {max_question_length} characters)."
        }), 400

    dataset = Dataset.query.get(dataset_id)
    # Same behavior for "doesn't exist" and "belongs to someone else's
    # session" — don't reveal which one it is.
    if not dataset or dataset.session_id != session.get("qm_session_id"):
        return jsonify({"error": "Dataset not found."}), 404

    column_names = [c["name"] for c in dataset.columns]
    nlp_hints = nlp_service.preprocess_question(question, column_names)

    import sqlite3
    conn = sqlite3.connect(f"file:{dataset.db_path}?mode=ro", uri=True)
    try:
        cursor = conn.cursor()
        cursor.execute(f'SELECT * FROM "{dataset.table_name}" LIMIT 3')
        cols = [d[0] for d in cursor.description]
        sample_rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    finally:
        conn.close()

    result = ask_and_run(question, dataset, nlp_hints, sample_rows)

    summary = ""
    chart_type = nlp_hints["suggested_chart"]
    if result["success"]:
        chart_type = nlp_service.suggest_chart_type(nlp_hints["intent"], result["columns"])
        try:
            summary = ai_service.summarize_result(question, result["columns"], result["results"])
        except ai_service.AIServiceError as exc:
            logger.warning("Summary generation skipped: %s", exc)

    history = QueryHistory(
        id=new_id("hist_"),
        session_id=session.get("qm_session_id", ""),
        dataset_id=dataset_id,
        natural_query=question,
        generated_sql=result["sql"],
        intent=nlp_hints["intent"],
        chart_type=chart_type,
        row_count=len(result["rows"]),
        success=result["success"],
        error_message=result["error"],
        retries=result["retries"],
    )
    db.session.add(history)
    db.session.commit()

    return jsonify({
        "history_id": history.id,
        "success": result["success"],
        "sql": result["sql"],
        "columns": result["columns"],
        "results": result["results"],
        "row_count": len(result["rows"]),
        "chart_type": chart_type,
        "intent": nlp_hints["intent"],
        "summary": summary,
        "retries": result["retries"],
        "error": result["error"],
    }), (200 if result["success"] else 422)


@query_bp.route("/history/<dataset_id>")
def history(dataset_id):
    dataset = Dataset.query.get(dataset_id)
    if not dataset or dataset.session_id != session.get("qm_session_id"):
        return jsonify({"error": "Dataset not found."}), 404

    records = (
        QueryHistory.query.filter_by(dataset_id=dataset_id)
        .order_by(QueryHistory.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({"history": [r.to_dict() for r in records]})
