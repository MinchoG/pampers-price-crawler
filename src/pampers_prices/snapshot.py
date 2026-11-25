"""Generate the static Diaperhunt catalogue from the local comparison engine."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from playwright.async_api import async_playwright

from .compare import rank_offers, scan
from .crawler import STORES, browser_launch_options


async def refresh():
    catalogue = {str(size): [] for size in range(9)}
    coverage = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(**browser_launch_options())
        async def shop(store):
            for size in range(9):
                args = SimpleNamespace(category="diapers", query="Pampers Premium Care",
                                       size=size, max_pages=2, product_url=[])
                rows, messages = await scan(browser, store, args)
                coverage.setdefault(store.name, {})[size] = messages
                for rate, price, pieces, title, name, url, _ in rank_offers([(rows, messages)]):
                    if url.startswith("https://"):
                        catalogue[str(size)].append(dict(store=name, price=float(price), pieces=pieces,
                                                         unit=float(rate), title=title, url=url))
        try:
            await asyncio.gather(*(shop(store) for store in STORES))
        finally:
            await browser.close()
    for offers in catalogue.values():
        offers.sort(key=lambda o: (o["unit"], -o["pieces"], o["store"]))
    if not any(catalogue.values()):
        raise RuntimeError("No offers found; keeping previous snapshot")
    data = dict(updated=datetime.now(timezone.utc).isoformat(), sizes=catalogue, stores=list(coverage))
    target = Path("diaperhunt/offers.json")
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temp.replace(target)
    print({size: len(rows) for size, rows in catalogue.items()})


if __name__ == "__main__":
    asyncio.run(refresh())
