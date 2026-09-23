# QueryMind — API Reference

All responses are JSON unless noted. A session cookie (`qm_session_id`) is
set automatically on first visit; no login is required.

## Main

### `GET /`
Renders the upload page, or redirects to `/dashboard` if the session
already has datasets.

### `POST /upload`
Multipart form upload. Field name: `file` (must be `.csv`, ≤ 50MB).

**Response `201`**
```json
{
  "dataset": { "id": "ds_...", "filename": "...", "row_count": 120, "columns": [...] },
  "redirect": "/workspace/ds_..."
}
```

### `GET /dashboard`
Renders the dataset list for the current session.

### `GET /workspace/<dataset_id>`
Renders the interactive analysis workspace for one dataset.

### `DELETE /api/datasets/<dataset_id>`
Deletes a dataset's metadata row and its backing SQLite file.

---

## Query

### `POST /query/ask`
```json
{ "dataset_id": "ds_...", "question": "What are total sales by region?" }
```

**Response `200` (success) / `422` (failed after retries)**
```json
{
  "history_id": "hist_...",
  "success": true,
  "sql": "SELECT region, SUM(sales) ...",
  "columns": ["region", "sales"],
  "results": [{"region": "North", "sales": 1200}],
  "row_count": 4,
  "chart_type": "bar",
  "intent": "aggregate",
  "summary": "Sales are highest in the North region...",
  "retries": 0,
  "error": null
}
```

### `GET /query/history/<dataset_id>`
Returns up to the 50 most recent questions asked against a dataset.

---

## Analytics

### `GET /analytics/profile/<dataset_id>`
Row/column counts, dtypes, missing-value stats, numeric summary stats.

### `GET /analytics/correlation/<dataset_id>`
Pearson correlation matrix for numeric columns.

### `POST /analytics/forecast`
```json
{ "dataset_id": "ds_...", "date_column": "sale_date", "value_column": "revenue", "horizon": 12 }
```
Returns `history_dates/values` and `forecast_dates/values`, plus
`method`: `"arima"` or `"rule_based"`.

### `POST /analytics/outliers`
```json
{ "dataset_id": "ds_...", "column": "revenue" }
```
Returns z-score-based outlier count and row indices.

---

## Export

All export routes re-run the stored, validated SQL for a given
`history_id` (from `/query/ask`) before generating the file.

- `GET /export/csv/<history_id>` → `.csv` download
- `GET /export/excel/<history_id>` → `.xlsx` download
- `GET /export/pdf/<history_id>` → `.pdf` download

---

## Error format

Non-2xx responses follow:
```json
{ "error": "Human-readable message." }
```
