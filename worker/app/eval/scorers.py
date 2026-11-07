"""Custom scoring engine for the Agenyx Evaluation Platform.

Scorers evaluate model responses against expected outcomes and produce
normalized scores (0.0 to 1.0) that are stored in the evaluation
database. Scorers are pluggable: new scorers can be registered without
modifying the evaluation pipeline.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any


class Scorer(ABC):
    """Abstract base class for evaluation scorers.

    A scorer takes a model response and expected output/context and
    produces a normalized score between 0.0 and 1.0, plus optional
    details for debugging.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique scorer identifier."""

    @abstractmethod
    async def score(
        self,
        *,
        response: str,
        expected: str | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Score a model response.

        Returns a dict:

            {
                "score": 0.85,           # 0.0 to 1.0
                "score_unit": "percent", # percent, raw, count
                "details": {...},        # scorer-specific details
            }
        """
        raise NotImplementedError


# Registry of scorer name -> scorer class
SCORER_REGISTRY: dict[str, type[Scorer]] = {}


def get_scorer(name: str) -> type[Scorer]:
    """Return the scorer class for a given name."""
    if name not in SCORER_REGISTRY:
        raise KeyError(f"Unknown scorer: {name}")
    return SCORER_REGISTRY[name]


def register_scorer(name: str, scorer_class: type[Scorer]) -> None:
    """Register a new scorer class."""
    SCORER_REGISTRY[name] = scorer_class


def list_scorers() -> list[str]:
    """Return all registered scorer names."""
    return sorted(SCORER_REGISTRY.keys())


