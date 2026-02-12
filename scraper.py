#!/usr/bin/env python3
"""Simple Walmart store loop loader for scraper inputs."""

from __future__ import annotations

import json
from pathlib import Path

STORES_PATH = Path("input/stores.json")
SKUS_PATH = Path("input/skus.json")


def load_stores(path: Path = STORES_PATH) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    stores = data.get("stores", [])
    if not isinstance(stores, list):
        raise ValueError("input/stores.json must contain a 'stores' list")
    return stores


def load_skus(path: Path = SKUS_PATH) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, dict):
        raw_skus = data.get("skus", [])
        if not isinstance(raw_skus, list):
            raise ValueError("input/skus.json must contain a 'skus' list")
    elif isinstance(data, list):
        raw_skus = [item.get("sku") for item in data if isinstance(item, dict)]
    else:
        raise ValueError("input/skus.json must be either {'skus': [...]} or [{'sku': '...'}]")

    skus = [sku.strip() for sku in raw_skus if isinstance(sku, str) and sku.strip()]
    print(f"Loaded {len(skus)} SKUs -> {skus[:5]}")

    if not skus:
        raise ValueError("No SKUs found in input/skus.json")

    return skus


def iter_store_targets(path: Path = STORES_PATH):
    for store in load_stores(path):
        store_id = store.get("store_id")
        store_slug = store.get("store_slug")
        if not store_id or not store_slug:
            raise ValueError("Each store must include store_id and store_slug")
        yield store_id, store_slug


def main() -> None:
    for store_id, store_slug in iter_store_targets():
        print(f"Processing store_id={store_id} store_slug={store_slug}")


if __name__ == "__main__":
    main()
