class SandboxError(Exception):
    """Base exception for sandbox execution failures."""


class SandboxUnavailableError(SandboxError):
    """Raised when the sandbox cannot be reached."""


class SandboxProtocolError(SandboxError):
    """Raised when the sandbox returns an invalid response."""


class SandboxToolError(SandboxError):
    """Raised when the sandbox reports a tool failure."""
