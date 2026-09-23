"""Profiling, correlation analysis, and time-series forecasting.

Forecasting uses a dual-algorithm approach: statsmodels ARIMA is tried
first; if it fails (too few points, non-convergence, etc.) a simple
rule-based moving-average/linear-trend fallback kicks in so the user
always gets a forecast rather than an error.
"""

import sqlite3
import warnings

import numpy as np
import pandas as pd
from flask import current_app

from app.utils.helpers import safe_float
from app.utils.logger import get_logger

logger = get_logger(__name__)

warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")


def _read_table(db_path: str, table_name: str) -> pd.DataFrame:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return pd.read_sql_query(f'SELECT * FROM "{table_name}"', conn)
    finally:
        conn.close()


def profile_dataset(db_path: str, table_name: str) -> dict:
    """Return summary stats, dtypes, and missing-value counts for a dataset."""
    df = _read_table(db_path, table_name)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    describe = df[numeric_cols].describe().to_dict() if numeric_cols else {}

    missing = df.isna().sum()
    missing_pct = (missing / max(len(df), 1) * 100).round(2)

    # Duplicate detection can be expensive on very wide frames and throws on
    # unhashable cell values, so treat it as best-effort metadata.
    try:
        duplicate_count = int(df.duplicated().sum())
    except (TypeError, ValueError):
        duplicate_count = 0

    # A simple 0-100 health score: penalize missing cells and duplicate rows.
    avg_missing_pct = float(missing_pct.mean()) if len(df.columns) else 0.0
    duplicate_pct = (duplicate_count / max(len(df), 1)) * 100
    quality_score = round(max(0.0, 100.0 - avg_missing_pct - duplicate_pct), 1)

    profile = {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "duplicate_count": duplicate_count,
        "quality_score": quality_score,
        "columns": [
            {
                "name": col,
                "dtype": str(df[col].dtype),
                "missing_count": int(missing[col]),
                "missing_pct": safe_float(missing_pct[col]),
                "unique_count": int(df[col].nunique()),
            }
            for col in df.columns
        ],
        "numeric_summary": {
            col: {stat: safe_float(val) for stat, val in stats.items()}
            for col, stats in describe.items()
        },
    }
    return profile


def correlation_matrix(db_path: str, table_name: str) -> dict:
    """Return a Pearson correlation matrix for numeric columns."""
    df = _read_table(db_path, table_name)
    numeric = df.select_dtypes(include=[np.number])
    if numeric.shape[1] < 2:
        return {"columns": [], "matrix": []}
    corr = numeric.corr().round(3)
    return {
        "columns": corr.columns.tolist(),
        "matrix": [[safe_float(v) for v in row] for row in corr.values.tolist()],
    }


def _rule_based_forecast(series: pd.Series, horizon: int) -> list:
    """Linear-trend + moving-average fallback forecast."""
    values = series.values.astype(float)
    n = len(values)
    window = max(3, min(6, n // 2))
    recent_avg = values[-window:].mean()

    x = np.arange(n)
    slope, intercept = np.polyfit(x, values, 1) if n >= 2 else (0.0, recent_avg)

    forecast = []
    for step in range(1, horizon + 1):
        trend_value = slope * (n + step) + intercept
        blended = 0.6 * trend_value + 0.4 * recent_avg
        forecast.append(round(safe_float(blended), 4))
    return forecast


def forecast_series(db_path: str, table_name: str, date_column: str, value_column: str,
                     horizon: int = None) -> dict:
    """Forecast `value_column` over time using ARIMA, falling back to a
    rule-based trend model when ARIMA can't be fit."""
    try:
        config = current_app.config
    except RuntimeError:
        config = {}

    horizon = horizon or config.get("FORECAST_DEFAULT_HORIZON", 12)
    min_points = config.get("FORECAST_MIN_POINTS", 8)

    df = _read_table(db_path, table_name)
    if date_column not in df.columns or value_column not in df.columns:
        raise ValueError("date_column or value_column not found in dataset.")

    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
    df = df.dropna(subset=[date_column, value_column]).sort_values(date_column)
    df = df.groupby(date_column, as_index=False)[value_column].sum()

    if len(df) < 3:
        raise ValueError("Not enough data points to forecast (need at least 3).")

    series = df.set_index(date_column)[value_column].astype(float)
    history = [round(safe_float(v), 4) for v in series.values.tolist()]
    history_dates = [d.isoformat() for d in series.index.to_pydatetime()]

    method_used = "rule_based"
    forecast_values = None

    if len(series) >= min_points:
        try:
            from statsmodels.tsa.arima.model import ARIMA

            model = ARIMA(series.values, order=(1, 1, 1))
            fitted = model.fit()
            forecast_values = [round(safe_float(v), 4) for v in fitted.forecast(steps=horizon)]
            method_used = "arima"
        except Exception as exc:
            logger.warning("ARIMA failed (%s), falling back to rule-based forecast.", exc)
            forecast_values = None

    if forecast_values is None:
        forecast_values = _rule_based_forecast(series, horizon)
        method_used = "rule_based"

    inferred_freq = pd.infer_freq(series.index) or "D"
    future_dates = pd.date_range(
        start=series.index[-1], periods=horizon + 1, freq=inferred_freq
    )[1:]

    return {
        "method": method_used,
        "history_dates": history_dates,
        "history_values": history,
        "forecast_dates": [d.isoformat() for d in future_dates.to_pydatetime()],
        "forecast_values": forecast_values,
    }


def detect_outliers(db_path: str, table_name: str, column: str, z_threshold: float = 3.0) -> dict:
    """Flag rows whose z-score for `column` exceeds `z_threshold`."""
    df = _read_table(db_path, table_name)
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in dataset.")

    values = pd.to_numeric(df[column], errors="coerce")
    mean, std = values.mean(), values.std()
    if not std or std == 0:
        return {"outlier_count": 0, "outlier_indices": []}

    z_scores = (values - mean) / std
    outlier_mask = z_scores.abs() > z_threshold
    return {
        "outlier_count": int(outlier_mask.sum()),
        "outlier_indices": df.index[outlier_mask].tolist(),
        "mean": safe_float(mean),
        "std": safe_float(std),
    }
