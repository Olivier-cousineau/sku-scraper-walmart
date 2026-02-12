#!/usr/bin/env python3
"""Entrypoint used by GitHub Actions to generate per-store snapshot files."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
import sys

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scraper import load_skus, load_stores

BASE_URL = "https://www.walmart.ca/ip/{sku}?storeId={store_id}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def build_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-CA,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )
    return session


def _extract_braced_json(raw_text: str, marker: str) -> str | None:
    marker_pos = raw_text.find(marker)
    if marker_pos < 0:
        return None

    start = raw_text.find("{", marker_pos)
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(raw_text)):
        ch = raw_text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw_text[start : idx + 1]
    return None


def _extract_embedded_data(html: str) -> dict | list | None:
    soup = BeautifulSoup(html, "html.parser")

    next_data_script = soup.find("script", id="__NEXT_DATA__")
    if next_data_script and next_data_script.string:
        try:
            return json.loads(next_data_script.string)
        except json.JSONDecodeError:
            pass

    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "__WML_REDUX_INITIAL_STATE__" not in text:
            continue
        payload = _extract_braced_json(text, "__WML_REDUX_INITIAL_STATE__")
        if not payload:
            continue
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            continue

    return None


def _walk_items(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_items(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_items(item)


def _first_str(node: dict, keys: list[str]) -> str | None:
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _number_from(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9.,-]", "", value).replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("price", "value", "amount", "current", "minPrice"):
            if key in value:
                found = _number_from(value[key])
                if found is not None:
                    return found
    return None


def _extract_product_fields(data, sku: str) -> dict | None:
    sku_norm = str(sku).strip()
    candidates: list[dict] = []
    fallback_candidates: list[dict] = []

    for node in _walk_items(data):
        node_sku = node.get("sku") or node.get("id") or node.get("usItemId")
        title = _first_str(node, ["name", "title", "productName"])
        if not title:
            continue

        if isinstance(node_sku, (str, int)) and str(node_sku).strip() == sku_norm:
            candidates.append(node)
        else:
            fallback_candidates.append(node)

    product = candidates[0] if candidates else (fallback_candidates[0] if fallback_candidates else None)
    if not product:
        return None

    title = _first_str(product, ["name", "title", "productName"])
    if not title:
        return None

    price_current = None
    for key in ("currentPrice", "price", "priceDisplay", "finalPrice"):
        if key in product:
            price_current = _number_from(product[key])
            if price_current is not None:
                break

    price_regular = None
    for key in ("wasPrice", "regularPrice", "listPrice", "compareAtPrice"):
        if key in product:
            price_regular = _number_from(product[key])
            if price_regular is not None:
                break

    availability_text = _first_str(
        product,
        ["availabilityStatus", "availabilityText", "fulfillmentLabel", "inventoryStatus"],
    )

    in_stock = product.get("inStock")
    if not isinstance(in_stock, bool):
        status_lower = (availability_text or "").lower()
        if any(token in status_lower for token in ["in stock", "available", "pickup"]):
            in_stock = True
        elif any(token in status_lower for token in ["out of stock", "unavailable", "sold out"]):
            in_stock = False
        else:
            in_stock = None

    return {
        "sku": str(product.get("sku") or sku),
        "title": title,
        "price_current": price_current,
        "price_regular": price_regular,
        "in_stock": in_stock,
        "availability": availability_text,
    }


def fetch_sku_store_data(
    session: requests.Session,
    sku: str,
    store_id: str,
    store_slug: str,
) -> dict[str, object]:
    url = BASE_URL.format(sku=sku, store_id=store_id)

    try:
        response = session.get(url, timeout=25)
    except requests.RequestException:
        return {"sku": sku, "status": "not_found"}

    if response.status_code in (403, 404, 429):
        return {"sku": sku, "status": "not_found"}

    if "robot" in response.text.lower() or "access denied" in response.text.lower():
        return {"sku": sku, "status": "not_found"}

    embedded_data = _extract_embedded_data(response.text)
    if embedded_data is None:
        return {"sku": sku, "status": "not_found"}

    extracted = _extract_product_fields(embedded_data, sku)
    if not extracted:
        return {"sku": sku, "status": "not_found"}

    checked_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    extracted.update(
        {
            "store_id": store_id,
            "store_slug": store_slug,
            "checked_at": checked_at,
        }
    )
    return extracted


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

    session = build_session()

    for store in stores:
        store_id = store.get("store_id")
        store_slug = store.get("store_slug")
        if not store_id or not store_slug:
            raise ValueError("Each store must include store_id and store_slug")

        results: list[dict[str, object]] = []

        for sku in skus:
            try:
                results.append(fetch_sku_store_data(session, sku, store_id, store_slug))
            except Exception as e:
                print(f"[{store_slug}] FAIL sku={sku}: {e}")
                results.append({"sku": sku, "status": "not_found"})
            finally:
                time.sleep(1)

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
