from __future__ import annotations

from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent_runtime.context_manager import ContextManager


class EventLike(Protocol):
    event_type: str
    payload: dict[str, Any]
    created_at: Any


class ContextReplayer:
    def __init__(self, context_manager: ContextManager) -> None:
        self.context_manager = context_manager

    def rehydrate(self, execution: Any, events: list[Any]) -> ContextManager:
        """Reconstructs state history directly from event logs."""
        self.context_manager.clear()

        for event in sorted(events, key=lambda e: getattr(e, "created_at", 0)):
            event_type = getattr(event, "event_type", None) or (
                event.get("event_type") if isinstance(event, dict) else None
            )
            payload = getattr(event, "payload", None) or (
                event.get("payload", {}) if isinstance(event, dict) else {}
            )

            if event_type == "USER_INPUT":
                self.context_manager.add_user_message(payload.get("text", ""))
            elif event_type == "MODEL_DECISION":
                self.context_manager.add_assistant_message(payload.get("decision", ""))
            elif event_type == "TOOL_RESULT":
                self.context_manager.add_tool_result(
                    tool_call_id=payload.get("tool_call_id"),
                    result=payload.get("result"),
                )

        return self.context_manager
