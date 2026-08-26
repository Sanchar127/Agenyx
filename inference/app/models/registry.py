from threading import RLock

from .definition import ModelDefinition


class ModelRegistry:
    """
    Thread-safe registry of models exposed by Agenyx.

    A model ID is mapped to the provider capable of serving it.

    Example:

        qwen2.5:7b   -> ollama-local
        llama3.2:3b  -> ollama-local

    Multiple models can belong to the same provider.
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelDefinition] = {}
        self._lock = RLock()

    def register(
        self,
        model: ModelDefinition,
    ) -> None:
        """
        Register a model.

        Raises:
            ValueError:
                If the model ID/provider is empty or the model
                has already been registered.
        """

        if not isinstance(model, ModelDefinition):
            raise TypeError(
                "model must be an instance of ModelDefinition"
            )

        if not model.model_id.strip():
            raise ValueError(
                "model_id must not be empty"
            )

        if not model.provider_name.strip():
            raise ValueError(
                "provider_name must not be empty"
            )

        with self._lock:
            if model.model_id in self._models:
                raise ValueError(
                    f"Model already registered: {model.model_id}"
                )

            self._models[model.model_id] = model

    def get(
        self,
        model_id: str,
    ) -> ModelDefinition:
        """
        Return a registered model.

        Raises:
            KeyError:
                If the model is not registered.
        """

        if not model_id:
            raise KeyError(
                "model_id must not be empty"
            )

        with self._lock:
            try:
                return self._models[model_id]

            except KeyError as exc:
                raise KeyError(
                    f"Model is not registered: {model_id}"
                ) from exc

    def list_models(self) -> list[ModelDefinition]:
        """
        Return a snapshot of all registered models.

        Important:
            This method is intentionally named `list_models`
            instead of `list` so it does not shadow Python's
            built-in `list` type.
        """

        with self._lock:
            return list(self._models.values())

    def exists(
        self,
        model_id: str,
    ) -> bool:
        """
        Check whether a model is registered.
        """

        with self._lock:
            return model_id in self._models

    def remove(
        self,
        model_id: str,
    ) -> None:
        """
        Remove a model from the registry.

        Raises:
            KeyError:
                If the model is not registered.
        """

        with self._lock:
            if model_id not in self._models:
                raise KeyError(
                    f"Model is not registered: {model_id}"
                )

            del self._models[model_id]

    def clear(self) -> None:
        """
        Remove all registered models.
        """

        with self._lock:
            self._models.clear()

    def count(self) -> int:
        """
        Return the number of registered models.
        """

        with self._lock:
            return len(self._models)
