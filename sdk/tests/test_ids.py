"""Tests for the id validation module."""

import pytest
from gx_auth_sdk.ids import validate_object, validate_subject, validate_type


class TestValidateSubject:
    def test_simple_subject(self):
        assert validate_subject("user:abc") == "user:abc"

    def test_userset(self):
        assert validate_subject("group:lab-x#member") == "group:lab-x#member"

    def test_wildcard(self):
        assert validate_subject("user:*") == "user:*"

    def test_empty_string(self):
        with pytest.raises(ValueError, match="non-empty string"):
            validate_subject("")

    def test_none(self):
        with pytest.raises(ValueError, match="non-empty string"):
            validate_subject(None)

    def test_whitespace(self):
        with pytest.raises(ValueError, match="whitespace"):
            validate_subject("user: abc")

    def test_no_colon(self):
        with pytest.raises(ValueError, match="type:id"):
            validate_subject("userabc")

    def test_empty_type(self):
        with pytest.raises(ValueError, match="empty type"):
            validate_subject(":abc")

    def test_empty_id(self):
        with pytest.raises(ValueError, match="empty id"):
            validate_subject("user:")

    def test_empty_id_includes_sub_hint(self):
        with pytest.raises(ValueError, match="no IdP"):
            validate_subject("user:")

    def test_userset_empty_relation(self):
        with pytest.raises(ValueError, match="empty relation"):
            validate_subject("group:lab-x#")

    def test_userset_empty_id(self):
        with pytest.raises(ValueError, match="empty id"):
            validate_subject("group:#member")

    def test_custom_what_label(self):
        with pytest.raises(ValueError, match="grant subject"):
            validate_subject("", "grant subject")


class TestValidateObject:
    def test_valid(self):
        assert validate_object("project:42") == "project:42"

    def test_empty_string(self):
        with pytest.raises(ValueError, match="non-empty string"):
            validate_object("")

    def test_empty_id(self):
        with pytest.raises(ValueError, match="empty id"):
            validate_object("project:")

    def test_rejects_userset(self):
        with pytest.raises(ValueError, match="usersets and wildcards"):
            validate_object("group:lab-x#member")

    def test_rejects_wildcard(self):
        with pytest.raises(ValueError, match="usersets and wildcards"):
            validate_object("user:*")

    def test_no_colon(self):
        with pytest.raises(ValueError, match="type:id"):
            validate_object("project42")

    def test_whitespace(self):
        with pytest.raises(ValueError, match="whitespace"):
            validate_object("project: 42")


class TestValidateType:
    def test_valid(self):
        assert validate_type("sample") == "sample"

    def test_empty(self):
        with pytest.raises(ValueError, match="non-empty string"):
            validate_type("")

    def test_contains_colon(self):
        with pytest.raises(ValueError, match="bare type name"):
            validate_type("sample:1")

    def test_whitespace(self):
        with pytest.raises(ValueError, match="bare type name"):
            validate_type("sample foo")
