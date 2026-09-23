"""Tests for app.services.analytics_service."""

import sqlite3

import pandas as pd
import pytest

from app.services.analytics_service import (
    correlation_matrix,
    detect_outliers,
    forecast_series,
    profile_dataset,
)


@pytest.fixture()
def sample_db(tmp_path):
    db_path = str(tmp_path / "sample.db")
    conn = sqlite3.connect(db_path)

    dates = pd.date_range("2024-01-01", periods=14, freq="D")
    df = pd.DataFrame({
        "sale_date": dates.astype(str),
        "revenue": [100, 102, 98, 250, 105, 108, 110, 112, 300, 115, 118, 120, 122, 125],
        "units": [10, 12, 9, 25, 11, 13, 14, 15, 30, 16, 17, 18, 19, 20],
    })
    df.to_sql("tbl_test", conn, index=False, if_exists="replace")
    conn.close()
    return db_path


def test_profile_dataset_returns_row_and_column_counts(sample_db, app):
    with app.app_context():
        profile = profile_dataset(sample_db, "tbl_test")
        assert profile["row_count"] == 14
        assert profile["column_count"] == 3
        col_names = [c["name"] for c in profile["columns"]]
        assert "revenue" in col_names and "units" in col_names


def test_correlation_matrix_includes_numeric_columns(sample_db, app):
    with app.app_context():
        result = correlation_matrix(sample_db, "tbl_test")
        assert "revenue" in result["columns"]
        assert "units" in result["columns"]
        assert len(result["matrix"]) == len(result["columns"])


def test_forecast_series_uses_arima_or_rule_based(sample_db, app):
    with app.app_context():
        result = forecast_series(sample_db, "tbl_test", "sale_date", "revenue", horizon=5)
        assert result["method"] in ("arima", "rule_based")
        assert len(result["forecast_values"]) == 5
        assert len(result["forecast_dates"]) == 5


def test_forecast_series_raises_on_missing_column(sample_db, app):
    with app.app_context():
        with pytest.raises(ValueError):
            forecast_series(sample_db, "tbl_test", "not_a_column", "revenue")


def test_detect_outliers_flags_extreme_values(sample_db, app):
    with app.app_context():
        result = detect_outliers(sample_db, "tbl_test", "revenue", z_threshold=1.5)
        assert result["outlier_count"] >= 1
