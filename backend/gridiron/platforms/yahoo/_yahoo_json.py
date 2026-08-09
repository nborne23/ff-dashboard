"""Shared low-level helpers for Yahoo Fantasy Sports API's JSON quirks.

Yahoo represents collections as `{"count": N, "0": {...}, "1": {...}, ...}` and represents a
single resource's fields as an array of small (often single-key) dicts — sometimes with an
extra level of list nesting for resources with many optional sub-resources (`team`, `league`,
`player`). These helpers normalize both patterns so `client.py` (URL navigation) and
`mapper.py` (entity mapping) don't each reimplement Yahoo's JSON parsing.
"""

from typing import Any


def collection_items(collection: dict) -> list[Any]:
    """Return the ordered items of a Yahoo `{"count": N, "0": {...}, ...}` collection."""
    count = collection.get("count", 0)
    return [collection[str(i)] for i in range(count) if str(i) in collection]


def flatten(resource: Any) -> dict:
    """Merge a Yahoo resource array (list of small dicts, possibly nested one level deep, e.g.
    `[[{"a": 1}, {"b": 2}], {"c": 3}]`) into a single flat dict. A plain dict is returned as-is
    (copied)."""
    if isinstance(resource, dict):
        return dict(resource)
    merged: dict = {}
    for item in resource:
        if isinstance(item, dict):
            merged.update(item)
        elif isinstance(item, list):
            merged.update(flatten(item))
    return merged


def find_subresource(parts: Any, key: str) -> Any:
    """Find `key` among a resource array's dict elements, skipping any nested list elements
    (which represent scalar fields, not named sub-resources). Raises `KeyError` if `key` is
    never found among the array's dict elements."""
    for part in parts:
        if isinstance(part, dict) and key in part:
            return part[key]
    raise KeyError(key)


def truthy(value: Any) -> bool:
    """Yahoo represents booleans inconsistently (`1`/`0` ints, `"1"`/`"0"` strings)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false")
    return bool(value)
