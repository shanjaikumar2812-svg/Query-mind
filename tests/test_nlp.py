"""Tests for app.services.nlp_service."""

from app.services.nlp_service import (
    detect_intent,
    extract_mentioned_columns,
    preprocess_question,
    suggest_chart_type,
)


def test_detect_intent_forecast():
    assert detect_intent("Can you forecast sales for next month?") == "forecast"


def test_detect_intent_aggregate():
    assert detect_intent("What is the total revenue?") == "aggregate"


def test_detect_intent_ranking():
    assert detect_intent("Show me the top 5 products") == "ranking"


def test_detect_intent_general_fallback():
    assert detect_intent("blah blah nonsense") == "general"


def test_suggest_chart_type_single_column_is_table():
    assert suggest_chart_type("aggregate", result_columns=["total"]) == "table"


def test_suggest_chart_type_two_columns_uses_intent_hint():
    assert suggest_chart_type("trend", result_columns=["month", "sales"]) == "line"


def test_extract_mentioned_columns_matches_direct_reference():
    columns = ["product_name", "units_sold", "sale_date"]
    result = extract_mentioned_columns("How many units_sold were there?", columns)
    assert "units_sold" in result


def test_preprocess_question_bundles_intent_and_columns():
    columns = ["revenue", "region"]
    result = preprocess_question("Compare revenue by region", columns)
    assert result["intent"] == "comparison"
    assert "revenue" in result["mentioned_columns"]
    assert "region" in result["mentioned_columns"]
