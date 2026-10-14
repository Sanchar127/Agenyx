# app/tools/idempotency.py
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional


class IdempotencyManager:
    def __init__(self, db_session) -> None:
        self.db = db_session

    @staticmethod
    def generate_key(execution_id: str, step_index: int, tool_name: str, payload: dict[str, Any]) -> str:
        raw_str = f"{execution_id}:{step_index}:{tool_name}:{json.dumps(payload, sort_keys=True)}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def get_cached_result(self, idempotency_key: str) -> Optional[dict[str, Any]]:
        query = getattr(self.db, "query", None)
        if query is None:
            return None

        try:
            from app.db.models.result import ExecutionResultModel
            # Query by execution_id or whatever field primary key is mapped to
            record = (
                self.db.query(ExecutionResultModel)
                .filter(ExecutionResultModel.execution_id == idempotency_key)
                .first()
            )
            return getattr(record, "output", None) if record else None
        except Exception:
            return None

    def save_result(self, idempotency_key: str, execution_id: str, output: dict[str, Any]) -> None:
        from app.db.models.result import ExecutionResultModel

        # Store using idempotency_key as execution_id (or primary lookup field)
        record = ExecutionResultModel(
            execution_id=idempotency_key,
            output=output,
        )
        self.db.add(record)
        self.db.commit()
