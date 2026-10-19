from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.mcp_gateway.routing import MCPRootPathMiddleware


async def mcp_root(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "path": request.scope["path"],
            "root_path": request.scope["root_path"],
        }
    )


def create_test_app() -> FastAPI:
    mcp_app = Starlette(
        routes=[
            Route("/", mcp_root, methods=["GET", "POST"]),
        ]
    )

    app = FastAPI()
    app.add_middleware(
        MCPRootPathMiddleware,
        mcp_app=mcp_app,
    )
    app.mount("/mcp", mcp_app, name="mcp")
    return app


def test_exact_mcp_path_does_not_redirect() -> None:
    with TestClient(create_test_app()) as client:
        response = client.post("/mcp", follow_redirects=False)

    assert response.status_code == 200
    assert response.json() == {
        "path": "/",
        "root_path": "/mcp",
    }


def test_mcp_path_with_trailing_slash_still_works() -> None:
    with TestClient(create_test_app()) as client:
        response = client.post("/mcp/", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers.get("location") is None
