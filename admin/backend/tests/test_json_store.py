"""Tests for JsonStore — specifically the patch vs update distinction.

Regression guard: an earlier version of the device SSE loop called
`store.update(id, partial_dict)` which wiped unmentioned fields. The
`patch()` method was added to make that safe. These tests verify that
update() still does full-replace (intended) and patch() preserves fields.
"""

import os
import tempfile

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


class TestAtomicWrites:
    """Writes must never leave a truncated file on disk — a killed Python
    mid-write used to produce a 0-byte .json that crashed list_all() on
    next boot. _write_atomic routes through a *.tmp + os.replace."""

    def test_create_leaves_no_tmp_file(self, store):
        store.create({"name": "A"})
        leftover = [f for f in os.listdir(store.base_dir) if f.endswith(".tmp")]
        assert leftover == []

    def test_update_leaves_no_tmp_file(self, store):
        dev = store.create({"name": "A"})
        store.update(dev["id"], {"name": "B"})
        leftover = [f for f in os.listdir(store.base_dir) if f.endswith(".tmp")]
        assert leftover == []

    def test_patch_leaves_no_tmp_file(self, store):
        dev = store.create({"name": "A"})
        store.patch(dev["id"], {"name": "B"})
        leftover = [f for f in os.listdir(store.base_dir) if f.endswith(".tmp")]
        assert leftover == []


class TestCorruptionRecovery:
    """A single truncated JSON file must not take down list_all().
    It's quarantined to *.corrupted and the rest of the store still loads."""

    def test_list_all_quarantines_truncated_file(self, store):
        dev_good = store.create({"name": "good"})
        # Simulate a kill-9-during-write: a half-written file.
        bad_path = os.path.join(store.base_dir, "dev_broken.json")
        with open(bad_path, "w") as f:
            f.write('{"name": "bad",')  # trailing comma, unclosed

        # list_all must not raise; the good entity is returned.
        result = store.list_all()
        ids = [d["id"] for d in result]
        assert dev_good["id"] in ids
        assert "dev_broken" not in ids

        # The corrupt file has been renamed aside so we don't trip on it
        # again next boot — and so the operator can forensics it.
        assert os.path.exists(bad_path + ".corrupted")
        assert not os.path.exists(bad_path)

    def test_list_all_tolerates_multiple_corrupt_files(self, store):
        store.create({"name": "A"})
        for name in ("broken1", "broken2"):
            with open(os.path.join(store.base_dir, f"{name}.json"), "w") as f:
                f.write("not json")
        assert len(store.list_all()) == 1
