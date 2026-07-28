"""Tests for server-side id validation (issue #5).

Covers the validators module directly and the pydantic schema wiring, so a
malformed id is rejected at the API boundary before reaching the engine.
"""

import pytest
from pydantic import ValidationError

from authz.api import CheckIn, GrantIn, ListObjectsIn
from authz.validators import (
    validate_object,
    validate_relation,
    validate_subject,
    validate_type_name,
)

# --- validate_subject -------------------------------------------------------


class TestValidateSubject:
    def test_valid_subject(self):
        assert validate_subject("user:abc123") == "user:abc123"

    def test_valid_userset(self):
        assert validate_subject("group:lab-x#member") == "group:lab-x#member"

    def test_valid_wildcard(self):
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


# --- validate_object --------------------------------------------------------


class TestValidateObject:
    def test_valid_object(self):
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


# --- validate_type_name -----------------------------------------------------


class TestValidateTypeName:
    def test_valid_type(self):
        assert validate_type_name("sample") == "sample"

    def test_empty_string(self):
        with pytest.raises(ValueError, match="non-empty string"):
            validate_type_name("")

    def test_contains_colon(self):
        with pytest.raises(ValueError, match="bare type name"):
            validate_type_name("sample:1")

    def test_whitespace(self):
        with pytest.raises(ValueError, match="bare type name"):
            validate_type_name("sample foo")


# --- validate_relation ------------------------------------------------------


class TestValidateRelation:
    def test_valid_relation(self):
        assert validate_relation("can_view") == "can_view"

    def test_empty_string(self):
        with pytest.raises(ValueError, match="non-empty string"):
            validate_relation("")

    def test_whitespace(self):
        with pytest.raises(ValueError, match="whitespace"):
            validate_relation("can view")


# --- Schema wiring: malformed ids produce pydantic ValidationError ----------


class TestCheckInSchema:
    def test_valid_payload_passes(self):
        CheckIn(user="user:abc", relation="can_view", object="project:1")

    def test_rejects_empty_user(self):
        with pytest.raises(ValidationError, match="user"):
            CheckIn(user="user:", relation="can_view", object="project:1")

    def test_rejects_malformed_object(self):
        with pytest.raises(ValidationError, match="object"):
            CheckIn(user="user:abc", relation="can_view", object="project:")

    def test_rejects_empty_relation(self):
        with pytest.raises(ValidationError, match="relation"):
            CheckIn(user="user:abc", relation="", object="project:1")

    def test_rejects_unqualified_user(self):
        with pytest.raises(ValidationError, match="user"):
            CheckIn(user="abc", relation="can_view", object="project:1")


class TestListObjectsInSchema:
    def test_valid_payload_passes(self):
        ListObjectsIn(user="user:abc", relation="can_view", type="sample")

    def test_rejects_empty_user(self):
        with pytest.raises(ValidationError, match="user"):
            ListObjectsIn(user="user:", relation="can_view", type="sample")

    def test_rejects_qualified_type(self):
        with pytest.raises(ValidationError, match="type"):
            ListObjectsIn(user="user:abc", relation="can_view", type="sample:1")

    def test_rejects_empty_relation(self):
        with pytest.raises(ValidationError, match="relation"):
            ListObjectsIn(user="user:abc", relation="", type="sample")


class TestGrantInSchema:
    def test_valid_payload_passes(self):
        GrantIn(subject="user:abc", relation="member", object="project:1")

    def test_rejects_empty_subject(self):
        with pytest.raises(ValidationError, match="subject"):
            GrantIn(subject="user:", relation="member", object="project:1")

    def test_rejects_wildcard_object(self):
        with pytest.raises(ValidationError, match="object"):
            GrantIn(subject="user:abc", relation="member", object="project:*")

    def test_rejects_empty_relation(self):
        with pytest.raises(ValidationError, match="relation"):
            GrantIn(subject="user:abc", relation="", object="project:1")

    def test_accepts_userset_subject(self):
        GrantIn(subject="group:lab-x#member", relation="viewer", object="project:1")
