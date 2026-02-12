import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, TimeoutError, async_playwright

INPUT_SKUS = Path("input/skus.json")
INPUT_STORES = Path("input/stores.json")
SNAPSHOTS_DIR = Path("snapshots")
THROTTLE_SECONDS = 1.2


def load_skus(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, dict) and isinstance(data.get("skus"), list):
        return [str(sku).strip() for sku in data["skus"] if str(sku).strip()]

    if isinstance(data, list):
        skus: list[str] = []
        for obj in data:
            if isinstance(obj, dict) and obj.get("sku"):
                sku = str(obj["sku"]).strip()
                if sku:
                    skus.append(sku)
        return skus

    raise ValueError(
        "Format input/skus.json non supporté. Utiliser {'skus':[...]} ou [{'sku':'...'}]."
    )


def load_stores(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    stores = data.get("stores", []) if isinstance(data, dict) else []
    normalized: list[dict[str, str]] = []

    for store in stores:
        if not isinstance(store, dict):
            continue
        store_id = str(store.get("store_id", "")).strip()
        store_slug = str(store.get("store_slug", "")).strip()
        if store_id and store_slug:
            normalized.append(
                {
                    "store_id": store_id,
                    "store_slug": store_slug,
                    "name": str(store.get("name", "")).strip(),
                }
            )

    if not normalized:
        raise ValueError("Aucun magasin valide trouvé dans input/stores.json")

    return normalized


def nested_get(data: Any, *keys: str) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def extract_product_from_next_data(next_data: dict[str, Any]) -> tuple[str | None, Any, Any]:
    product = first_non_empty(
        nested_get(next_data, "props", "pageProps", "initialData", "data", "product"),
        nested_get(next_data, "props", "pageProps", "dehydratedState", "queries"),
        nested_get(next_data, "props", "pageProps", "product"),
        nested_get(next_data, "props", "pageProps", "data", "product"),
    )

    title = None
    price = None
    availability = None

    if isinstance(product, dict):
        title = first_non_empty(
            product.get("name"),
            product.get("title"),
            nested_get(product, "identifiers", "name"),
        )
        price = first_non_empty(
            nested_get(product, "priceInfo", "currentPrice", "price"),
            nested_get(product, "priceInfo", "price"),
            product.get("price"),
        )
        availability = first_non_empty(
            nested_get(product, "availabilityStatus"),
            nested_get(product, "availability", "status"),
            nested_get(product, "availability", "isAvailable"),
            product.get("inStock"),
        )

    if title is None:
        page_props = nested_get(next_data, "props", "pageProps")
        if isinstance(page_props, dict):
            title = first_non_empty(page_props.get("title"), page_props.get("productTitle"))
            price = first_non_empty(
                price,
                nested_get(page_props, "price", "current"),
                page_props.get("price"),
            )
            availability = first_non_empty(
                availability,
                page_props.get("availability"),
                page_props.get("inStock"),
            )

    return title, price, availability


async def try_set_store_context(page: Page, store_id: str) -> None:
    url = f"https://www.walmart.ca/en/stores-near-me/{store_id}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception:
        return

    candidates = [
        "button:has-text('Set as my store')",
        "button:has-text('Select this store')",
        "button:has-text('Choose store')",
        "button:has-text('My store')",
        "button:has-text('Définir comme magasin')",
        "button:has-text('Choisir ce magasin')",
    ]

    for selector in candidates:
        try:
            button = page.locator(selector).first
            if await button.count() > 0 and await button.is_visible():
                await button.click(timeout=2500)
                await asyncio.sleep(1.0)
                return
        except Exception:
            continue


async def extract_item(page: Page, sku: str, store: dict[str, str]) -> dict[str, Any]:
    captured_at = datetime.now(timezone.utc).isoformat()
    url = f"https://www.walmart.ca/fr/ip/{sku}"
    title = None
    price_current = None
    availability = None

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        next_data_content = await page.locator("script#__NEXT_DATA__[type='application/json']").first.text_content()

        if next_data_content:
            try:
                next_data = json.loads(next_data_content)
                title, price_current, availability = extract_product_from_next_data(next_data)
            except json.JSONDecodeError:
                pass

        if title is None:
            title = await page.title()
        if price_current is None:
            price_current = await page.locator("[itemprop='price']").first.get_attribute("content")
        if availability is None:
            availability = await page.locator("link[itemprop='availability']").first.get_attribute("href")
    except TimeoutError as exc:
        title = f"ERROR_TIMEOUT: {exc}"
    except Exception as exc:
        title = f"ERROR: {type(exc).__name__}: {exc}"

    in_stock = None
    if isinstance(availability, bool):
        in_stock = availability
    elif isinstance(availability, str):
        low = availability.lower()
        if "instock" in low or "in stock" in low or "available" in low:
            in_stock = True
        elif "outofstock" in low or "out of stock" in low or "unavailable" in low:
            in_stock = False

    return {
        "retailer": "walmart",
        "walmart store_id": store["store_id"],
        "store_slug": store["store_slug"],
        "sku": sku,
        "url": url,
        "title": title,
        "price_current": price_current,
        "in_stock": in_stock,
        "captured_at": captured_at,
    }


async def scrape_store(context: BrowserContext, skus: list[str], store: dict[str, str]) -> list[dict[str, Any]]:
    page = await context.new_page()
    await try_set_store_context(page, store["store_id"])

    results: list[dict[str, Any]] = []
    for sku in skus:
        item = await extract_item(page, sku, store)
        results.append(item)
        await asyncio.sleep(THROTTLE_SECONDS)

    await page.close()
    return results


async def main() -> None:
    skus = load_skus(INPUT_SKUS)
    stores = load_stores(INPUT_STORES)

    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = SNAPSHOTS_DIR / today
    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="fr-CA")

        for store in stores:
            print(f"[INFO] Scraping store {store['store_id']} ({store['store_slug']})")
            results = await scrape_store(context, skus, store)

            out_file = output_dir / f"{store['store_slug']}.json"
            out_file.write_text(
                json.dumps(results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[OK] Wrote {out_file}")

        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
