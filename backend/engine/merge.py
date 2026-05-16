from __future__ import annotations

import json
from typing import Any


def parse_merge_fields(merge_fields_raw: str | None) -> list[str]:
    raw = (merge_fields_raw or "").strip()
    if not raw:
        return []
    try:
        obj = json.loads(raw)
        if isinstance(obj, list):
            return [str(x) for x in obj if x is not None]
    except json.JSONDecodeError:
        pass
    # Backward compatible: allow comma-separated strings.
    return [p.strip() for p in raw.split(",") if p.strip()]


def merge_values(
    *,
    strategy: str,
    fields: list[str],
    source_outputs: list[dict],
    merge_key_field: str,
) -> dict[str, Any]:
    """
    Merge predecessor outputs (store['node_outputs'][source_id]) by strategy.
    For each `field` we look up `source_out[field]` and merge that value.
    """
    strategy = (strategy or "append").strip().lower()
    merge_key_field = (merge_key_field or "id").strip()

    merged: dict[str, Any] = {}
    if not fields:
        return merged

    for field in fields:
        values = [out.get(field) for out in source_outputs if isinstance(out, dict)]

        if strategy == "append":
            if not all(isinstance(v, list) for v in values):
                raise ValueError(f"append requires list values for field={field}")
            merged[field] = []
            for v in values:
                merged[field] = merged[field] + v

        elif strategy == "zip":
            if not all(isinstance(v, list) for v in values):
                raise ValueError(f"zip requires list values for field={field}")
            lengths = [len(v) for v in values]
            if len(set(lengths)) != 1:
                raise ValueError(f"zip_error: length mismatch for field={field} ({lengths})")
            n = lengths[0]
            zipped: list[list[Any]] = []
            for i in range(n):
                zipped.append([v[i] for v in values])
            merged[field] = zipped

        elif strategy == "combine_by_key":
            if not all(isinstance(v, list) for v in values):
                raise ValueError(f"combine_by_key requires list-of-dicts values for field={field}")
            if not merge_key_field:
                raise ValueError("combine_by_key requires merge_key_field")

            order_keys: list[Any] = []
            by_key: dict[Any, dict] = {}
            for v in values:
                for item in v:
                    if not isinstance(item, dict):
                        raise ValueError(f"combine_by_key expects dict items for field={field}")
                    if merge_key_field not in item:
                        raise ValueError(f"zip_error: missing key {merge_key_field} in item for field={field}")
                    key = item.get(merge_key_field)
                    if key not in by_key:
                        by_key[key] = dict(item)
                        order_keys.append(key)
                        continue

                    existing = by_key[key]
                    # Conflict rule: if both sides define a field with different values -> error.
                    for k, new_val in item.items():
                        if k in existing and existing[k] != new_val:
                            raise ValueError(
                                f"zip_error: combine_by_key conflict for field={field}, key={key}, subkey={k}"
                            )
                        if k not in existing:
                            existing[k] = new_val

            merged[field] = [by_key[k] for k in order_keys]
        else:
            raise ValueError(f"Unknown merge strategy: {strategy}")

    return merged
