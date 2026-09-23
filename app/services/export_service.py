"""Generate downloadable CSV, Excel, and PDF files from query results."""

import os

import pandas as pd
from flask import current_app, render_template

from app.utils.helpers import new_id
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _export_path(extension: str) -> str:
    export_dir = current_app.config["EXPORT_DIR"]
    os.makedirs(export_dir, exist_ok=True)
    filename = f"export_{new_id()}.{extension}"
    return os.path.join(export_dir, filename)


def export_csv(columns: list, rows: list) -> str:
    """Write results to a CSV file and return its path."""
    df = pd.DataFrame(rows, columns=columns)
    path = _export_path("csv")
    df.to_csv(path, index=False)
    return path


def export_excel(columns: list, rows: list, sheet_name: str = "Results") -> str:
    """Write results to an .xlsx file and return its path."""
    df = pd.DataFrame(rows, columns=columns)
    path = _export_path("xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return path


def export_pdf(title: str, question: str, sql: str, columns: list, rows: list, summary: str = "") -> str:
    """Render an HTML report and convert it to PDF. Tries WeasyPrint first,
    falls back to pdfkit (wkhtmltopdf) if WeasyPrint's native deps are missing.
    """
    html = render_template(
        "pages/export_report.html",
        title=title,
        question=question,
        sql=sql,
        columns=columns,
        rows=rows[:500],
        summary=summary,
        total_rows=len(rows),
    )
    path = _export_path("pdf")

    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(path)
        return path
    except Exception as exc:
        logger.warning("WeasyPrint failed (%s), falling back to pdfkit.", exc)

    try:
        import pdfkit
        pdfkit.from_string(html, path)
        return path
    except Exception as exc:
        logger.error("pdfkit fallback also failed: %s", exc)
        raise RuntimeError(
            "PDF export failed. Ensure WeasyPrint's system libraries or "
            "wkhtmltopdf are installed."
        ) from exc
