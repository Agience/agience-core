"""gate_service capability feature (`beacon`): enforcement-off grants all;
when enforced, the feature must be present in the entitlement cache."""

from services import gate_service


def test_features_open_when_enforcement_disabled(monkeypatch):
    # Dev / self-host: enforcement off → every capability granted, no DB touch.
    monkeypatch.setattr(gate_service, "enforcement_enabled", lambda: False)
    assert gate_service.has_feature(None, "user-1", "beacon") is True


def test_feature_present_when_enforced(monkeypatch):
    monkeypatch.setattr(gate_service, "enforcement_enabled", lambda: True)
    monkeypatch.setattr(gate_service, "get_limits", lambda db, pid: {"features": ["beacon"]})
    assert gate_service.has_feature(object(), "user-1", "beacon") is True


def test_feature_absent_when_enforced(monkeypatch):
    monkeypatch.setattr(gate_service, "enforcement_enabled", lambda: True)
    monkeypatch.setattr(gate_service, "get_limits", lambda db, pid: {"features": []})
    assert gate_service.has_feature(object(), "user-1", "beacon") is False


def test_no_entitlement_row_when_enforced(monkeypatch):
    monkeypatch.setattr(gate_service, "enforcement_enabled", lambda: True)
    monkeypatch.setattr(gate_service, "get_limits", lambda db, pid: None)
    assert gate_service.has_feature(object(), "user-1", "beacon") is False


# --- set_limits writes the capability set (the gate_router `features` path) ----

def test_set_limits_persists_features_on_insert():
    from unittest.mock import MagicMock

    db = MagicMock()
    coll = db.collection.return_value
    coll.has.return_value = False  # new row → insert path
    gate_service.set_limits(db, "user-1", max_workspaces=2, features=["beacon"])
    doc = coll.insert.call_args.args[0]
    assert doc["features"] == ["beacon"]


def test_set_limits_without_features_does_not_clobber_on_update():
    from unittest.mock import MagicMock

    db = MagicMock()
    coll = db.collection.return_value
    coll.has.return_value = True  # existing row → update path
    gate_service.set_limits(db, "user-1", max_workspaces=2)  # features omitted
    doc = coll.update.call_args.args[0]
    assert "features" not in doc  # omitting features leaves the existing set untouched