class TaskCompletionScorer(Scorer):
    """Scores whether a model response completes the requested task.

    Uses a simple heuristic: checks if expected keywords/phrases appear
    in the response. Can be overridden with an LLM-based judge for
    more nuanced scoring.
    """

    @property
    def name(self) -> str:
        return "task_completion"

    async def score(
        self,
        *,
        response: str,
        expected: str | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        context = context or {}
        expected_keywords = context.get("expected_keywords", [])

        if expected:
            # If expected answer is provided, check for exact/partial match
            response_lower = response.lower().strip()
            expected_lower = expected.lower().strip()

            if expected_lower == response_lower:
                score = 1.0
            elif expected_lower in response_lower:
                score = 0.8
            else:
                # Check keyword overlap
                expected_words = set(expected_lower.split())
                response_words = set(response_lower.split())
                if expected_words:
                    overlap = len(expected_words & response_words) / len(expected_words)
                    score = min(overlap, 0.7)
                else:
                    score = 0.5
        elif expected_keywords:
            response_lower = response.lower()
            found = sum(
                1 for kw in expected_keywords if kw.lower() in response_lower
            )
            score = found / len(expected_keywords) if expected_keywords else 0.0
        else:
            # No expected output: score based on response non-empty
            score = 0.5 if response.strip() else 0.0

        score = max(0.0, min(1.0, score))

        return {
            "score": score,
            "score_unit": "percent",
            "details": {
                "response_length": len(response),
                "expected_provided": expected is not None,
                "keywords_checked": len(expected_keywords) if expected_keywords else 0,
            },
        }


class ToolSelectionAccuracyScorer(Scorer):
    """Scores whether the model selected the correct tools."""

    @property
    def name(self) -> str:
        return "tool_selection_accuracy"

    async def score(
        self,
        *,
        response: str,
        expected: str | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        context = context or {}
        expected_tools = context.get("expected_tools", [])

        if not expected_tools:
            return {
                "score": 0.0,
                "score_unit": "percent",
                "details": {"reason": "no expected tools provided"},
            }

        response_lower = response.lower()
        found_tools = []

        for tool in expected_tools:
            tool_name = tool.get("name", "").lower()
            if tool_name and tool_name in response_lower:
                found_tools.append(tool_name)

        score = len(found_tools) / len(expected_tools) if expected_tools else 0.0
        score = max(0.0, min(1.0, score))

        return {
            "score": score,
            "score_unit": "percent",
            "details": {
                "expected_tools": [t.get("name", "") for t in expected_tools],
                "found_tools": found_tools,
                "missing_tools": [
                    t.get("name", "")
                    for t in expected_tools
                    if t.get("name", "").lower() not in response_lower
                ],
            },
        }


class AnswerCorrectnessScorer(Scorer):
    """Scores whether the model's answer is factually correct.

    Uses exact match, containment, or keyword overlap depending on
    what information is available.
    """

    @property
    def name(self) -> str:
        return "answer_correctness"

    async def score(
        self,
        *,
        response: str,
        expected: str | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not expected:
            return {
                "score": 0.0,
                "score_unit": "percent",
                "details": {"reason": "no expected answer provided"},
            }

        response_lower = response.lower().strip()
        expected_lower = expected.lower().strip()

        if expected_lower == response_lower:
            score = 1.0
        elif expected_lower in response_lower:
            score = 0.85
        elif response_lower in expected_lower:
            score = 0.7
        else:
            # Keyword overlap
            expected_words = set(expected_lower.split())
            response_words = set(response_lower.split())
            # Remove common stop words
            stop_words = {
                "the", "a", "an", "and", "or", "but", "in", "on", "at",
                "to", "for", "of", "with", "by", "from", "as", "is",
                "are", "was", "were", "be", "been", "being", "have",
                "has", "had", "do", "does", "did", "will", "would",
                "could", "should", "may", "might", "must", "shall",
            }
            expected_words -= stop_words
            response_words -= stop_words
            if expected_words:
                overlap = len(expected_words & response_words) / len(expected_words)
                score = min(overlap, 0.6)
            else:
                score = 0.0

        score = max(0.0, min(1.0, score))

        return {
            "score": score,
            "score_unit": "percent",
            "details": {
                "exact_match": expected_lower == response_lower,
                "contains_expected": expected_lower in response_lower,
                "response_length": len(response),
                "expected_length": len(expected),
            },
        }


class JSONValidityScorer(Scorer):
    """Scores whether the model response is valid JSON."""

    @property
    def name(self) -> str:
        return "json_validity"

    async def score(
        self,
        *,
        response: str,
        expected: str | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            parsed = json.loads(response)
            is_valid = True
        except (json.JSONDecodeError, ValueError):
            parsed = None
            is_valid = False

        score = 1.0 if is_valid else 0.0

        return {
            "score": score,
            "score_unit": "percent",
            "details": {
                "is_valid_json": is_valid,
                "parsed_type": type(parsed).__name__ if parsed else None,
                "response_length": len(response),
            },
        }


class ToolCallAccuracyScorer(Scorer):
    """Scores whether tool calls in the response match expected tool calls."""

    @property
    def name(self) -> str:
        return "tool_call_accuracy"

    async def score(
        self,
        *,
        response: str,
        expected: str | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        context = context or {}
        expected_tool_calls = context.get("expected_tool_calls", [])

        if not expected_tool_calls:
            return {
                "score": 0.0,
                "score_unit": "percent",
                "details": {"reason": "no expected tool calls provided"},
            }

        response_lower = response.lower()
        correct_calls = 0

        for tool_call in expected_tool_calls:
            tool_name = tool_call.get("name", "").lower()
            tool_args = tool_call.get("arguments", {})

            if tool_name and tool_name in response_lower:
                # Check if key arguments are present
                args_found = True
                for key, value in tool_args.items():
                    if str(value).lower() not in response_lower:
                        args_found = False
                        break
                if args_found:
                    correct_calls += 1

        score = correct_calls / len(expected_tool_calls) if expected_tool_calls else 0.0
        score = max(0.0, min(1.0, score))

        return {
            "score": score,
            "score_unit": "percent",
            "details": {
                "expected_tool_calls": len(expected_tool_calls),
                "correct_tool_calls": correct_calls,
            },
        }


# Register built-in scorers
register_scorer("task_completion", TaskCompletionScorer)
register_scorer("tool_selection_accuracy", ToolSelectionAccuracyScorer)
register_scorer("answer_correctness", AnswerCorrectnessScorer)
register_scorer("json_validity", JSONValidityScorer)
register_scorer("tool_call_accuracy", ToolCallAccuracyScorer)
