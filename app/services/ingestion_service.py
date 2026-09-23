"""CSV ingestion: encoding detection, cleaning, and dynamic SQLite table creation.

Each uploaded CSV gets its own SQLite database file under DATA_DIR/databases/
so datasets never collide and can be dropped independently.
"""

import os
import sqlite3

import chardet
import pandas as pd
from flask import current_app
from werkzeug.datastructures import FileStorage

from app.utils.helpers import new_id
from app.utils.logger import get_logger
from app.utils.security import sanitize_filename, sanitize_identifier

logger = get_logger(__name__)


class IngestionError(Exception):
    """Raised when a CSV fails validation or cannot be ingested."""


def allowed_file(filename: str) -> bool:
    try:
        allowed_extensions = current_app.config["ALLOWED_EXTENSIONS"]
    except RuntimeError:
        allowed_extensions = {"csv"}
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in allowed_extensions


def _detect_encoding(raw_bytes: bytes) -> str:
    result = chardet.detect(raw_bytes[:200000])
    return result.get("encoding") or "utf-8"


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names, drop fully-empty rows/columns, coerce dtypes."""
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")

    seen = {}
    clean_cols = []
    for col in df.columns:
        base = sanitize_identifier(str(col))
        count = seen.get(base, 0)
        seen[base] = count + 1
        clean_cols.append(base if count == 0 else f"{base}_{count}")
    df.columns = clean_cols

    # Best-effort numeric/datetime coercion for text columns.
    # pandas 2 types these as `object`; pandas 3 defaults them to `str`, so
    # check both or date columns silently stay strings and forecasting breaks.
    for col in df.columns:
        is_text = df[col].dtype == object or pd.api.types.is_string_dtype(df[col])
        if is_text:
            coerced = pd.to_numeric(df[col], errors="coerce")
            if coerced.notna().mean() > 0.9:
                df[col] = coerced
                continue
            try:
                dt = pd.to_datetime(df[col], errors="coerce", format="mixed")
                if dt.notna().mean() > 0.9:
                    df[col] = dt
            except (ValueError, TypeError):
                pass

    return df


def ingest_csv(file: FileStorage, session_id: str) -> dict:
    """Read, clean, and persist an uploaded CSV into its own SQLite DB.

    Returns a dict of metadata ready to populate a Dataset row.
    """
    filename = sanitize_filename(file.filename or "upload.csv")
    if not allowed_file(filename):
        raise IngestionError("Only .csv files are supported.")

    raw = file.read()
    if not raw:
        raise IngestionError("Uploaded file is empty.")
    encoding = _detect_encoding(raw)

    from io import BytesIO
    try:
        df = pd.read_csv(BytesIO(raw), encoding=encoding, low_memory=False)
    except Exception as exc:  # pandas raises many exception subtypes for bad CSVs
        raise IngestionError(f"Could not parse CSV ({encoding}): {exc}") from exc

    max_rows = current_app.config["MAX_ROWS"]
    max_cols = current_app.config["MAX_COLUMNS"]
    if len(df) > max_rows:
        raise IngestionError(f"Dataset exceeds max row limit ({max_rows}).")
    if len(df.columns) > max_cols:
        raise IngestionError(f"Dataset exceeds max column limit ({max_cols}).")
    if len(df.columns) == 0:
        raise IngestionError("No columns detected in the uploaded file.")

    df = _clean_dataframe(df)

    dataset_id = new_id("ds_")
    table_name = f"tbl_{dataset_id}"
    db_filename = f"{dataset_id}.db"
    db_path = os.path.join(current_app.config["DATABASES_DIR"], db_filename)

    os.makedirs(current_app.config["DATABASES_DIR"], exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
    finally:
        conn.close()

    columns_meta = [
        {"name": col, "dtype": str(df[col].dtype)} for col in df.columns
    ]

    logger.info("Ingested dataset %s (%s rows, %s cols) -> %s", dataset_id, len(df), len(df.columns), db_path)

    return {
        "id": dataset_id,
        "session_id": session_id,
        "original_filename": filename,
        "table_name": table_name,
        "db_path": db_path,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": columns_meta,
        "file_size_bytes": len(raw),
    }


# --------------------------------------------------------------------------
# Curated sample datasets
#
# These ship with the app (sample_data/) so a first-time visitor can try
# QueryMind without having a CSV of their own handy. Loading one runs through
# exactly the same ingest_csv() path as a real upload.
# --------------------------------------------------------------------------

SAMPLE_DATASETS = {
    "flipkart_mobiles": {
        "label": "Flipkart Mobiles",
        "filename": "flipkart_mobiles.csv",
    },
    "saas_mrr": {
        "label": "SaaS MRR",
        "filename": "saas_mrr.csv",
    },
    "ecommerce_orders": {
        "label": "E-commerce Orders",
        "filename": "ecommerce_orders.csv",
    },
}


def _sample_path(filename: str) -> str:
    return os.path.join(current_app.config["SAMPLE_DATASETS_DIR"], filename)


def list_samples() -> list:
    """Return metadata for every bundled sample that actually exists on disk."""
    samples = []
    for key, meta in SAMPLE_DATASETS.items():
        path = _sample_path(meta["filename"])
        if not os.path.exists(path):
            logger.warning("Sample dataset missing from disk: %s", path)
            continue

        try:
            row_count = max(sum(1 for _ in open(path, "r", encoding="utf-8", errors="ignore")) - 1, 0)
        except OSError:
            row_count = 0

        if row_count >= 1000:
            size_label = f"{row_count / 1000:.1f}k"
        else:
            size_label = str(row_count)

        samples.append({
            "key": key,
            "label": meta["label"],
            "filename": meta["filename"],
            "row_count": row_count,
            "size_label": size_label,
        })
    return samples


def ingest_sample(sample_key: str, session_id: str) -> dict:
    """Ingest one of the bundled sample CSVs for the given session.

    Reuses ingest_csv() by wrapping the file on disk in a FileStorage, so
    samples get identical cleaning, validation, and storage treatment.
    """
    meta = SAMPLE_DATASETS.get(sample_key)
    if not meta:
        raise IngestionError("Unknown sample dataset.")

    path = _sample_path(meta["filename"])
    if not os.path.exists(path):
        raise IngestionError("Sample dataset is not available on this install.")

    from io import BytesIO

    with open(path, "rb") as handle:
        payload = handle.read()

    storage = FileStorage(
        stream=BytesIO(payload),
        filename=meta["filename"],
        content_type="text/csv",
    )
    return ingest_csv(storage, session_id)


def load_sample(df: pd.DataFrame, limit: int = 5) -> list:
    """Return a small JSON-serializable sample of rows for prompt context."""
    sample = df.head(limit).copy()
    for col in sample.columns:
        if pd.api.types.is_datetime64_any_dtype(sample[col]):
            sample[col] = sample[col].astype(str)
    return sample.where(pd.notnull(sample), None).to_dict(orient="records")
