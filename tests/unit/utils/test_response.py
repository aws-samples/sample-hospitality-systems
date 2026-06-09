"""Unit tests for utils.response."""

import json

from utils.response import (
    snake_to_camel,
    transform_keys,
    ok,
    created,
    error,
    not_found,
    forbidden,
    bad_request,
    server_error,
)


class TestSnakeToCamel:
    def test_basic(self):
        assert snake_to_camel("guest_profile_id") == "guestProfileId"

    def test_single_word(self):
        assert snake_to_camel("guest") == "guest"

    def test_already_camel_passes_through(self):
        # No underscores -> unchanged
        assert snake_to_camel("guestId") == "guestId"


class TestTransformKeys:
    def test_flat_dict(self):
        assert transform_keys({"first_name": "A"}) == {"firstName": "A"}

    def test_nested_dict(self):
        out = transform_keys({"outer_key": {"inner_key": 1}})
        assert out == {"outerKey": {"innerKey": 1}}

    def test_list_of_dicts(self):
        out = transform_keys([{"a_b": 1}, {"c_d": 2}])
        assert out == [{"aB": 1}, {"cD": 2}]

    def test_scalar_passthrough(self):
        assert transform_keys("hello") == "hello"
        assert transform_keys(42) == 42


class TestSuccessEnvelopes:
    def test_ok_envelope(self):
        resp = ok({"room_type": "King"})
        assert resp["statusCode"] == 200
        assert resp["headers"]["Content-Type"] == "application/json"
        body = json.loads(resp["body"])
        assert body["success"] is True
        assert body["data"] == {"roomType": "King"}
        assert "requestId" in body["metadata"]
        assert "timestamp" in body["metadata"]

    def test_response_carries_cors_allow_origin(self):
        # REST API Gateway does NOT inject CORS headers on proxy responses —
        # only on the OPTIONS preflight. The Lambda must emit
        # Access-Control-Allow-Origin itself or browsers block the page from
        # reading the response. Lock that in so it can't regress.
        resp = ok({"a": 1})
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_ok_with_metadata(self):
        resp = ok({"a": 1}, metadata={"total_count": 5})
        body = json.loads(resp["body"])
        assert body["metadata"]["totalCount"] == 5

    def test_created_envelope(self):
        resp = created({"reservation_id": "r1"})
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["success"] is True
        assert body["data"] == {"reservationId": "r1"}


class TestErrorEnvelopes:
    def test_error_basic(self):
        resp = error(422, "ROOM_NOT_AVAILABLE", "No rooms")
        assert resp["statusCode"] == 422
        body = json.loads(resp["body"])
        assert body["success"] is False
        assert body["error"]["code"] == "ROOM_NOT_AVAILABLE"
        assert body["error"]["message"] == "No rooms"
        assert "details" not in body["error"]

    def test_error_with_details_transformed(self):
        resp = error(400, "BAD", "msg", details={"bad_field": "x"})
        body = json.loads(resp["body"])
        assert body["error"]["details"] == {"badField": "x"}

    def test_not_found(self):
        resp = not_found()
        assert resp["statusCode"] == 404
        assert json.loads(resp["body"])["error"]["code"] == "NOT_FOUND"

    def test_forbidden(self):
        resp = forbidden()
        assert resp["statusCode"] == 403
        assert json.loads(resp["body"])["error"]["code"] == "FORBIDDEN"

    def test_bad_request(self):
        resp = bad_request("nope")
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "BAD_REQUEST"
        assert body["error"]["message"] == "nope"

    def test_server_error(self):
        resp = server_error()
        assert resp["statusCode"] == 500
        assert json.loads(resp["body"])["error"]["code"] == "INTERNAL_ERROR"
