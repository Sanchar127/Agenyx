class TenantAuthorizer:
    """Authorize tenant access to configured models."""
    def __init__(
        self,
        tenant_model: dict[str, frozenset[str]],

    ) -> None:
        self.tenant_models= tenant_model

    def is_allowed(self, tenant_id: str, model_id: str) -> bool:
        """
        Return True if the tenant is allowed to use the model.
        """

        allowed_models = self.tenant_models.get(tenant_id)

        if allowed_models is None:
            return False

        return model_id in allowed_models
