"""Thread-safe JSON file storage with CRUD operations."""

import json
import os
import secrets
import threading
from typing import Optional


class JsonStore:
    """Generic CRUD store backed by JSON files in data/{entity_type}/{id}.json."""

    def __init__(self, data_dir: str, entity_type: str, id_prefix: str):
        self.base_dir = os.path.join(data_dir, entity_type)
        self.id_prefix = id_prefix
        self._lock = threading.Lock()
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, entity_id: str) -> str:
        return os.path.join(self.base_dir, f"{entity_id}.json")

    def _generate_id(self) -> str:
        return f"{self.id_prefix}_{secrets.token_hex(4)}"

    def list_all(self) -> list[dict]:
        """Return all entities."""
        with self._lock:
            entities = []
            if not os.path.isdir(self.base_dir):
                return entities
            for filename in sorted(os.listdir(self.base_dir)):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.base_dir, filename)
                    with open(filepath, "r") as f:
                        entities.append(json.load(f))
            return entities

    def get(self, entity_id: str) -> Optional[dict]:
        """Return entity by ID, or None if not found."""
        with self._lock:
            path = self._path(entity_id)
            if not os.path.exists(path):
                return None
            with open(path, "r") as f:
                return json.load(f)

    def create(self, data: dict) -> dict:
        """Create a new entity. Assigns ID and created_at if not present."""
        import datetime
        with self._lock:
            if "id" not in data or not data["id"]:
                data["id"] = self._generate_id()
            if "created_at" not in data:
                data["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            path = self._path(data["id"])
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            return data

    def update(self, entity_id: str, data: dict) -> Optional[dict]:
        """Full replace of entity. Returns None if not found."""
        with self._lock:
            path = self._path(entity_id)
            if not os.path.exists(path):
                return None
            data["id"] = entity_id
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            return data

    def patch(self, entity_id: str, data: dict) -> Optional[dict]:
        """Merge `data` into the existing entity (shallow). Returns None if not found."""
        with self._lock:
            path = self._path(entity_id)
            if not os.path.exists(path):
                return None
            with open(path, "r") as f:
                current = json.load(f)
            current.update(data)
            current["id"] = entity_id
            with open(path, "w") as f:
                json.dump(current, f, indent=2)
            return current

    def delete(self, entity_id: str) -> bool:
        """Delete entity. Returns True if deleted, False if not found."""
        with self._lock:
            path = self._path(entity_id)
            if not os.path.exists(path):
                return False
            os.remove(path)
            return True
