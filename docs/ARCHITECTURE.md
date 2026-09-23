# QueryMind — Architecture

## Overview

QueryMind is a Flask application that lets a user upload any CSV, ask
questions about it in plain English, and get back SQL, tabular results,
charts, forecasts, and downloadable reports.

```
Browser (Jinja2 + Chart.js)
        │
        ▼
Flask app factory (app/__init__.py)
        │
        ├── routes/        HTTP layer — thin, delegates to services
        ├── services/       business logic
        ├── models/         SQLAlchemy ORM (master metadata DB)
        └── utils/          logging, security, helpers
```

## Data model

Two tiers of storage:

1. **Master DB** (`data/master.db`, SQLite via SQLAlchemy) — holds
   `sessions`, `datasets` (metadata only), and `query_history`.
2. **Per-dataset DBs** (`data/databases/<dataset_id>.db`) — each uploaded
   CSV is materialized as a single table (`tbl_<dataset_id>`) inside its
   own SQLite file. This keeps datasets isolated: dropping a dataset is a
   single file delete, and a generated query can never accidentally touch
   another dataset's data because the connection itself is scoped to one
   file.

## Request flow: asking a question

1. `POST /query/ask {dataset_id, question}` (`routes/query.py`)
2. `nlp_service.preprocess_question` — NLTK tokenization + keyword
   matching to guess intent (`aggregate`, `trend`, `forecast`, `ranking`,
   `comparison`, `filter`, `general`) and which columns are likely
   referenced.
3. `sql_service.ask_and_run`:
   - `ai_service.generate_sql` — prompts Gemini with the table schema,
     a few sample rows, and the NLP hints; expects back a single SQLite
     `SELECT` statement.
   - `utils.security.validate_sql` — hard allowlist: only `SELECT`,
     single statement, no DDL/DML keywords, must reference the dataset's
     own table.
   - `sql_service.execute_sql` — opens the per-dataset SQLite file in
     **read-only URI mode** (`file:...?mode=ro`) as defense-in-depth
     beneath the keyword blocklist, then executes.
   - **Self-healing loop**: if validation or execution fails, the error
     is fed back into another Gemini call (up to `AI_MAX_RETRIES`) so the
     model can correct its own SQL.
4. `ai_service.summarize_result` — a short plain-English summary of the
   result set.
5. The question, SQL, outcome, and retry count are logged to
   `query_history` for audit and for re-running on export.

## Forecasting

`analytics_service.forecast_series` tries `statsmodels` ARIMA(1,1,1)
first. If the series is too short or ARIMA fails to converge, it falls
back to a blended linear-trend + moving-average model
(`_rule_based_forecast`) so the user always gets a usable forecast
instead of an error.

## Exports

Exports are keyed off a `query_history` row, not off client-supplied
data: `export.py` re-runs the stored, already-validated SQL against the
dataset before generating CSV / Excel / PDF. This guarantees the export
always reflects real, validated query results. PDF generation tries
WeasyPrint first and falls back to `pdfkit` (wkhtmltopdf) if WeasyPrint's
native system libraries aren't available in the deployment environment.

## Security notes

- SQL is never trusted from the LLM or the client — `validate_sql` is the
  single choke point every generated query passes through.
- Per-dataset SQLite connections are opened read-only.
- Uploaded filenames are sanitized (`sanitize_filename`) before use.
- Column names are sanitized into safe SQL identifiers at ingestion time,
  so no user-supplied header ever reaches a `CREATE TABLE`/`to_sql` call
  unescaped.
