# QueryMind

Upload a CSV file, pose your question in simple English, and receive a genuine answer in the form of an actual SQL query executed on your data, together with a chart and a brief summary.

I created this as the capstone project for my final year on the B.Sc. Data Science & Analytics course. The problem I was attempting to solve is a rather common one: those who need answers from a spreadsheet usually don't know SQL, and it's not realistic to just learn SQL when someone is looking at a CSV five minutes before a meeting. That's why QueryMind allows you to simply ask.

The more difficult issue behind this one — in fact, the part I actually spent most of my time on — is that it's not sufficient simply to give an LLM a database connection and then hope for the best. Therefore, a major portion of this project concerns what takes place *between* the AI producing a query and that query actually reaching your data.

## What it does

1. You upload a CSV file.
2. You then pose a question—for example, 'average revenue by region' or 'the top 5 products by sales in 2024'—something you would normally do when using Excel.
3. The app carries out a lightweight natural language processing check in order to get an idea of what you're asking, and then passes that together with your schema to Gemini so that it can generate the SQL.
4. The SQL will be validated by a strict validator and executed via a **read-only** database connection before any result is displayed—nothing produced by the AI is blindly trusted.
5. A results table is displayed, together with a chart that has been automatically selected and a simple English summary explaining what the figures show.
If there is a problem—such as a wrong column reference or a syntax error—the app sends the precise error to Gemini and asks it to try a few times before honestly informing you that it cannot provide an answer.

## Why it's built this way

Each CSV file you upload is given its own separate SQLite database file. A generated query cannot accidentally (or maliciously) affect a different dataset since the connection is restricted to just one file on the disk.

Before a query is executed, it must first go through a validator which checks whether it starts with `SELECT`, whether it avoids a predefined list of dangerous keywords, whether it contains SQL comments (since this is a common method of slipping in additional logic when using a simple filter), whether it avoids including multiple statements, and whether it actually refers to the table it is intended to refer to. The database connection is then opened in **read-only mode** anyway, so that even if there was a mistake in the validator, there is still a second, independent barrier behind it which makes a write operation physically impossible.

I prefer to build up the safety measures rather than have the system fail whenever someone types in something unexpected into the question box.

## Project structure

```
querymind/
├── run.py                        # the entry point, since it creates and runs the Flask app
├── requirements.txt
│
├── app/
│   ├── __init__.py              # this is the app factory — it builds the Flask app and registers the blueprints
│   ├── config.py                # configuration based on the environment (for dev/prod, API keys, limits)
│   ├── extensions.py            # This file contains SQLAlchemy, CORS, and other Flask extensions
│   │
│   ├── models/                  # database models
│   │   ├── session.py            # A browser session—involveing one user and requiring no login
│   │   ├── dataset.py            # info about an uploaded CSV (schema, number of rows, database path)
│   │   └── history.py            # records every question asked, the SQL statement generated, and the result
│   │
│   ├── routes/                  # thin Flask blueprints — parse the request, call a service, return JSON
│   │   ├── main.py               # handles upload, shows dataset list, and dashboard pages
│   │   ├── query.py              # the endpoint for asking questions and receiving answers
│   │   ├── analytics.py           # contains the profiling, correlation, and forecasting endpoints
│   │   └── export.py              # Endpoints for exporting to CSV, Excel, or PDF
│   │
│   ├── services/                 # where the actual logic lives
│   │   ├── ingestion_service.py    # For cleaning CSV files, determining the types, and loading them into SQLite
│   │   ├── nlp_service.py           # for intent detection and column matching (NLTK)
│   │   ├── ai_service.py            # builds prompts and calls Gemini (makes SQL and summaries)
│   │   ├── sql_service.py           # the request is made then the generation takes place followed by validation and execution with a retry procedure
│   │   ├── analytics_service.py     # for dataset profiling, correlations, and ARIMA/rule-based forecasting
│   │   └── export_service.py        # it re-runs a saved query and produces a CSV/Excel/PDF from it
│   │
│   ├── utils/
│   │   ├── security.py              # the validator for the SQL allowlist
│   │   ├── helpers.py              # some shared utilities
│   │   └── logger.py                 # sets up rotating file logging
│   │
│   ├── static/                   # CSS and vanilla JS for the frontend
│   │   ├── css/
│   │   └── js/                    # api.js, app.js, charts.js, utils.js
│   │
│   └── templates/                # Jinja2 HTML templates
│       ├── base.html
│       ├── pages/                 # upload, workspace, dashboard, export views
│       └── partials/               # reusable components (navbar, query panel, chart card)
│
├── data/
│   ├── master.db                  # sessions, dataset details, query history
│   └── databases/                 # one isolated SQLite file per uploaded dataset
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API_REFERENCE.md
│   └── USER_GUIDE.md
│
└── tests/                        # pytest suite covering ingestion, NLP, SQL validation, analytics
```

