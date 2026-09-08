"""Tests for classify_quiz_areas in memory_prompts.py."""
from types import SimpleNamespace

import pytest

from app.discussion.memory_prompts import classify_quiz_areas


def _make_quiz_result(questions):
    """Create a mock QuizResult with a questions list."""
    return SimpleNamespace(questions=questions)


class TestClassifyQuizAreas:
    """Test difficulty category classification from quiz data."""

    def test_empty_results(self):
        """No quiz results returns empty lists."""
        strong, weak = classify_quiz_areas([])
        assert strong == []
        assert weak == []

    def test_none_questions(self):
        """QuizResult with None questions is skipped."""
        result = SimpleNamespace(questions=None)
        strong, weak = classify_quiz_areas([result])
        assert strong == []
        assert weak == []

    def test_single_strong_area(self):
        """A category with 100% accuracy is strong."""
        result = _make_quiz_result([
            {"type": "recall", "correct": True},
            {"type": "recall", "correct": True},
            {"type": "recall", "correct": True},
        ])
        strong, weak = classify_quiz_areas([result])
        assert "recall" in strong
        assert weak == []

    def test_single_weak_area(self):
        """A category with 0% accuracy is weak."""
        result = _make_quiz_result([
            {"type": "analysis", "correct": False},
            {"type": "analysis", "correct": False},
            {"type": "analysis", "correct": False},
        ])
        strong, weak = classify_quiz_areas([result])
        assert strong == []
        assert "analysis" in weak

    def test_mixed_areas(self):
        """Multiple categories classified correctly."""
        result = _make_quiz_result([
            {"type": "recall", "correct": True},
            {"type": "recall", "correct": True},
            {"type": "understanding", "correct": False},
            {"type": "understanding", "correct": False},
            {"type": "understanding", "correct": False},
        ])
        strong, weak = classify_quiz_areas([result])
        assert "recall" in strong
        assert "understanding" in weak

    def test_middle_accuracy_neither_strong_nor_weak(self):
        """A category at 60% (between 50% and 70%) is neither."""
        result = _make_quiz_result([
            {"type": "connection", "correct": True},
            {"type": "connection", "correct": True},
            {"type": "connection", "correct": True},
            {"type": "connection", "correct": False},
            {"type": "connection", "correct": False},
        ])
        strong, weak = classify_quiz_areas([result])
        assert "connection" not in strong
        assert "connection" not in weak

    def test_min_questions_filter(self):
        """Categories with fewer than min_questions are ignored."""
        result = _make_quiz_result([
            {"type": "recall", "correct": True},  # Only 1 question
        ])
        strong, weak = classify_quiz_areas([result], min_questions=2)
        assert strong == []
        assert weak == []

    def test_custom_thresholds(self):
        """Custom strong and weak thresholds are respected."""
        result = _make_quiz_result([
            {"type": "recall", "correct": True},
            {"type": "recall", "correct": False},
        ])
        # 50% accuracy: with strong_threshold=50, it's strong
        strong, weak = classify_quiz_areas(
            [result], strong_threshold=50.0, weak_threshold=30.0
        )
        assert "recall" in strong

    def test_accepts_difficulty_key(self):
        """Questions using 'difficulty' instead of 'type' are handled."""
        result = _make_quiz_result([
            {"difficulty": "analysis", "correct": True},
            {"difficulty": "analysis", "correct": True},
        ])
        strong, weak = classify_quiz_areas([result])
        assert "analysis" in strong

    def test_accepts_was_correct_key(self):
        """Questions using 'was_correct' instead of 'correct' are handled."""
        result = _make_quiz_result([
            {"type": "recall", "was_correct": True},
            {"type": "recall", "was_correct": True},
        ])
        strong, weak = classify_quiz_areas([result])
        assert "recall" in strong

    def test_multiple_quiz_results(self):
        """Aggregates across multiple QuizResult objects."""
        r1 = _make_quiz_result([
            {"type": "recall", "correct": True},
            {"type": "recall", "correct": True},
        ])
        r2 = _make_quiz_result([
            {"type": "recall", "correct": False},
        ])
        # 2/3 = 66.7% => neither strong (>70) nor weak (<50)
        strong, weak = classify_quiz_areas([r1, r2])
        assert "recall" not in strong
        assert "recall" not in weak

    def test_unknown_category_skipped(self):
        """Questions with 'unknown' or missing category are ignored."""
        result = _make_quiz_result([
            {"type": "unknown", "correct": True},
            {"correct": True},
            {"type": "", "correct": True},
        ])
        strong, weak = classify_quiz_areas([result])
        assert strong == []
        assert weak == []

    def test_case_normalization(self):
        """Category names are lowered and stripped."""
        result = _make_quiz_result([
            {"type": " RECALL ", "correct": True},
            {"type": "recall", "correct": True},
        ])
        strong, weak = classify_quiz_areas([result])
        assert "recall" in strong

    def test_sorted_output(self):
        """Results are sorted alphabetically."""
        result = _make_quiz_result([
            {"type": "understanding", "correct": True},
            {"type": "understanding", "correct": True},
            {"type": "recall", "correct": True},
            {"type": "recall", "correct": True},
            {"type": "analysis", "correct": True},
            {"type": "analysis", "correct": True},
        ])
        strong, weak = classify_quiz_areas([result])
        assert strong == sorted(strong)
