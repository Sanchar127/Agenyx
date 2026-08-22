class AgenyxError(Exception):
    """Base Agenyx exception."""


class LLMError(AgenyxError):
    """Base LLM provider error."""


class LLMConnectionError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


class ToolError(AgenyxError):
    """Base tool execution error."""


class UnknownToolError(ToolError):
    pass


class InvalidToolArgumentsError(ToolError):
    pass


class ToolExecutionError(ToolError):
    pass


class AgentMaxStepsError(AgenyxError):
    pass


class AgentProtocolError(AgenyxError):
    pass
