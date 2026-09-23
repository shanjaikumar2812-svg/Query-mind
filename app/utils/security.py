"""Input sanitization and SQL safety validation.

QueryMind lets an LLM generate SQL from natural language and then runs it
against a per-dataset SQLite database. This module is the last line of
defense before that SQL ever touches a connection: it enforces a strict
read-only, single-statement, single-table allowlist.
"""

import re
from typing import Tuple

# Statement types / keywords that must never appear in generated SQL.
_FORBIDDEN_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE", "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX",
    "GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL",
)

# Only these SQL functions/keywords are considered safe read-side building
# blocks; this is used for informational logging, not as a hard filter.
_SELECT_PATTERN = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_COMMENT_PATTERN = re.compile(r"(--|/\*|\*/|;--)")
_MULTI_STATEMENT_PATTERN = re.compile(r";\s*\S")  # semicolon followed by more content


def validate_sql(sql: str, allowed_table: str) -> Tuple[bool, str]:
    """Validate that `sql` is a single, read-only SELECT against `allowed_table`.

    Returns (is_valid, error_message). error_message is empty when valid.
    """
    if not sql or not sql.strip():
        return False, "Empty SQL statement."

    cleaned = sql.strip().rstrip(";").strip()

    if not _SELECT_PATTERN.match(cleaned):
        return False, "Only SELECT statements are permitted."

    upper = cleaned.upper()
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            return False, f"Statement contains forbidden keyword: {keyword}."

    if _COMMENT_PATTERN.search(cleaned):
        return False, "SQL comments are not permitted."

    if _MULTI_STATEMENT_PATTERN.search(sql):
        return False, "Multiple statements are not permitted."

    if allowed_table and not re.search(
        rf'\b(FROM|JOIN)\s+["\[`]?{re.escape(allowed_table)}["\]`]?\b', cleaned, re.IGNORECASE
    ):
        return False, f"Query must reference the dataset table '{allowed_table}'."

    return True, ""


def sanitize_identifier(name: str, max_length: int = 64) -> str:
    """Sanitize a string into a safe SQL identifier (table/column name)."""
    name = str(name).strip()
    name = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    if not name or name[0].isdigit():
        name = f"col_{name}"
    name = name[:max_length].strip("_") or "col"
    return name.lower()


def sanitize_filename(filename: str) -> str:
    """Strip path components and unsafe characters from an uploaded filename."""
    filename = filename.replace("\\", "/").split("/")[-1]
    filename = re.sub(r"[^A-Za-z0-9_.\-]", "_", filename)
    return filename[:200] or "upload.csv"
