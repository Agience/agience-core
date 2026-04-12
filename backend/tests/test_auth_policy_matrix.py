import pytest
from fastapi.routing import APIRoute

from main import app
from services.dependencies import get_auth


def _get_route(path: str, method: str) -> APIRoute:
    method = method.upper()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f"Route not found for {method} {path}")


def _route_dependency_calls(route: APIRoute):
    return {dep.call for dep in route.dependant.dependencies if dep.call is not None}


@pytest.mark.parametrize(
    "method,path",
    [
        # Unified artifact endpoints
        ("POST", "/artifacts"),
        ("GET", "/artifacts/{artifact_id}"),
        ("PATCH", "/artifacts/{artifact_id}"),
        ("DELETE", "/artifacts/{artifact_id}"),
        ("POST", "/artifacts/{artifact_id}/invoke"),
        ("POST", "/artifacts/search"),
        # Grant endpoints
        ("POST", "/grants/claim"),
        ("POST", "/grants"),
    ],
)
def test_all_critical_routes_use_get_auth(method, path):
    """All critical routes use the unified get_auth() dependency."""
    route = _get_route(path, method)
    calls = _route_dependency_calls(route)
    assert get_auth in calls, f"Expected get_auth on {method} {path}"
