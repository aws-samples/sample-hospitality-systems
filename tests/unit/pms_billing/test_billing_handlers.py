"""Unit tests for PMS billing handlers — authz gates + not-found branches.

post_charge and void_folio are Manager/Admin only; list/get admit FrontDesk
too. Folio settlement + charge-posting transactional flows are deferred to
integration.
"""

import pytest

FOLIO = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
PROP = "a1b2c3d4-e5f6-4789-abcd-ef0123456789"


@pytest.fixture
def list_folios(load_handler):
    return load_handler("pms/billing/list_folios.py")


@pytest.fixture
def get_folio(load_handler):
    return load_handler("pms/billing/get_folio.py")


@pytest.fixture
def post_charge(load_handler):
    return load_handler("pms/billing/post_charge.py")


@pytest.fixture
def void_folio(load_handler):
    return load_handler("pms/billing/void_folio.py")


class TestAuthGates:
    def test_list_folios_forbidden_for_housekeeping(self, list_folios, make_event, lambda_context):
        assert list_folios.handler(make_event(groups=["Housekeeping"]), lambda_context)["statusCode"] == 403

    def test_get_folio_forbidden_for_guest(self, get_folio, make_event, lambda_context):
        ev = make_event(groups=[], path_params={"folioId": FOLIO})
        assert get_folio.handler(ev, lambda_context)["statusCode"] == 403

    def test_post_charge_forbidden_for_frontdesk(self, post_charge, make_event, lambda_context):
        # post_charge is Manager/Admin only.
        ev = make_event(groups=["FrontDesk"], path_params={"folioId": FOLIO},
                        body={"amount": 50, "description": "Spa"})
        assert post_charge.handler(ev, lambda_context)["statusCode"] == 403

    def test_void_folio_forbidden_for_frontdesk(self, void_folio, make_event, lambda_context):
        ev = make_event(groups=["FrontDesk"], path_params={"folioId": FOLIO}, body={})
        assert void_folio.handler(ev, lambda_context)["statusCode"] == 403


class TestNotFound:
    def test_get_folio_not_found(self, get_folio, make_event, mock_db, monkeypatch, lambda_context):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(get_folio, "get_conn", lambda: mock_db.conn)
        ev = make_event(groups=["Manager"], path_params={"folioId": FOLIO})
        assert get_folio.handler(ev, lambda_context)["statusCode"] == 404
