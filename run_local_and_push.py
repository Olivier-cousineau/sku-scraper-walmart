#!/usr/bin/env python3
"""Run Walmart scraper locally, then commit and push snapshots changes."""

from __future__ import annotations

import subprocess
import sys


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _has_snapshot_changes() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "snapshots"],
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def main() -> None:
    _run([sys.executable, "scripts/walmart_sku_store_check.py"])

    if not _has_snapshot_changes():
        print("No changes detected in snapshots/. Nothing to commit.")
        return

    _run(["git", "add", "snapshots"])
    _run(["git", "commit", "-m", "chore: update walmart snapshots (local)"])
    _run(["git", "push"])


if __name__ == "__main__":
    main()
