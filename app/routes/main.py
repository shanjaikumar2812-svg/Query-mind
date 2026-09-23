"""Home, upload, dashboard, and workspace routes."""

from flask import Blueprint, abort, jsonify, render_template, request, session, url_for

from app.extensions import db
from app.models.dataset import Dataset
from app.models.session import Session as WorkspaceSession
from app.services.ingestion_service import (
    IngestionError,
    ingest_csv,
    ingest_sample,
    list_samples,
)
from app.utils.helpers import format_file_size, new_id
from app.utils.logger import get_logger

main_bp = Blueprint("main", __name__)
logger = get_logger(__name__)


def _get_or_create_session_id() -> str:
    """QueryMind uses a lightweight, login-free session tracked via cookie."""
    session_id = session.get("qm_session_id")
    if not session_id or not WorkspaceSession.query.get(session_id):
        session_id = new_id("sess_")
        db.session.add(WorkspaceSession(id=session_id))
        db.session.commit()
        session["qm_session_id"] = session_id
    return session_id


def _decorate(dataset: Dataset) -> dict:
    """Dataset dict plus the display-only fields the templates render."""
    data = dataset.to_dict()
    data["size_label"] = format_file_size(dataset.file_size_bytes or 0)
    data["uploaded_label"] = (
        dataset.uploaded_at.strftime("%d %b %Y, %H:%M") if dataset.uploaded_at else "Recently uploaded"
    )
    return data


def _session_datasets(session_id: str) -> list:
    return (
        Dataset.query.filter_by(session_id=session_id)
        .order_by(Dataset.uploaded_at.desc())
        .all()
    )


def _persist_dataset(meta: dict) -> Dataset:
    """Turn ingestion metadata into a committed Dataset row."""
    dataset = Dataset(
        id=meta["id"],
        session_id=meta["session_id"],
        original_filename=meta["original_filename"],
        table_name=meta["table_name"],
        db_path=meta["db_path"],
        row_count=meta["row_count"],
        column_count=meta["column_count"],
        file_size_bytes=meta["file_size_bytes"],
    )
    dataset.columns = meta["columns"]
    db.session.add(dataset)
    db.session.commit()
    return dataset


@main_bp.route("/")
def home():
    """Landing page: dropzone, curated samples, and the active session card."""
    session_id = _get_or_create_session_id()
    datasets = _session_datasets(session_id)
    latest = _decorate(datasets[0]) if datasets else None

    return render_template(
        "pages/upload.html",
        samples=list_samples(),
        latest=latest,
        dataset_count=len(datasets),
    )


@main_bp.route("/upload", methods=["POST"])
def upload():
    session_id = _get_or_create_session_id()

    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400
    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    try:
        meta = ingest_csv(file, session_id)
    except IngestionError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        # Full detail (file paths, library internals) goes to the server log
        # only — the client gets a safe, generic message.
        logger.exception("Unexpected ingestion failure")
        return jsonify({"error": "Unexpected error during upload."}), 500

    dataset = _persist_dataset(meta)

    return jsonify({
        "dataset": dataset.to_dict(),
        "redirect": url_for("main.workspace", dataset_id=dataset.id),
    }), 201


@main_bp.route("/upload/sample/<sample_key>", methods=["POST"])
def upload_sample(sample_key):
    """Load one of the curated sample datasets bundled with the app."""
    session_id = _get_or_create_session_id()

    try:
        meta = ingest_sample(sample_key, session_id)
    except IngestionError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        logger.exception("Unexpected sample ingestion failure")
        return jsonify({"error": "Unexpected error while loading the sample."}), 500

    dataset = _persist_dataset(meta)

    return jsonify({
        "dataset": dataset.to_dict(),
        "redirect": url_for("main.workspace", dataset_id=dataset.id),
    }), 201


@main_bp.route("/dashboard")
def dashboard():
    session_id = _get_or_create_session_id()
    datasets = _session_datasets(session_id)
    return render_template(
        "pages/dashboard.html",
        datasets=[_decorate(d) for d in datasets],
        session_id=session_id,
    )


@main_bp.route("/workspace/<dataset_id>")
def workspace(dataset_id):
    session_id = _get_or_create_session_id()
    dataset = Dataset.query.get_or_404(dataset_id)
    if dataset.session_id != session_id:
        # Behave exactly like "doesn't exist" — don't reveal that a dataset
        # with this id exists for someone else's session.
        abort(404)

    decorated = _decorate(dataset)
    return render_template(
        "pages/workspace.html",
        dataset=decorated,
        size_label=decorated["size_label"],
    )


@main_bp.route("/api/datasets/<dataset_id>", methods=["DELETE"])
def delete_dataset(dataset_id):
    import os
    session_id = _get_or_create_session_id()
    dataset = Dataset.query.get_or_404(dataset_id)
    if dataset.session_id != session_id:
        return jsonify({"error": "Dataset not found."}), 404
    db_path = dataset.db_path
    db.session.delete(dataset)
    db.session.commit()
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except OSError as exc:
        logger.warning("Could not remove dataset file %s: %s", db_path, exc)
    return jsonify({"deleted": dataset_id})
