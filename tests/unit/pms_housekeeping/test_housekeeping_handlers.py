"""Unit tests for PMS housekeeping handlers — authz gates + validation.

Deep task state-machine transitions (assign/complete/inspect drive SFN
task tokens) are deferred to integration. These tests lock the require_groups
gates and the deterministic validation/not-found branches.
"""

import pytest

TASK = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
PROP = "a1b2c3d4-e5f6-4789-abcd-ef0123456789"


@pytest.fixture
def list_tasks(load_handler):
    return load_handler("pms/housekeeping/list_tasks.py")


@pytest.fixture
def get_task(load_handler):
    return load_handler("pms/housekeeping/get_task.py")


@pytest.fixture
def assign_task(load_handler):
    return load_handler("pms/housekeeping/assign_task.py")


@pytest.fixture
def complete_task(load_handler):
    return load_handler("pms/housekeeping/complete_task.py")


@pytest.fixture
def inspect_task(load_handler):
    return load_handler("pms/housekeeping/inspect_task.py")


@pytest.fixture
def room_status(load_handler):
    return load_handler("pms/housekeeping/room_status.py")


class TestAuthGates:
    """Housekeeping handlers admit Housekeeping/Manager/Admin; a guest (no
    group) is rejected with 403."""

    def test_list_tasks_forbidden(self, list_tasks, make_event, lambda_context):
        assert list_tasks.handler(make_event(groups=[]), lambda_context)["statusCode"] == 403

    def test_get_task_forbidden(self, get_task, make_event, lambda_context):
        ev = make_event(groups=[], path_params={"taskId": TASK})
        assert get_task.handler(ev, lambda_context)["statusCode"] == 403

    def test_assign_task_forbidden(self, assign_task, make_event, lambda_context):
        ev = make_event(groups=[], path_params={"taskId": TASK}, body={"assignedTo": "Maria"})
        assert assign_task.handler(ev, lambda_context)["statusCode"] == 403

    def test_complete_task_forbidden(self, complete_task, make_event, lambda_context):
        ev = make_event(groups=[], path_params={"taskId": TASK}, body={})
        assert complete_task.handler(ev, lambda_context)["statusCode"] == 403

    def test_inspect_task_forbidden(self, inspect_task, make_event, lambda_context):
        ev = make_event(groups=[], path_params={"taskId": TASK}, body={"passed": True})
        assert inspect_task.handler(ev, lambda_context)["statusCode"] == 403

    def test_room_status_forbidden_for_guest(self, room_status, make_event, lambda_context):
        assert room_status.handler(make_event(groups=[]), lambda_context)["statusCode"] == 403


class TestNotFoundAndValidation:
    def test_get_task_not_found(self, get_task, make_event, mock_db, monkeypatch, lambda_context):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(get_task, "get_conn", lambda: mock_db.conn)
        ev = make_event(groups=["Housekeeping"], path_params={"taskId": TASK})
        assert get_task.handler(ev, lambda_context)["statusCode"] == 404

    def test_assign_task_not_found(self, assign_task, make_event, mock_db, monkeypatch, lambda_context):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(assign_task, "get_conn", lambda: mock_db.conn)
        ev = make_event(groups=["Manager"], path_params={"taskId": TASK},
                        body={"assignedTo": "Maria"})
        resp = assign_task.handler(ev, lambda_context)
        assert resp["statusCode"] in (400, 404)
