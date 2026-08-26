
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    """
    Definition of a model exposed by Agenyx.

    A model is independent from the provider implementation.

    Example:

        qwen2.5:7b
            -> ollama-local

        llama3.2:3b
            -> ollama-local

    The same provider may serve many models.
    """

    model_id: str
    provider_name: str

    object: str = "model"
    owned_by: str = "agenyx"

    # Optional metadata used later by model/semantic routing.
    capabilities: frozenset[str] = field(
        default_factory=frozenset
    )

    context_window: int | None = None

    # Whether Agenyx should expose this model through
    # /v1/models.
    enabled: bool = True
