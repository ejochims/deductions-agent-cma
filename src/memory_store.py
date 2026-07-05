"""Managed-Agents memory store: cross-session precedent recall.

A memory store is a workspace-scoped set of notes that persists across sessions.
We seed it with Meridian's pre-digested settlement precedents (agent/memory_seed.json
— chiefly the 60%-of-claim convention for demo billbacks that lack Exhibit B) and
attach it read/write to every case's session. The agent consults it before drafting
a partial and may append new precedents; because all case sessions share one store,
a convention applied in one case is recalled in the next.

The store id is cached in runs/.managed_ids.json alongside the agent/environment
ids so the store is created and seeded once.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = REPO_ROOT / "agent" / "memory_seed.json"
_IDS_CACHE = REPO_ROOT / "runs" / ".managed_ids.json"

MEMORY_INSTRUCTIONS = (
    "Meridian settlement precedents and conventions. Consult before drafting a "
    "partial or a borderline decision; apply established conventions consistently; "
    "you may append a new precedent when you settle a novel pattern."
)


def _load_ids() -> dict:
    return json.loads(_IDS_CACHE.read_text()) if _IDS_CACHE.exists() else {}


def _save_ids(ids: dict) -> None:
    _IDS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _IDS_CACHE.write_text(json.dumps(ids, indent=2) + "\n")


def create_or_load_memory_store(client) -> str:
    """Create + seed the store once, or reuse the cached id."""
    ids = _load_ids()
    if ids.get("memory_store_id"):
        return ids["memory_store_id"]

    import anthropic

    store = client.beta.memory_stores.create(
        name="Meridian Deductions Precedents",
        description="Settlement precedents and conventions for deduction analysts.",
    )
    # Seed the pre-digested precedents. Only a 409 path conflict (already seeded)
    # is ignored — any other failure means the store is missing its precedents,
    # which must surface, not be swallowed.
    for note in json.loads(SEED_PATH.read_text()):
        try:
            client.beta.memory_stores.memories.create(
                store.id, path=note["path"], content=note["content"])
        except anthropic.APIStatusError as exc:
            if exc.status_code != 409:
                raise

    ids["memory_store_id"] = store.id
    _save_ids(ids)
    return store.id


def memory_resource(store_id: str) -> dict:
    """The session-resource entry that mounts the store read/write."""
    return {
        "type": "memory_store",
        "memory_store_id": store_id,
        "access": "read_write",
        "instructions": MEMORY_INSTRUCTIONS,
    }
