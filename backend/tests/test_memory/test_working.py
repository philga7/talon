"""WorkingMemoryStore: get/set, GC."""

import pytest
from app.memory.working import WorkingMemoryStore


@pytest.mark.asyncio
async def test_set_get() -> None:
    """set then get returns value."""
    store = WorkingMemoryStore(idle_seconds=60)
    await store.set("s1", "key", "value")
    assert await store.get("s1", "key") == "value"


@pytest.mark.asyncio
async def test_get_missing_returns_none() -> None:
    """get for missing key returns None."""
    store = WorkingMemoryStore()
    assert await store.get("s1", "missing") is None


@pytest.mark.asyncio
async def test_get_all_empty() -> None:
    """get_all for session with no keys returns empty dict."""
    store = WorkingMemoryStore()
    assert await store.get_all("s1") == {}


@pytest.mark.asyncio
async def test_get_all_returns_all_pairs() -> None:
    """get_all returns all key-value pairs for session."""
    store = WorkingMemoryStore()
    await store.set("s1", "a", "1")
    await store.set("s1", "b", "2")
    assert await store.get_all("s1") == {"a": "1", "b": "2"}


@pytest.mark.asyncio
async def test_delete_existing() -> None:
    """delete existing key returns True and removes key."""
    store = WorkingMemoryStore()
    await store.set("s1", "k", "v")
    assert await store.delete("s1", "k") is True
    assert await store.get("s1", "k") is None


@pytest.mark.asyncio
async def test_delete_missing_returns_false() -> None:
    """delete missing key returns False."""
    store = WorkingMemoryStore()
    assert await store.delete("s1", "missing") is False


@pytest.mark.asyncio
async def test_gc_idle_sessions() -> None:
    """gc_idle_sessions removes sessions idle past threshold."""
    store = WorkingMemoryStore(idle_seconds=0)
    await store.set("s1", "k", "v")
    n = await store.gc_idle_sessions()
    assert n >= 1
    assert await store.get("s1", "k") is None
