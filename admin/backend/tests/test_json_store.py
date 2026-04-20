"""Tests for JsonStore — specifically the patch vs update distinction.

Regression guard: an earlier version of the device SSE loop called
`store.update(id, partial_dict)` which wiped unmentioned fields. The
`patch()` method was added to make that safe. These tests verify that
update() still does full-replace (intended) and patch() preserves fields.
"""

import tempfile
from pathlib import Path

import pytest

from storage.json_store import JsonStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmp:
        yield JsonStore(tmp, "devices", "dev")


class TestCreateAndGet:
    def test_create_assigns_id_and_created_at(self, store):
        dev = store.create({"name": "A", "ip_address": "1.1.1.1"})
        assert dev["id"].startswith("dev_")
        assert dev["created_at"]
        assert dev["name"] == "A"


class TestUpdate:
    def test_update_is_full_replace(self, store):
        """update() intentionally replaces the whole record — preserved for PUT semantics."""
        dev = store.create({"name": "A", "ip_address": "1.1.1.1", "osc_port": 9000})
        store.update(dev["id"], {"name": "B"})  # no ip_address passed
        reloaded = store.get(dev["id"])
        assert reloaded["name"] == "B"
        assert "ip_address" not in reloaded  # full replace: field is gone


class TestPatch:
    def test_patch_merges_fields(self, store):
        dev = store.create({
            "name": "A", "ip_address": "1.1.1.1", "osc_port": 9000,
        })
        result = store.patch(dev["id"], {"type": "vents", "hardware_id": "vents_deadbeef"})
        assert result["name"] == "A"
        assert result["ip_address"] == "1.1.1.1"
        assert result["osc_port"] == 9000
        assert result["type"] == "vents"
        assert result["hardware_id"] == "vents_deadbeef"

        reloaded = store.get(dev["id"])
        assert reloaded == result

    def test_patch_preserves_created_at(self, store):
        dev = store.create({"name": "A"})
        created_at = dev["created_at"]
        store.patch(dev["id"], {"type": "vents"})
        reloaded = store.get(dev["id"])
        assert reloaded["created_at"] == created_at

    def test_patch_missing_entity_returns_none(self, store):
        assert store.patch("dev_nonexistent", {"type": "vents"}) is None

    def test_patch_cannot_change_id(self, store):
        dev = store.create({"name": "A"})
        store.patch(dev["id"], {"id": "dev_hijack"})
        reloaded = store.get(dev["id"])
        assert reloaded["id"] == dev["id"]  # id field is locked to the path
