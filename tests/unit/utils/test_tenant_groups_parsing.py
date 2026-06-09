"""Supplementary tenant tests: the string-form cognito:groups parsing in
get_groups_from_event (the existing tenant tests exercise list-form groups,
leaving the bracket/space and comma string branches uncovered)."""

from utils.tenant import get_groups_from_event


def _event(groups):
    return {"requestContext": {"authorizer": {"claims": {"cognito:groups": groups}}}}


class TestGetGroupsFromEvent:
    def test_list_form(self):
        assert get_groups_from_event(_event(["Admin", "Manager"])) == ["Admin", "Manager"]

    def test_bracket_space_string(self):
        assert get_groups_from_event(_event("[Admin Manager]")) == ["Admin", "Manager"]

    def test_comma_string(self):
        assert get_groups_from_event(_event("Admin,Manager")) == ["Admin", "Manager"]

    def test_empty_brackets(self):
        assert get_groups_from_event(_event("[]")) == []

    def test_empty_string(self):
        assert get_groups_from_event(_event("")) == []

    def test_absent_claim(self):
        event = {"requestContext": {"authorizer": {"claims": {"sub": "u"}}}}
        assert get_groups_from_event(event) == []
