"""Tests for the OpenFGA decision-engine client."""

import pytest
from gx_auth_sdk import check, delete_relationship, list_objects, write_relationship
from openfga_sdk import CheckResponse, ListObjectsResponse


class TestCheck:
    def test_returns_true_when_allowed(self, fake_fga):
        fake_fga.check_response = CheckResponse(allowed=True)
        assert check("user:alice", "can_view", "project:1") is True

    def test_returns_false_when_denied(self, fake_fga):
        fake_fga.check_response = CheckResponse(allowed=False)
        assert check("user:alice", "can_view", "project:1") is False

    def test_passes_context(self, fake_fga):
        fake_fga.check_response = CheckResponse(allowed=True)
        check("user:alice", "can_view", "project:1", context={"level": 3})
        assert fake_fga._last_check.context == {"level": 3}

    def test_rejects_malformed_user(self, fake_fga):
        with pytest.raises(ValueError, match="empty id"):
            check("user:", "can_view", "project:1")

    def test_rejects_malformed_object(self, fake_fga):
        with pytest.raises(ValueError, match="empty id"):
            check("user:alice", "can_view", "project:")

    def test_rejects_unqualified_user(self, fake_fga):
        with pytest.raises(ValueError, match="type:id"):
            check("alice", "can_view", "project:1")


class TestListObjects:
    def test_returns_object_ids(self, fake_fga):
        fake_fga.list_objects_response = ListObjectsResponse(objects=["sample:1", "sample:2"])
        result = list_objects("user:alice", "can_view", "sample")
        assert result == ["sample:1", "sample:2"]

    def test_returns_empty_list(self, fake_fga):
        fake_fga.list_objects_response = ListObjectsResponse(objects=[])
        assert list_objects("user:alice", "can_view", "sample") == []

    def test_rejects_malformed_user(self, fake_fga):
        with pytest.raises(ValueError, match="empty id"):
            list_objects("user:", "can_view", "sample")

    def test_rejects_qualified_type(self, fake_fga):
        with pytest.raises(ValueError, match="bare type name"):
            list_objects("user:alice", "can_view", "sample:1")

    def test_passes_correct_type(self, fake_fga):
        fake_fga.list_objects_response = ListObjectsResponse(objects=[])
        list_objects("user:alice", "can_view", "sample")
        assert fake_fga._last_list_objects.type == "sample"


class TestWriteRelationship:
    def test_writes_tuple(self, fake_fga):
        write_relationship("user:alice", "viewer", "project:1")
        assert len(fake_fga.writes) == 1
        t = fake_fga.writes[0]
        assert t.user == "user:alice"
        assert t.relation == "viewer"
        assert t.object == "project:1"

    def test_rejects_malformed_user(self, fake_fga):
        with pytest.raises(ValueError):
            write_relationship("user:", "viewer", "project:1")

    def test_rejects_malformed_object(self, fake_fga):
        with pytest.raises(ValueError):
            write_relationship("user:alice", "viewer", "project:")


class TestDeleteRelationship:
    def test_deletes_tuple(self, fake_fga):
        delete_relationship("user:alice", "viewer", "project:1")
        assert len(fake_fga.deletes) == 1
        t = fake_fga.deletes[0]
        assert t.user == "user:alice"
        assert t.relation == "viewer"
        assert t.object == "project:1"

    def test_rejects_malformed_user(self, fake_fga):
        with pytest.raises(ValueError):
            delete_relationship("user:", "viewer", "project:1")
