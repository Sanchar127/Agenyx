from dataclasses import dataclass
from datetime import timedelta

@dataclass
class RecoveryPolicy:
    stale_timeout: timedelta = timedelta(minutes=5)
    max_recovery_attempts: int = 3
    allow_partial_replay: bool = True

    def can_recover(self, current_attempts: int, elapsed_since_heartbeat: timedelta) -> bool:
        if current_attempts >= self.max_recovery_attempts:
            return False
        if elapsed_since_heartbeat < self.stale_timeout:
            return False
        return True
