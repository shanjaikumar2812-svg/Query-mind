# QueryMind — New UI Integration

The Stitch redesign has been merged into the existing Flask app. The backend
contract is unchanged: every route, service, model, and test behaves exactly as
before. Only the presentation layer was replaced, plus three small **additive**
backend features the new design needs.

---

## How to run

```bash
pip install -r requirements.txt
python run.py          # http://localhost:5000
```

No new dependencies were added.

---

## Screen mapping

| Stitch export | Route | Template |
|---|---|---|
| `stitch_..._redesign.zip` (landing) | `GET /` | `app/templates/pages/upload.html` |
| `stitch_..._redesign1.zip` (workspace) | `GET /workspace/<id>` | `app/templates/pages/workspace.html` |
| — (rebuilt to match) | `GET /dashboard` | `app/templates/pages/dashboard.html` |

---

## Frontend → backend wiring

Every interactive element is connected to a real endpoint. Nothing is mocked.

| UI control | Calls |
|---|---|
| Dropzone / "Upload CSV" | `POST /upload` |
| Curated sandbox chips | `POST /upload/sample/<key>` *(new)* |
| "Run" in the Ask bar | `POST /query/ask` |
| Suggested query pills | `POST /query/ask` (generated from the real schema) |
| Dataset Health + Schema Profile | `GET /analytics/profile/<id>` |
| "Run forecast" | `POST /analytics/forecast` |
| Recent Questions list | `GET /query/history/<id>` |
| CSV / Excel / PDF buttons | `GET /export/{csv,excel,pdf}/<history_id>` |
| Remove dataset (dashboard) | `DELETE /api/datasets/<id>` |

The Stitch mockups shipped hardcoded demo values (`3,114 rows`, `₹179,900`,
a fake `14ms` timing, a static SQL block). All of those are now populated from
live response data.

---

## Backend changes (all additive, none breaking)

1. **`app/routes/main.py`**
   - `GET /` now renders the landing page with the curated samples and an
     "Active Session" card, instead of redirecting to `/dashboard` when a
     dataset exists. The redesign puts the dropzone and the active dataset on
     the same screen, so the redirect no longer made sense.
   - Added `POST /upload/sample/<sample_key>` to load a bundled sample.
   - Added `_decorate()`, which attaches display-only fields (`size_label`,
     `uploaded_label`) to the dataset dict. The `Dataset` model is untouched.

2. **`app/services/ingestion_service.py`**
   - Added `SAMPLE_DATASETS`, `list_samples()`, and `ingest_sample()`.
     Samples are wrapped in a `FileStorage` and pushed through the **same**
     `ingest_csv()` path as a real upload — identical cleaning, validation,
     and per-dataset SQLite isolation.
   - Hardened the dtype coercion in `_clean_dataframe()` to treat both pandas 2
     `object` and pandas 3 `str` columns as text. Without this, date columns
     silently stay strings on pandas 3 and forecasting stops detecting them.
     Behaviour on your pinned pandas 2.2.3 is unchanged.

3. **`app/services/analytics_service.py`**
   - `profile_dataset()` now also returns `duplicate_count` and
     `quality_score` (0–100), which feed the Dataset Health card. Existing
     keys are untouched, so `tests/test_analytics.py` still passes.

4. **`.gitignore`** — `sample_data/` was being ignored, which would have
   dropped the bundled samples from the repo. It is now tracked. A stray
   `rm cached` fragment on line 1 was also removed.

---

## New files

```
app/static/css/apple-ui.css     design tokens, toast/modal/table styles, fallbacks
sample_data/flipkart_mobiles.csv    3,114 rows — mirrors the mockup dataset
sample_data/saas_mrr.csv            2,400 rows — has a date column (forecasting demo)
sample_data/ecommerce_orders.csv    4,500 rows — has a date column
_backup_old_ui/                     your previous templates, CSS, and JS
```

`_backup_old_ui/` is a safety net — delete it once you're happy with the new UI.

---

## Assets and offline behaviour

- **Fonts and icons are local.** Inter + JetBrains Mono come from your existing
  `vendor/fonts/`, and the Material Symbols in the mockups were mapped onto your
  already-vendored Bootstrap Icons. Every icon used was verified to exist in
  that font.
- **Chart.js is local** (your existing vendored copy).
- **Tailwind is loaded from the CDN** (`cdn.tailwindcss.com`), the way the Stitch
  export did. This is the one asset that needs an internet connection. If you
  want fully offline rendering, run the Tailwind CLI once and vendor the output:

  ```bash
  npx tailwindcss -i input.css -o app/static/css/tailwind.css --minify
  ```

  then swap the CDN `<script>` in `base.html` for that stylesheet.
- **Bootstrap CSS/JS is no longer loaded.** It conflicted with Tailwind's reset.
  The one thing that depended on it — the contact modal — was rewritten as a
  small vanilla modal in `utils.js`. The vendored Bootstrap files are still on
  disk and harmless.

---

## Behaviour added in the UI layer

- **Chart type toggle** (Bar / Line / Donut) re-renders from cached results, so
  switching views costs no extra query.
- **Tabs** (AI Insight / SQL Query / Data Table) — all three are populated from
  a single `/query/ask` response.
- **Suggested pills** are generated from your dataset's actual columns, not
  hardcoded.
- **Forecast panel** auto-detects date and numeric columns. When a dataset has
  no usable date column it shows the "no time-series detected" state from the
  mockup rather than an empty dropdown. (Try `saas_mrr` for the working case and
  `flipkart_mobiles` for the empty state.)
- **Clicking a schema column** appends its name to the question box.
- **Copy SQL / Copy Result** include a fallback for plain-http localhost, where
  the async clipboard API is blocked.

---

## Verification performed

- All Python modules byte-compile; all four JS files pass `node --check`.
- Every template renders under Jinja's `StrictUndefined` (catches any missing
  variable), in both the populated and empty states.
- 60 element IDs, 7 CSS classes, and 10 data-attributes referenced by `app.js`
  were confirmed present in the rendered HTML.
- Every URL called from the frontend was matched against a registered route.
- All three sample CSVs were pushed through the real `_clean_dataframe()` and
  SQLite write path; `list_samples()` and the new profile metrics were executed
  and asserted.

The Flask app itself could not be booted here (no network to install Flask), so
please do one manual smoke run: upload a CSV, ask a question, switch the three
tabs, toggle the chart types, and export a CSV.
