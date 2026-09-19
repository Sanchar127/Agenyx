from app.tenancy.authorizer import TenantAuthorizer


def test_tenant_can_access_authorized_model():
    authorizer = TenantAuthorizer(
        {
            "tenant-a": frozenset({
                "qwen2.5:7b",
                "llama3.2:3b",
            }),
            "tenant-b": frozenset({
                "llama3.2:3b",
            }),
        }
    )

    assert authorizer.is_allowed(
        "tenant-a",
        "qwen2.5:7b",
    )


def test_tenant_cannot_access_unauthorized_model():
    authorizer = TenantAuthorizer(
        {
            "tenant-a": frozenset({
                "qwen2.5:7b",
            }),
        }
    )

    assert not authorizer.is_allowed(
        "tenant-a",
        "llama3.2:3b",
    )


def test_unknown_tenant_is_denied():
    authorizer = TenantAuthorizer(
        {
            "tenant-a": frozenset({
                "qwen2.5:7b",
            }),
        }
    )

    assert not authorizer.is_allowed(
        "tenant-unknown",
        "qwen2.5:7b",
    )
