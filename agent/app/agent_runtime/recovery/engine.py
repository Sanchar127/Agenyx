import logging
from sqlalchemy.orm import Session
from app.agent_runtime.domain.status import ExecutionStatus
from app.agent_runtime.recovery.policy import RecoveryPolicy
from app.agent_runtime.recovery.replayer import ContextReplayer
from app.agent_runtime.runtime import AgentRuntime

logger = logging.getLogger(__name__)

class RecoveryEngine:
    def __init__(self, db: Session, runtime: AgentRuntime, policy: RecoveryPolicy):
        self.db = db
        self.runtime = runtime
        self.policy = policy

    def recover_execution(self, execution_id: str):
        execution = self.runtime.get_execution(execution_id)
        events = self.runtime.get_execution_events(execution_id)

        if not self.policy.can_recover(execution.recovery_attempts, execution.elapsed_since_update()):
            logger.error(f"Execution {execution_id} exceeded recovery bounds. Marking as FAILED.")
            self.runtime.update_status(execution_id, ExecutionStatus.FAILED)
            return

        logger.info(f"Initiating crash recovery for Execution {execution_id}...")
        self.runtime.update_status(execution_id, ExecutionStatus.RECOVERING)

        # 1. Rehydrate Context
        replayer = ContextReplayer(self.runtime.context_manager)
        replayer.rehydrate(execution, events)

        # 2. Re-enter Execution Loop
        self.runtime.update_status(execution_id, ExecutionStatus.RUNNING)
        self.runtime.resume_loop(execution_id)
