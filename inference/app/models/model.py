from dataclasses import dataclass


@dataclass(frozen=True)
class ModelDefinition:
    """
    Describes a model exposed by an inference provider.

    A model is identified by its public model ID while the
    provider identifies the backend capable of serving it.
    """

    model_id: str
    provider_name: str

    object: str = "model"
    owned_by: str = "agenyx"
