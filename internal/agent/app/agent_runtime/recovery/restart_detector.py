# app/agent_runtime/recovery/restart_detector.py
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agent_runtime.domain.status import ExecutionStatus
from app.db.models.execution import ExecutionModel  # <-- Fixed: Added missing import

logger = logging.getLogger(__name__)


class RestartDetector:
    def __init__(self, db_session, stale_threshold_seconds: int = 300) -> None:
        self.db = db_session
        self.stale_threshold_seconds = stale_threshold_seconds

    def scan_and_flag_orphaned_executions(self) -> list[str]:
        now = datetime.now(timezone.utc)
        orphaned_runs = (
            self.db.query(ExecutionModel)
            .filter(
                ExecutionModel.status.in_(
                    [ExecutionStatus.RUNNING, ExecutionStatus.RECOVERING]
                )
            )
            .all()
        )

        flagged_ids = []
        for run in orphaned_runs:
            updated_at = run.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)

            delta = (now - updated_at).total_seconds()
            if delta > self.stale_threshold_seconds:
                run.status = ExecutionStatus.CRASHED
                run.recovery_attempts = (getattr(run, "recovery_attempts", 0) or 0) + 1
                flagged_ids.append(run.id)

        if flagged_ids:
            self.db.commit()
            logger.warning(
                "Detected %d crashed/orphaned executions: %s",
                len(flagged_ids),
                flagged_ids,
            )

        return flagged_ids
