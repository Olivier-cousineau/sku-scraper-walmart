#!/usr/bin/env python3
"""Entrypoint used by GitHub Actions to generate per-store snapshot files."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scraper import load_skus, load_stores


def main() -> None:
    print("SKUS FILE EXISTS:", Path("input/skus.json").exists())
    print("STORES FILE EXISTS:", Path("input/stores.json").exists())

    skus = load_skus()
    stores = load_stores()

    print(f"Loaded {len(skus)} SKUs. Sample: {skus[:5]}")
    print(f"Loaded {len(stores)} stores. Sample: {stores[:2]}")

    if not skus:
        raise SystemExit("ERROR: 0 SKUs loaded from input/skus.json")

    out_dir = Path("snapshots") / datetime.utcnow().strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)

    for store in stores:
        store_id = store.get("store_id")
        store_slug = store.get("store_slug")
        if not store_id or not store_slug:
            raise ValueError("Each store must include store_id and store_slug")

        results: list[dict[str, str]] = []

        for sku in skus:
            try:
                # Placeholder payload until full scraper extraction is wired here.
                results.append({"sku": sku, "status": "pending"})
            except Exception as e:
                print(f"[{store_slug}] FAIL sku={sku}: {e}")

        out_path = out_dir / f"{store_slug}.json"

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "store_id": store_id,
                    "store_slug": store_slug,
                    "results": results,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
            f.write("\n")

        print(f"Wrote {out_path} ({len(results)} items)")


if __name__ == "__main__":
    main()
