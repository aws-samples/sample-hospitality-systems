"""Unit tests for utils.validation."""

import json
from datetime import date, timedelta

from utils.validation import (
    parse_body,
    require_fields,
    validate_date,
    validate_date_range,
    validate_pagination,
    validate_uuid,
)

VALID_UUID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"


class TestParseBody:
    def test_returns_dict_when_body_is_dict(self):
        assert parse_body({"body": {"a": 1}}) == {"a": 1}

    def test_parses_json_string(self):
        assert parse_body({"body": '{"a": 1}'}) == {"a": 1}

    def test_returns_none_when_body_missing(self):
        assert parse_body({}) is None

    def test_returns_none_when_body_is_none(self):
        assert parse_body({"body": None}) is None

    def test_returns_none_on_invalid_json(self):
        assert parse_body({"body": "{not json"}) is None


class TestRequireFields:
    def test_returns_none_when_all_present(self):
        assert require_fields({"a": 1, "b": 2}, ["a", "b"]) is None

    def test_error_when_body_none(self):
        resp = require_fields(None, ["a"])
        assert resp["statusCode"] == 400

    def test_error_lists_missing_fields(self):
        resp = require_fields({"a": 1}, ["a", "b", "c"])
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "b" in body["error"]["message"]
        assert "c" in body["error"]["message"]

    def test_none_valued_field_counts_as_missing(self):
        resp = require_fields({"a": None}, ["a"])
        assert resp["statusCode"] == 400


class TestValidateUuid:
    def test_bool_style_valid(self):
        assert validate_uuid(VALID_UUID) is True

    def test_bool_style_invalid(self):
        assert validate_uuid("not-a-uuid") is False

    def test_raising_style_returns_value(self):
        assert validate_uuid(VALID_UUID, "propertyId") == VALID_UUID

    def test_raising_style_raises_on_invalid(self):
        try:
            validate_uuid("nope", "propertyId")
            raise AssertionError("expected ValueError")
        except ValueError as e:
            assert "propertyId" in str(e)

    def test_none_value_is_invalid(self):
        assert validate_uuid(None) is False


class TestValidateDate:
    def test_parses_valid_date(self):
        assert validate_date("2026-07-15") == date(2026, 7, 15)

    def test_returns_none_on_bad_format(self):
        assert validate_date("07/15/2026") is None

    def test_returns_none_on_none(self):
        assert validate_date(None) is None


class TestValidateDateRange:
    def _future(self, days):
        return (date.today() + timedelta(days=days)).isoformat()

    def test_valid_future_range(self):
        assert validate_date_range(self._future(1), self._future(3)) is None

    def test_bad_checkin_format(self):
        resp = validate_date_range("bad", self._future(3))
        assert resp["statusCode"] == 400

    def test_bad_checkout_format(self):
        resp = validate_date_range(self._future(1), "bad")
        assert resp["statusCode"] == 400

    def test_checkin_in_past_rejected(self):
        past = (date.today() - timedelta(days=2)).isoformat()
        resp = validate_date_range(past, self._future(3))
        assert resp["statusCode"] == 400

    def test_checkout_not_after_checkin_rejected(self):
        d = self._future(5)
        resp = validate_date_range(d, d)
        assert resp["statusCode"] == 400


class TestValidatePagination:
    def test_defaults_when_no_params(self):
        assert validate_pagination({}) == {"page": 1, "limit": 20, "offset": 0}

    def test_reads_params(self):
        result = validate_pagination({"queryStringParameters": {"page": "3", "limit": "10"}})
        assert result == {"page": 3, "limit": 10, "offset": 20}

    def test_non_numeric_falls_back_to_defaults(self):
        result = validate_pagination({"queryStringParameters": {"page": "x", "limit": "y"}})
        assert result["page"] == 1
        assert result["limit"] == 20

    def test_page_floor(self):
        assert validate_pagination({"queryStringParameters": {"page": "0"}})["page"] == 1

    def test_limit_floor(self):
        assert validate_pagination({"queryStringParameters": {"limit": "0"}})["limit"] == 1

    def test_limit_ceiling(self):
        assert validate_pagination({"queryStringParameters": {"limit": "500"}})["limit"] == 100

    def test_null_query_params(self):
        assert validate_pagination({"queryStringParameters": None})["page"] == 1
