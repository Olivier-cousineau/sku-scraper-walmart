#!/usr/bin/env python3
"""Compatibility entrypoint for the Walmart SKU workflow.

This script exists at the exact path expected by the GitHub Actions workflow.
It delegates to the current scraper implementation in ``scraper.py``.
"""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scraper import main


if __name__ == "__main__":
    main()
