
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.agent_runtime.domain.execution_state import ExecutionState
from app.agent_runtime.domain.status import ExecutionStatus
from app.agent_runtime.domain.step import Step
from app.agent_runtime.state_machine import ExecutionStateMachine


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class Execution:
    """
    Represents the lifecycle of a single agent execution.

    ExecutionState is the authoritative lifecycle state.

    ExecutionStatus is retained for backward compatibility with the
    existing runtime and tests. It is synchronized automatically from
    ExecutionState.

    State lifecycle:

        CREATED
           |
           v
        PLANNING
           |
           v
        INFERENCE
         /      \
        v        v
    TOOL_EXECUTION  COMPLETED
        |
        v
    OBSERVING
        |
        v
    INFERENCE

    Any active state may transition to FAILED or CANCELLED.
    """

    id: UUID = field(default_factory=uuid4)

    # Backward-compatible status field.
    #
    # ExecutionState is the authoritative state. This field exists so
    # existing callers that still consume ExecutionStatus continue to work.
    status: ExecutionStatus = ExecutionStatus.CREATED

    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    error: str | None = None
    error_type: str | None = None

    # Ordered execution trace.
    steps: list[Step] = field(default_factory=list)

    # State machine is intentionally hidden from repr output because
    # callers should interact with Execution through state/transition APIs.
    state_machine: ExecutionStateMachine = field(
        default_factory=ExecutionStateMachine,
        repr=False,
    )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> ExecutionState:
        """
        Return the authoritative execution state.
        """
        return self.state_machine.state

    def can_transition_to(self, target: ExecutionState) -> bool:
        """
        Return whether the execution can transition to the target state.
        """
        return self.state_machine.can_transition_to(target)

    def transition_to(self, target: ExecutionState) -> None:
        """
        Transition the execution to a new lifecycle state.

        Invalid transitions are rejected by ExecutionStateMachine.

        Timestamp and backward-compatible status synchronization are
        handled here so every explicit state transition remains consistent.
        """
        self.state_machine.transition_to(target)

        self._sync_status()

        if target is ExecutionState.PLANNING:
            self._mark_started()

        elif target is ExecutionState.COMPLETED:
            self._mark_completed()

        elif target is ExecutionState.FAILED:
            self._mark_failed_state()

        elif target is ExecutionState.CANCELLED:
            self._mark_cancelled_state()

    # ------------------------------------------------------------------
    # Backward-compatible lifecycle methods
    # ------------------------------------------------------------------

    def mark_started(self) -> None:
        """
        Backward-compatible way to start an execution.

        Historically callers could do:

            execution.mark_started()

        and call it repeatedly without changing the original started_at.

        The state machine now owns the lifecycle, so this method maps the
        legacy operation to PLANNING while remaining idempotent for already
        active executions.
        """
        if self.state is ExecutionState.CREATED:
            self.transition_to(ExecutionState.PLANNING)
            return

        if self.state in {
            ExecutionState.PLANNING,
            ExecutionState.INFERENCE,
            ExecutionState.TOOL_EXECUTION,
            ExecutionState.OBSERVING,
        }:
            # Preserve legacy idempotent behavior.
            self._mark_started()
            self._sync_status()
            return

        raise RuntimeError(
            "Cannot start execution from terminal state "
            f"'{self.state.value}'"
        )

    def mark_completed(self) -> None:
        """
        Backward-compatible way to complete an execution.

        Older code expected:

            execution.mark_started()
            execution.mark_completed()

        That historically skipped intermediate lifecycle states.

        We preserve that behavior at the public compatibility boundary
        while still ensuring the actual state machine reaches COMPLETED
        through its valid transition path:

            PLANNING -> INFERENCE -> COMPLETED
        """
        if self.state is ExecutionState.PLANNING:
            # Compatibility bridge for the old mark_started()/mark_completed()
            # sequence.
            self.state_machine.transition_to(ExecutionState.INFERENCE)
            self._sync_status()

        if self.state is ExecutionState.INFERENCE:
            self.transition_to(ExecutionState.COMPLETED)
            return

        if self.state is ExecutionState.COMPLETED:
            # Preserve idempotent behavior for callers that mark completion
            # more than once.
            return

        raise RuntimeError(
            "Cannot complete execution from state "
            f"'{self.state.value}'"
        )

    def mark_failed(
        self,
        *,
        error: str,
        error_type: str | None = None,
    ) -> None:
        """
        Backward-compatible way to fail an execution.

        Failure is allowed from any non-terminal state.
        """
        if not error:
            raise ValueError("Execution failure error cannot be empty")

        if self.state in {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
        }:
            if self.state is ExecutionState.FAILED:
                # Preserve idempotent/update behavior for an already failed
                # execution.
                self.error = error
                self.error_type = error_type
                return

            raise RuntimeError(
                "Cannot fail execution from terminal state "
                f"'{self.state.value}'"
            )

        self.error = error
        self.error_type = error_type

        self.transition_to(ExecutionState.FAILED)

    def mark_cancelled(self) -> None:
        """
        Backward-compatible way to cancel an execution.
        """
        if self.state is ExecutionState.CANCELLED:
            # Preserve idempotent cancellation behavior.
            return

        if self.state in {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
        }:
            raise RuntimeError(
                "Cannot cancel execution from terminal state "
                f"'{self.state.value}'"
            )

        self.transition_to(ExecutionState.CANCELLED)

    # ------------------------------------------------------------------
    # Step tracing
    # ------------------------------------------------------------------

    def add_step(self, step: Step) -> None:
        """
        Append a step to the execution trace.
        """
        self.steps.append(step)

    # ------------------------------------------------------------------
    # Internal state synchronization
    # ------------------------------------------------------------------

    def _sync_status(self) -> None:
        """
        Synchronize the legacy ExecutionStatus with ExecutionState.

        ExecutionState remains authoritative.
        """
        mapping = {
            ExecutionState.CREATED: ExecutionStatus.CREATED,

            ExecutionState.PLANNING: ExecutionStatus.RUNNING,
            ExecutionState.INFERENCE: ExecutionStatus.RUNNING,
            ExecutionState.TOOL_EXECUTION: ExecutionStatus.RUNNING,
            ExecutionState.OBSERVING: ExecutionStatus.RUNNING,

            ExecutionState.COMPLETED: ExecutionStatus.COMPLETED,
            ExecutionState.FAILED: ExecutionStatus.FAILED,
            ExecutionState.CANCELLED: ExecutionStatus.CANCELLED,
        }

        self.status = mapping[self.state]

    def _mark_started(self) -> None:
        """
        Set started_at once.

        This method intentionally does not change the state.
        """
        if self.started_at is None:
            self.started_at = utc_now()

    def _mark_completed(self) -> None:
        """
        Set completed_at once.

        This method intentionally does not change the state.
        """
        if self.completed_at is None:
            self.completed_at = utc_now()

    def _mark_failed_state(self) -> None:
        """
        Mark the timestamp associated with a failed execution.
        """
        if self.completed_at is None:
            self.completed_at = utc_now()

    def _mark_cancelled_state(self) -> None:
        """
        Mark the timestamp associated with a cancelled execution.
        """
        if self.completed_at is None:
            self.completed_at = utc_now()

    # ------------------------------------------------------------------
    # Derived information
    # ------------------------------------------------------------------

    @property
    def duration_seconds(self) -> float | None:
        """
        Return execution duration in seconds.

        Returns None until both started_at and completed_at exist.
        """
        if self.started_at is None:
            return None

        if self.completed_at is None:
            return None

        return max(
            0.0,
            (self.completed_at - self.started_at).total_seconds(),
        )

    @property
    def is_terminal(self) -> bool:
        """
        Return True when the execution reached a terminal state.
        """
        return self.state_machine.is_terminal

    @property
    def is_completed(self) -> bool:
        """
        Return True when the execution completed successfully.
        """
        return self.state is ExecutionState.COMPLETED

    @property
    def is_failed(self) -> bool:
        """
        Return True when the execution failed.
        """
        return self.state is ExecutionState.FAILED

    @property
    def is_cancelled(self) -> bool:
        """
        Return True when the execution was cancelled.
        """
        return self.state is ExecutionState.CANCELLED