A pattern that is worth observing is this: **the routes remain simple while the services maintain the logic.** The role of a route is merely to parse the incoming request and then invoke a service function—它 does not include any business logic of its own. This ensures that the same ingestion or query logic is not duplicated across three endpoints which happen to require it.

## How a question actually gets answered, end to end

```
User types a question
        │
        ▼
routes/query.py loads the dataset schema and three sample rows.
        │
        ▼
nlp_service.py. Cheap keyword pass. Detects intent (aggregate,
                  Which columns are referred to and which ones are part of the trend (or ranking)...
        │
        ▼
The ai_service.py file creates a prompt by combining the schema, some sample rows, and NLP hints.
                 + question) and sends it to Gemini
        │
        ▼
The SQL returned is validated by security.py: it must be SELECT-only and not destructive.
               keywords, no comments, no stacked statements, must
               reference the right table
        │
        ├── fails validation ──► error + bad SQL fed back to Gemini,
        │                        which gets another attempt (up to 3)
        │
        ▼ passes
The script sql_service.py opens a READ-ONLY SQLite connection and executes
        │
        ▼
Results come back → nlp_service picks a chart type based on the
                     actual result shape → ai_service writes a
                     plain-English summary of the results
        │
        ▼
Everything is logged to QueryHistory, and the answer is returned
```

## Under the hood

- **Ingestion** — the CSV files are encoded by detecting the encoding (since not all of them use UTF-8), have any empty rows or columns removed, their column names are sanitised to become valid SQL identifiers, and the types are inferred (as numeric, date, or text) before being loaded into a new SQLite table.
- **NLP** takes the question and breaks it down into tokens using NLTK, then compares it with the intent keywords and the actual column names in the dataset. It is deliberately kept simple since its sole function is to provide the large language model with a head start, not to carry out the heavy semantic processing itself.
– Forecasting begins with the use of ARIMA, but only if there is sufficient historical data for it to converge; if there isn't enough data, it resorts to a simple trend-plus-moving-average estimate instead of giving an error to the user.
- **Exports** – When carrying out CSV, Excel, or PDF exports, the system re-executes the *original, already-validated* query which was retrieved from the audit log, rather than relying on the data that the client says it has. This prevents someone from being able to submit fake 'results' and have them converted into a nicely formatted PDF.

## Tech stack

Flask, SQLAlchemy, SQLite, Google Gemini API, pandas, statsmodels, NLTK, Chart.js

## Running it locally

```bash
git clone <your-repo-url>
cd querymind
python -m venv .venv
Activate source .venv/bin/activate    # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Set your Groq API key:

```bash
export GROQ_API_KEY=your_key_here
```

Run it:

```bash
python run.py
```

The app is accessible via http://localhost:5000.

## Running the tests

```bash
pytest
```

The suite includes coverage of the edge cases associated with CSV ingestion, NLP intent detection, the behaviour of the SQL validator (such as the patterns intended for injection), and the forecasting fallback logic.

## What I'd build next

- **Multi-table joins.** At present, each dataset is isolated from the others; the obvious next move would be to allow someone to upload two related CSV files and then ask a question that refers to both of them.
– Improved understanding of questions. At present, the NLP layer relies on keywords. A system that can parse sentence structure would be able to identify things such as date ranges or numeric thresholds ("revenue over 50,000") without having to entirely depend on the LLM to work them out.
– True authentication. At the moment authentication is based on cookies, which is suitable for a demo but not something I would want to deploy if anyone were storing real data.

## About this project

I carried out the project by myself as a capstone project during my final year. Should you be looking at this as part of a recruitment process, I'll be happy to go into more detail about any aspect of it—the security validation and the retry loop are the two sections I would most like to discuss.
