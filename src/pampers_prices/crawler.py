from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, quote_plus, urljoin, urlsplit

from playwright.async_api import Browser, async_playwright

from .models import Offer
from .parsing import parse_offers


@dataclass(frozen=True, slots=True)
class Store:
    name: str
    base_url: str
    search_url: str

    def url_for(self, query: str) -> str:
        return self.search_url.format(query=quote(query, safe=""), query_plus=quote_plus(query))


STORES = (
    Store("Bubu.bg", "https://bubu.bg", "https://bubu.bg/vendor/pampers"),
    Store("Ozone", "https://www.ozone.bg", "https://www.ozone.bg/catalogsearch/result/?q={query}"),
    Store("eMAG", "https://www.emag.bg", "https://www.emag.bg/search/{query}?ref=effective_search"),
    Store("Galen", "https://galen.bg", "https://galen.bg/catalogsearch/result/?q={query_plus}"),
    Store("SOpharmacy", "https://sopharmacy.bg", "https://sopharmacy.bg/bg/sophSearch?text={query}"),
    Store("dm", "https://www.dm-drogeriemarkt.bg", "https://www.dm-drogeriemarkt.bg/search?query={query}"),
    Store("Notino", "https://www.notino.bg", "https://www.notino.bg/majka-i-dete/ednokratni-peleni/"),
    Store("Pipi Market", "https://www.pipimarket.bg", "https://www.pipimarket.bg/?s={query_plus}&post_type=product"),
    Store("Lilly", "https://lillydrogerie.bg", "https://lillydrogerie.bg/bebeta-i-deca/peleni-i-mokri-k-rpi/peleni"),
    Store("Remedium", "https://remedium.bg", "https://remedium.bg/search?query={query}"),
    Store("eBag", "https://ebag.bg", "https://ebag.bg/search?query={query}"),
    Store("Vis Vitalis", "https://visvitalis.bg", "https://visvitalis.bg/category/ednokratni-peleni-pampersi-gashchichki"),
    Store("36.6", "https://366.bg", "https://366.bg/products/brands/pampers"),
    Store("Raya Toys", "https://rayatoys.com", "https://rayatoys.com/pampers"),
    Store("Baby.bg", "https://www.baby.bg", "https://www.baby.bg/group-peleni-za-ednokratna-upotreba-pampers/"),
)


def browser_launch_options() -> dict[str, str]:
    """Use an explicit override, Playwright Chromium, or an installed macOS Chrome."""
    override = os.environ.get("PAMPERS_CRAWLER_BROWSER")
    if override:
        return {"executable_path": override}
    mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac_chrome.exists():
        return {"executable_path": str(mac_chrome)}
    return {}


async def crawl_store(
    browser: Browser, store: Store, query: str, size: int, timeout_ms: int,
    max_pages: int = 3, search_size: bool = False,
) -> tuple[list[Offer], str | None]:
    page = await browser.new_page(locale="bg-BG", extra_http_headers={"Accept-Language": "bg-BG,bg;q=0.9"})
    offers: dict[str, Offer] = {}
    url = store.url_for(f"{query} {size}" if search_size else query)
    visited: set[str] = set()
    try:
        for _ in range(max_pages):
            visited.add(url)
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if response is not None and response.status >= 400:
                return list(offers.values()), f"HTTP {response.status}"
            try:
                await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8_000))
            except Exception:
                pass
            for offer in parse_offers(await page.content(), store.name, store.base_url, query, size):
                offers.setdefault(offer.url, offer)
            next_link = page.locator('a[rel="next"], a.action.next, .pagination a.next').first
            href = await next_link.get_attribute("href") if await next_link.count() else None
            if not href:
                break
            url = urljoin(page.url, href)
            if url in visited or urlsplit(url).netloc != urlsplit(page.url).netloc:
                break
        return list(offers.values()), None
    except Exception as exc:
        return list(offers.values()), f"{type(exc).__name__}: {exc}"
    finally:
        await page.close()


async def crawl(
    query: str, size: int, timeout_seconds: int = 25, *, max_pages: int = 3,
    search_size: bool = False,
) -> tuple[list[Offer], dict[str, str]]:
    errors: dict[str, str] = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, **browser_launch_options())
        try:
            tasks = [
                crawl_store(browser, store, query, size, timeout_seconds * 1_000, max_pages, search_size)
                for store in STORES
            ]
            responses = await asyncio.gather(*tasks)
        finally:
            await browser.close()
    offers: list[Offer] = []
    for store, (found, error) in zip(STORES, responses, strict=True):
        offers.extend(found)
        if error:
            errors[store.name] = error
    return sorted(offers, key=lambda offer: (offer.price_per_piece, offer.price_eur)), errors

