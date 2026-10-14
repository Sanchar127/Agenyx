from __future__ import annotations


class AgenyxError(Exception):
    """Base exception for the Agenyx application."""


# ============================================================
# Agent-level errors
# ============================================================


class AgentError(AgenyxError):
    """Base exception for failures owned by the Agent layer."""


class InvalidStateTransition(AgentError):
    """Raised when an execution attempts an invalid state transition."""


class PlanningError(AgentError):
    """Raised when Agent planning fails."""


class DecisionError(AgentError):
    """
    Raised when inference output cannot be converted into a
    valid Agent decision.
    """


class AgentProtocolError(DecisionError):
    """
    Backward-compatible exception for invalid Agent/inference
    protocol data.

    This remains a DecisionError so existing callers continue to
    work while the Agent error hierarchy becomes more explicit.
    """


class ToolNotFound(AgentError):
    """
    Raised when the Agent requests a tool that does not exist.
    """


class UnknownToolError(ToolNotFound):
    """
    Backward-compatible exception for an unknown tool.

    UnknownToolError is intentionally a subclass of ToolNotFound.

    This means both of the following work:

        except ToolNotFound:
            ...

        except UnknownToolError:
            ...

    Existing callers can continue using UnknownToolError while
    new Agent-level code can depend on ToolNotFound.
    """


class ToolValidationError(AgentError):
    """
    Raised when tool arguments fail validation.
    """


class InvalidToolArgumentsError(ToolValidationError):
    """
    Backward-compatible exception for invalid tool arguments.

    New Agent code should generally use ToolValidationError.
    Existing callers can continue using InvalidToolArgumentsError.
    """


class ToolExecutionError(AgentError, RuntimeError):
    """
    Raised when a known tool fails during execution.
    """


class ExecutionLimitExceeded(AgentError):
    """
    Raised when an Agent execution exceeds a configured limit.
    """


class AgentMaxStepsError(ExecutionLimitExceeded):
    """
    Backward-compatible exception for maximum-step violations.
    """


class ExecutionCancelled(AgentError):
    """
    Raised when an Agent execution is cancelled.
    """


# ============================================================
# Agent <-> Inference service boundary
# ============================================================


class InferenceUnavailable(AgentError):
    """
    Raised when the Agent cannot reach the Inference service.

    The Agent intentionally does not know which inference provider
    is behind the service.
    """


class InferenceRequestFailed(AgentError):
    """
    Raised when the Inference service cannot successfully process
    an Agent request.
    """


# ============================================================
# Tool-layer compatibility errors
# ============================================================
#
# ToolNotFound, ToolValidationError and ToolExecutionError are now
# the Agent-facing error abstractions.
#
# UnknownToolError and InvalidToolArgumentsError above remain as
# compatibility subclasses for existing code/tests.
#
# ============================================================


class ToolError(AgenyxError):
    """
    Base exception for low-level tool-layer errors.

    Retained for backward compatibility with existing tool code.
    """


# ============================================================
# Inference-layer compatibility errors
# ============================================================
#
# These are temporarily retained because the current
# InferenceClient still imports them.
#
# They should eventually move into the Inference service/client
# boundary so Agent code does not depend on provider-specific
# failures.
#
# ============================================================


class LLMError(AgenyxError):
    """
    Base inference/provider error.

    Temporary compatibility exception.
    """


class LLMConnectionError(LLMError):
    """
    Raised when an LLM provider connection fails.
    """


class LLMTimeoutError(LLMError):
    """
    Raised when an LLM provider request times out.
    """


class LLMResponseError(LLMError):
    """
    Raised when an LLM provider returns an invalid response.
    """
