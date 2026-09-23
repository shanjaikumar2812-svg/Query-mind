"""Miscellaneous helper utilities shared across services and routes."""

import uuid
from datetime import datetime


def new_id(prefix: str = "") -> str:
    """Generate a short unique identifier, optionally prefixed."""
    token = uuid.uuid4().hex[:12]
    return f"{prefix}{token}" if prefix else token


def format_file_size(num_bytes: int) -> str:
    """Human-readable file size, e.g. 1536 -> '1.5 KB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def now_iso() -> str:
    """Current UTC timestamp in ISO 8601 format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def rows_to_dicts(columns, rows):
    """Convert (columns, rows) query results into a list of dicts."""
    return [dict(zip(columns, row)) for row in rows]


def safe_float(value, default=0.0):
    """Best-effort float conversion, guarding against NaN/None/str garbage."""
    try:
        result = float(value)
        if result != result:  # NaN check without importing math
            return default
        return result
    except (TypeError, ValueError):
        return default
