"""Unit tests for evaluation scorers."""

import pytest
import asyncio

from app.eval.scorers import (
    Scorer,
    TaskCompletionScorer,
    ToolSelectionAccuracyScorer,
    AnswerCorrectnessScorer,
    JSONValidityScorer,
    ToolCallAccuracyScorer,
    get_scorer,
    list_scorers,
    register_scorer,
)


def test_scorer_base_is_abstract():
    """Scorer cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Scorer()


def test_list_scorers():
    """Built-in scorers are registered."""
    scorers = list_scorers()
    assert "task_completion" in scorers
    assert "tool_selection_accuracy" in scorers
    assert "answer_correctness" in scorers
    assert "json_validity" in scorers
    assert "tool_call_accuracy" in scorers


def test_get_scorer():
    """get_scorer returns the correct class."""
    assert get_scorer("task_completion") is TaskCompletionScorer
    assert get_scorer("answer_correctness") is AnswerCorrectnessScorer


def test_get_scorer_unknown():
    with pytest.raises(KeyError, match="Unknown scorer"):
        get_scorer("nonexistent-scorer")


def test_register_scorer():
    class MyScorer(Scorer):
        @property
        def name(self) -> str:
            return "my-scorer"

        async def score(self, **kwargs):
            return {"score": 1.0, "score_unit": "percent", "details": {}}

    register_scorer("my-scorer", MyScorer)
    assert get_scorer("my-scorer") is MyScorer


@pytest.mark.asyncio
async def test_task_completion_exact_match():
    scorer = TaskCompletionScorer()
    result = await scorer.score(
        response="The capital of France is Paris.",
        expected="The capital of France is Paris.",
    )
    assert result["score"] == 1.0


@pytest.mark.asyncio
async def test_task_completion_contains():
    scorer = TaskCompletionScorer()
    result = await scorer.score(
        response="The capital of France is Paris, a beautiful city.",
        expected="Paris",
    )
    assert result["score"] == 0.8


@pytest.mark.asyncio
async def test_task_completion_keywords():
    scorer = TaskCompletionScorer()
    result = await scorer.score(
        response="Python is a great programming language for data science.",
        expected=None,
        context={"expected_keywords": ["python", "data", "science"]},
    )
    assert result["score"] == 1.0


@pytest.mark.asyncio
async def test_task_completion_empty():
    scorer = TaskCompletionScorer()
    result = await scorer.score(response="", expected=None)
    assert result["score"] == 0.0


@pytest.mark.asyncio
async def test_answer_correctness_exact():
    scorer = AnswerCorrectnessScorer()
    result = await scorer.score(
        response="42",
        expected="42",
    )
    assert result["score"] == 1.0


@pytest.mark.asyncio
async def test_answer_correctness_keyword_overlap():
    scorer = AnswerCorrectnessScorer()
    result = await scorer.score(
        response="The quick brown fox jumps over the lazy dog.",
        expected="quick brown fox",
    )
    assert result["score"] > 0.0


@pytest.mark.asyncio
async def test_answer_correctness_no_expected():
    scorer = AnswerCorrectnessScorer()
    result = await scorer.score(response="some answer")
    assert result["score"] == 0.0


@pytest.mark.asyncio
async def test_json_validity_valid():
    scorer = JSONValidityScorer()
    result = await scorer.score(response='{"key": "value"}')
    assert result["score"] == 1.0
    assert result["details"]["is_valid_json"] is True


@pytest.mark.asyncio
async def test_json_validity_invalid():
    scorer = JSONValidityScorer()
    result = await scorer.score(response="not json at all")
    assert result["score"] == 0.0
    assert result["details"]["is_valid_json"] is False


@pytest.mark.asyncio
async def test_tool_selection_accuracy():
    scorer = ToolSelectionAccuracyScorer()
    result = await scorer.score(
        response="I will use the calculator and search tools to help you.",
        expected=None,
        context={
            "expected_tools": [
                {"name": "calculator"},
                {"name": "search"},
                {"name": "weather"},
            ]
        },
    )
    assert result["score"] == 2 / 3  # 2 out of 3 tools found


@pytest.mark.asyncio
async def test_tool_call_accuracy():
    scorer = ToolCallAccuracyScorer()
    result = await scorer.score(
        response="I'm calling calculator with arguments x=5, y=10",
        expected=None,
        context={
            "expected_tool_calls": [
                {"name": "calculator", "arguments": {"x": 5, "y": 10}},
            ]
        },
    )
    assert result["score"] == 1.0


@pytest.mark.asyncio
async def test_json_validity_nested():
    scorer = JSONValidityScorer()
    result = await scorer.score(
        response='{"name": "test", "items": [1, 2, 3], "nested": {"a": true}}'
    )
    assert result["score"] == 1.0
    assert result["details"]["parsed_type"] == "dict"
