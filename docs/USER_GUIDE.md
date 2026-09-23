# QueryMind — User Guide

## What the frontend actually is

There's no separate frontend app (no React/Vue build step) — it's
server-rendered Jinja2 templates styled with a dark glassmorphism theme,
enhanced with vanilla JS + Chart.js for the interactive parts. That keeps
the whole thing deployable as a single Flask service.

```
app/templates/
├── base.html              shared shell: navbar, CSS/JS includes
├── partials/
│   ├── navbar.html
│   ├── health_card.html    dataset stats sidebar widget
│   ├── query_panel.html    the "ask a question" box + results
│   └── chart_card.html     <canvas> Chart.js mounts into
└── pages/
    ├── upload.html          "/"            drag-and-drop CSV upload
    ├── dashboard.html        "/dashboard"   grid of your datasets
    ├── workspace.html        "/workspace/<id>"  the main analysis screen
    └── export_report.html    (not user-facing — PDF export template)

app/static/
├── css/  main.css (layout+vars), glassmorphism.css (panel blur/glow), animations.css (spinners, fades)
└── js/   utils.js (DOM/toast helpers), api.js (fetch wrappers), charts.js (Chart.js factory), app.js (page wiring)
```

`app.js` exposes a small `window.QM` object with two entry points that
each page's `<script>` block calls: `QM.initUploadPage()` and
`QM.initWorkspacePage(datasetId)`. Everything else (`QMApi`, `QMCharts`,
`QMUtils`) is a helper library those two functions use.

## The three screens

### 1. Upload (`/`)
A glass-panel dropzone. Drag a CSV in, or click to browse. `app.js`
uploads it via `XMLHttpRequest` (so it can show a real progress bar),
hits `POST /upload`, and on success redirects the browser straight to
the new dataset's workspace.

### 2. Dashboard (`/dashboard`)
A card grid of every dataset you've uploaded in this browser session
(session is tracked via a cookie, no login). Click a card to jump into
its workspace.

### 3. Workspace (`/workspace/<dataset_id>`)
This is where the actual product lives. Two columns:

- **Left sidebar**
  - *Dataset Health* card — row/column counts, average missing-data %,
    and a scrollable list of every column with its inferred type. This
    loads from `GET /analytics/profile/<id>` on page load.
  - *Forecast* card — pick a date column and a numeric column from
    dropdowns (auto-populated from the profile response), hit **Run
    Forecast**, and a line chart renders history vs. projected future
    values.

- **Main panel**
  - *Ask QueryMind* — type a question in plain English, hit **Ask**.
    While waiting, the button shows a spinner. On response you get: a
    one-paragraph plain-English summary, a **Show SQL** toggle to reveal
    the exact generated query, an auto-picked chart (bar for
    comparisons/rankings, line for trends/forecasts, a plain table for
    single-column or list-style results), the full result table below
    the chart, and CSV / Excel / PDF export links.
  - *Recent Questions* — your last 50 questions against this dataset;
    click one to refill the input box.

## What happens when you click "Ask" — end to end

1. `app.js` posts `{dataset_id, question}` to `POST /query/ask`.
2. The Flask route (`routes/query.py`) runs the question through
   `nlp_service.preprocess_question` — cheap keyword/NLTK matching that
   guesses an *intent* (aggregate / trend / forecast / ranking /
   comparison / filter) and flags which of the dataset's columns are
   probably being referenced.
3. `sql_service.ask_and_run` calls `ai_service.generate_sql`, which sends
   Gemini the table schema, a few sample rows, and those hints, and asks
   for one `SELECT` statement back.
4. `utils.security.validate_sql` is a hard gate every generated query
   must pass: SELECT-only, single statement, no DDL/DML keywords, must
   reference the dataset's own table. It then runs against the
   dataset's private SQLite file opened in **read-only** mode.
5. **If it fails validation or execution**, the error message is fed
   back into another Gemini call (up to 3 attempts) so the model
   self-corrects — you never see this happen, you just occasionally
   wait a beat longer for a harder question.
6. On success, `ai_service.summarize_result` asks Gemini for a 2–3
   sentence plain-English summary, `nlp_service.suggest_chart_type`
   picks the chart, and everything is logged to `query_history`
   (this is what powers Recent Questions *and* what exports re-run
   later, so exports always reflect a real, validated query).
7. The JSON response comes back and `app.js` renders the summary,
   SQL block, Chart.js chart, and result table.

## Forecasting

`analytics_service.forecast_series` tries ARIMA(1,1,1) via `statsmodels`
first. If there isn't enough data (fewer than 8 points) or the model
fails to converge, it silently falls back to a blended linear-trend +
moving-average forecast — so **Run Forecast** always returns something
usable instead of an error. The forecast response tells you which
method was used (`arima` or `rule_based`).

## Exports

Export links don't send your current on-screen data back to the server —
they hit `GET /export/{csv,excel,pdf}/<history_id>`, which looks up that
question's saved SQL and **re-runs it fresh** against the dataset before
generating the file. This guarantees an export can never drift from a
real, security-validated query result. PDF generation tries WeasyPrint
first and falls back to `pdfkit`/wkhtmltopdf automatically if
WeasyPrint's native system libraries aren't installed in your deployment
environment.

## Running it locally

```bash
cp .env.example .env        # then fill in GEMINI_API_KEY
pip install -r requirements.txt --break-system-packages
python run.py                # http://localhost:5000
```

Upload a CSV on the home page, get redirected into its workspace, and
start asking questions.
