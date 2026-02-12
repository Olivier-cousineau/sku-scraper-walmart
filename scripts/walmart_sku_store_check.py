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

from scraper import iter_store_targets


def main() -> None:
    out_dir = Path("snapshots") / datetime.utcnow().strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)

    for store_id, store_slug in iter_store_targets():
        # Placeholder payload until full scraper extraction is wired here.
        results: list[dict[str, str]] = []
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
