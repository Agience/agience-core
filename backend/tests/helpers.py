"""
Shared test helpers and mock factories for backend tests.
"""
import json
from entities.artifact import Artifact
from entities.person import Person


# Mock factories

def mock_artifact(
    id="c1",
    collection_id="w1",
    state="draft",
    context_dict=None,
    content="test content",
    root_id=None,
    created_by="user-123",
):
    """Create a mock Artifact entity."""
    context = json.dumps(context_dict or {})
    return Artifact(
        id=id,
        collection_id=collection_id,
        state=state,
        context=context,
        content=content,
        root_id=root_id,
        created_by=created_by,
    )


def mock_container(
    id="col1",
    name="Test Collection",
    description="Test collection",
    created_by="user-123",
    content_type="application/vnd.agience.collection+json",
):
    """Create a mock container (workspace or collection) artifact."""
    return Artifact(
        id=id,
        name=name,
        description=description,
        created_by=created_by,
        content_type=content_type,
        state=Artifact.STATE_COMMITTED,
    )


def mock_person(
    id="user-123",
    email="test@example.com",
    name="Test User",
    picture="https://example.com/avatar.png"
):
    """Create a mock Person entity."""
    return Person(
        id=id,
        email=email,
        name=name,
        picture=picture
    )


# Assertion helpers

def assert_artifact_matches(artifact, expected_dict):
    """Assert artifact matches expected values."""
    assert artifact.id == expected_dict.get("id")
    if "collection_id" in expected_dict:
        assert artifact.collection_id == expected_dict["collection_id"]
    if "state" in expected_dict:
        assert artifact.state == expected_dict["state"]
    if "content" in expected_dict:
        assert artifact.content == expected_dict["content"]
    if "name" in expected_dict:
        assert artifact.name == expected_dict["name"]
    if "description" in expected_dict:
        assert artifact.description == expected_dict["description"]
    if "created_by" in expected_dict:
        assert artifact.created_by == expected_dict["created_by"]


# HTTP response helpers

def assert_http_status(response, expected_status):
    """Assert HTTP response status code."""
    assert response.status_code == expected_status, \
        f"Expected {expected_status}, got {response.status_code}: {response.text}"


def assert_response_has_fields(response_dict, required_fields):
    """Assert response dict contains all required fields."""
    for field in required_fields:
        assert field in response_dict, f"Response missing field: {field}"


# Mock DB helpers

def mock_db_session():
    """Create a mock DB session for testing."""
    from unittest.mock import Mock
    session = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    session.close = Mock()
    return session
