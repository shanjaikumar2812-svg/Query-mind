"""Lightweight NLP preprocessing: intent detection and column-entity matching.

This runs before the Groq call so we can (a) give the AI service a strong
hint about what the user wants, and (b) pick a sensible default chart type
without waiting on the LLM.
"""

import re

import nltk

from app.utils.logger import get_logger

logger = get_logger(__name__)

_NLTK_READY = False


def ensure_nltk_data() -> None:
    """Download required NLTK corpora once, quietly, on first use."""
    global _NLTK_READY
    if _NLTK_READY:
        return
    for pkg, path in (("punkt", "tokenizers/punkt"), ("punkt_tab", "tokenizers/punkt_tab")):
        try:
            nltk.data.find(path)
        except (LookupError, OSError):
            try:
                nltk.download(pkg, quiet=True)
            except Exception as exc:  # network may be unavailable in sandboxed envs
                logger.warning("Could not download NLTK package %s: %s", pkg, exc)
    _NLTK_READY = True


INTENT_KEYWORDS = {
    "forecast": ("forecast", "predict", "projection", "next month", "next year", "future", "upcoming"),
    "trend": ("trend", "over time", "growth", "change", "by month", "by year", "by day", "timeline"),
    "aggregate": ("total", "sum", "average", "avg", "count", "how many", "maximum", "minimum", "mean"),
    "comparison": ("compare", "versus", "vs", "difference between", "higher than", "lower than"),
    "ranking": ("top", "bottom", "highest", "lowest", "best", "worst", "rank"),
    "filter": ("where", "only", "show me", "filter", "which", "list"),
}

CHART_HINTS = {
    "forecast": "line",
    "trend": "line",
    "aggregate": "bar",
    "comparison": "bar",
    "ranking": "bar",
    "filter": "table",
}


def detect_intent(question: str) -> str:
    """Return the best-guess intent label for a natural-language question."""
    q = question.lower()
    scores = {intent: 0 for intent in INTENT_KEYWORDS}
    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                scores[intent] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def suggest_chart_type(intent: str, result_columns: list = None) -> str:
    """Pick a default chart type based on intent, refined by result shape."""
    if result_columns is not None:
        if len(result_columns) == 1:
            return "table"
        if len(result_columns) == 2:
            return CHART_HINTS.get(intent, "bar")
    return CHART_HINTS.get(intent, "table")


def extract_mentioned_columns(question: str, available_columns: list) -> list:
    """Return dataset columns that appear to be referenced in the question."""
    ensure_nltk_data()
    try:
        tokens = set(nltk.word_tokenize(question.lower()))
    except Exception:
        tokens = set(re.findall(r"[a-z0-9_]+", question.lower()))

    matched = []
    for col in available_columns:
        col_l = col.lower()
        col_words = set(re.split(r"[_\s]+", col_l))
        if col_l in question.lower() or col_words & tokens:
            matched.append(col)
    return matched


def preprocess_question(question: str, available_columns: list) -> dict:
    """Bundle intent + column hints for the AI service prompt."""
    intent = detect_intent(question)
    mentioned = extract_mentioned_columns(question, available_columns)
    return {
        "intent": intent,
        "mentioned_columns": mentioned,
        "suggested_chart": suggest_chart_type(intent),
    }
