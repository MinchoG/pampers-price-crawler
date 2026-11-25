"""Discover retailer links, then compare verified product-page offers."""
import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from decimal import Decimal
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.parse import quote_plus, urljoin, urlsplit, urldefrag

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .crawler import STORES, Store, browser_launch_options
from .parsing import PRICE_RE, UNAVAILABLE, _jsonld_items, extract_count, is_matching_diaper, parse_decimal


def quantity(title, args):
    if args.category == "diapers":
        if is_matching_diaper(title, args.query, args.size):
            # Remove size before counting: "Размер 2 x50 бр" is a 50-pack.
            return extract_count(re.sub(r"(?:размер|size|\bS)\s*\d+", "", title, flags=re.I))
        return None
    if not all(word in title.casefold() for word in args.query.casefold().split()):
        return None
    weights = re.findall(r"(?:(\d+)\s*[xх×]\s*)?(\d+(?:[.,]\d+)?)\s*(kg|кг|g|гр|г)\b", title, re.I)
    if len(weights) == 1:
        packs, weight, unit = weights[0]
        return Decimal(packs or 1) * parse_decimal(weight) / (1 if unit.lower() in ("kg", "кг") else 1000)
    return None


async def read(page, url):
    response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    if response and response.status >= 400:
        raise ValueError(f"HTTP {response.status}")
    return BeautifulSoup(await page.content(), "html.parser")


def listing_offer(link, title, amount):
    """Keep price and purchase controls inside the same product card."""
    for card in link.parents:
        if card.name in ("body", "html"):
            break
        if any(a["href"] != link["href"] for a in card.select("a[href]")):
            break
        text = card.get_text(" ", strip=True)
        if UNAVAILABLE.search(text):
            return None
        if not re.search(r"Добави в (?:кошницата|количка)", text, re.I):
            continue
        final = card.select_one('[data-price-type="finalPrice"][data-price-amount]')
        prices = PRICE_RE.findall(text)
        if final and "€" in final.get_text():
            price = parse_decimal(final["data-price-amount"])
        elif len(prices) == 1:
            price = parse_decimal(prices[0])
        else:
            return None
        if price and price > 0:
            return price / amount, price, amount, title
    return None


def verify(soup, args):
    for product in _jsonld_items(soup):
        if product.get("@type") != "Product":
            continue
        title = str(product.get("name", ""))
        amount = quantity(title, args)
        if not amount:
            continue
        offers = product.get("offers", [])
        for offer in offers if isinstance(offers, list) else [offers]:
            if not isinstance(offer, dict) or str(offer.get("availability", "")).split("/")[-1] != "InStock":
                continue
            price = parse_decimal(str(offer.get("price", "")))
            if price and price.is_finite() and price > 0 and offer.get("priceCurrency") == "EUR":
                yield price / amount, price, amount, title


async def scan(browser, store, args):
    page = await browser.new_page(locale="bg-BG")
    host = urlsplit(store.base_url).hostname.removeprefix("www.")
    def belongs(url):
        parts = urlsplit(url)
        return parts.scheme == "https" and (parts.hostname or "").removeprefix("www.") == host

    candidates = defaultdict(set)
    for url in args.product_url:
        if belongs(url):
            candidates[urldefrag(url).url].add("provided link")
    issues = []
    rows = []
    listings = {}
    routes = {"keyword": store.url_for(args.query)} if store.search_url else {}
    if args.category == "diapers" and "{query" in store.search_url:
        routes["size keyword"] = store.url_for(f"{args.query} {args.size}")
        routes["bulk pack"] = store.url_for(f"{args.query} XXL {args.size}")
        if store.name == "Ozone" and "pampers" in args.query.lower():
            routes["diaper catalogue"] = store.base_url + "/group-peleni-za-ednokratna-upotreba-pampers/"
    if store.name == "eMAG" and args.category == "diapers" and args.size == 1:
        if " ".join(args.query.casefold().split()) == "pampers premium care":
            known = store.base_url + "/peleni-pampers-premium-care-xxl-box-newborn-razmer-1-2-5-kg-156-br-8700216346757/pd/DTD6NKYBM/"
            candidates[known].add("known eMAG 156-pack")
        routes["size filter"] = (
            f"{store.base_url}/search/peleni-gashtichki/filter/razmer-f7988,1-v26552/"
            f"{quote_plus(args.query.lower())}/c?ref=lst_leftbar_7988_26552"
        )
    async def discover(route, url):
        visited = set()
        for _ in range(args.max_pages):
            visited.add(url)
            soup = await read(page, url)
            if store.name == "dm":
                try:
                    await page.locator('a[href*="/p/d/"]').first.wait_for(state="attached", timeout=6000)
                except Exception:
                    pass
                soup = BeautifulSoup(await page.content(), "html.parser")
                for summary in soup.find_all(string=re.compile(r";\s*Марка:")):
                    title, _, pricing = str(summary).partition("; Цена:")
                    amount = quantity(title, args)
                    price_match = PRICE_RE.search(pricing.split(";")[0])
                    if not amount or not price_match or "Налично за доставка" not in pricing:
                        continue
                    for parent in summary.parents:
                        urls = {urljoin(page.url, a["href"]) for a in parent.select('a[href*="/p/d/"]')}
                        if urls:
                            if len(urls) == 1:
                                target = urls.pop()
                                price = parse_decimal(price_match[1])
                                candidates[target].add(route)
                                listings[target] = (price / amount, price, amount, title)
                            break
            for link in soup.select("a[href]"):
                target = urldefrag(urljoin(page.url, link["href"])).url
                labels = (link.get("title", ""), link.get_text(" ", strip=True))
                if belongs(target):
                    for label in labels:
                        amount = quantity(label, args)
                        if amount:
                            candidates[target].add(route)
                            offer = listing_offer(link, label.strip(), amount)
                            if offer:
                                listings[target] = offer
                            break
            following = soup.select_one('a[rel="next"], a.action.next, .pagination a.next')
            url = urljoin(page.url, following.get("href", "")) if following else ""
            if not belongs(url) or url in visited:
                break
    try:
        if store.name == "eMAG" and args.category == "diapers" and "pampers" in args.query.lower():
            brand = store.base_url + "/peleni-gashtichki/brand/Pampers/"
            if args.size == 1:
                routes["brand and size"] = brand + "filter/razmer-f7988,1-v26552/c"
            else:
                try:
                    filters = await read(page, brand + "c")
                    pattern = rf"/filter/razmer-f7988,{args.size}-v\d+/c/?$"
                    for anchor in filters.select("a[href]"):
                        target = urljoin(brand, anchor["href"])
                        if belongs(target) and re.search(pattern, urlsplit(target).path):
                            routes["brand and size"] = target
                            break
                    else:
                        issues.append(f"eMAG size {args.size}: no matching filter link exposed")
                except Exception as exc:
                    issues.append(f"eMAG size {args.size} filter discovery: {str(exc).splitlines()[0]}")
        for route, start in routes.items():
            try:
                await discover(route, start)
            except Exception as exc:
                issues.append(f"{store.name} {route}: {str(exc).splitlines()[0]} — {start}")
        for url in sorted(candidates):
            sources = ", ".join(sorted(candidates[url]))
            if url in listings:
                rows.append((*listings[url], store.name, url, sources))
                continue
            try:
                matches = list(verify(await read(page, url), args))
                if matches:
                    rows.append((*min(matches), store.name, url, sources))
                else:
                    issues.append(f"Unverified product — {url}")
            except Exception as exc:
                issues.append(f"Unverified product ({str(exc).splitlines()[0]}) — {url}")
    finally:
        await page.close()
    return rows, [f"{store.name}: {len(candidates)} candidate links", *issues]


def google_links(query):
    params = urlencode({"engine": "google", "q": query, "google_domain": "google.bg",
                        "gl": "bg", "hl": "bg", "location": "Bulgaria",
                        "api_key": os.environ["SERPAPI_API_KEY"]})
    with urlopen("https://serpapi.com/search.json?" + params, timeout=20) as response:
        data = json.load(response)
    if data.get("error"):
        raise ValueError("Google search provider reported an error")
    return [item["link"] for item in data.get("organic_results", [])[:6] if item.get("link")]


async def browser_google_links(page, query):
    url = "https://www.google.bg/search?" + urlencode({"q": query, "hl": "bg", "gl": "bg", "pws": 0})
    print(f"Google Bulgaria search — {url}", flush=True)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        headings = page.locator("#rso a[href] h3")
        await headings.first.wait_for(timeout=5000)
        links = await headings.evaluate_all("""nodes => nodes.flatMap(node => {
          const a = node.closest('a');
          if (a.closest('[data-text-ad], [data-ta-slot], #tads, #bottomads, [data-pla-slot]')) return [];
          const u = new URL(a.href);
          return u.protocol === 'https:' && !/(^|\\.)google\\.[a-z.]+$/.test(u.hostname) ? [u.href] : [];
        })""")
        if links:
            return list(dict.fromkeys(links))[:6]
    except Exception:
        pass
    print("Google did not expose readable organic links in this browser.")
    if sys.stdin.isatty():
        raw = await asyncio.to_thread(input, "Open the search above and paste up to six organic product URLs (space-separated), or press Enter to skip: ")
        return list(dict.fromkeys(u for u in raw.split() if u.startswith("https://")))[:6]
    return []


def web_links(query):
    params = urlencode({"q": query, "count": 10, "search_lang": "bg"})
    request = Request("https://api.search.brave.com/res/v1/web/search?" + params,
                      headers={"X-Subscription-Token": os.environ["BRAVE_SEARCH_API_KEY"]})
    with urlopen(request, timeout=15) as response:
        return [item["url"] for item in json.load(response).get("web", {}).get("results", [])]


async def web_report(browser, args):
    page = await browser.new_page(locale="bg-BG")
    rows, messages = [], []
    visited = set()
    try:
        phrase = f"{args.query} {args.location}"
        queries = [phrase]
        if args.category == "diapers":
            queries = [f"{phrase} пелени размер {args.size}", f"{phrase} XXL размер {args.size}"]
        if args.google:
            queries = [args.query + (f" размер {args.size}" if args.category == "diapers" else "")]
        for query in queries:
            try:
                if args.google and not os.environ.get("SERPAPI_API_KEY"):
                    links = await browser_google_links(page, query)
                else:
                    links = await asyncio.to_thread(google_links if args.google else web_links, query)
            except Exception as exc:
                messages.append(f"Web search failed ({type(exc).__name__})")
                continue
            for url in links:
                if url in visited or urlsplit(url).scheme != "https":
                    continue
                visited.add(url)
                if args.google:
                    messages.append(f"Google organic result — {url}")
                try:
                    matches = list(verify(await read(page, url), args))
                    if matches:
                        host = urlsplit(url).hostname
                        name = next((s.name for s in STORES if urlsplit(s.base_url).hostname.removeprefix("www.") == host.removeprefix("www.")), host)
                        rows.append((*min(matches), name, url, "Google organic" if args.google else "web search"))
                except Exception as exc:
                    messages.append(f"Web result {url}: {str(exc).splitlines()[0]}")
    finally:
        await page.close()
    return rows, [f"Web search: {len(visited)} links checked", *messages]


def rank_offers(reports):
    merged = {}
    for rows, _ in reports:
        for row in rows:
            key = row[5], row[1], row[2]
            if key in merged:
                sources = sorted(set((merged[key][-1] + ", " + row[-1]).split(", ")))
                row = (*row[:-1], ", ".join(sources))
            merged[key] = row
    return sorted(merged.values(), key=lambda row: (row[0], -row[2], row[4]))


async def run(args):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(**browser_launch_options())
        try:
            tasks = [scan(browser, store, args) for store in args.stores]
            if args.web or args.google:
                tasks.append(web_report(browser, args))
            reports = await asyncio.gather(*tasks)
        finally:
            await browser.close()
    unit = "kg" if args.category == "coffee" else "diaper"
    ranked = rank_offers(reports)
    if ranked:
        print(f"\n{args.query}  ·  lowest price per {unit} first")
        print(f"{'Rank':4}  {'Store':12}  {'Pack':>8}  {'Price':>9}  {'€/' + unit:>10}  Product")
    for rank, (rate, price, amount, title, store, url, sources) in enumerate(ranked, 1):
        print(f"{rank:4}  {store:12}  {amount:>8}  €{price:8.2f}  {rate:10.4f}  {title}")
        print(f"      Found via {sources} · {url}")
    if not any(rows for rows, _ in reports):
        print("No verified offers to rank.")
    print("\nSearch coverage")
    for _, messages in reports:
        print("\n".join(messages))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--category", choices=["diapers", "coffee"], required=True)
    parser.add_argument("--size", type=int, choices=range(9))
    parser.add_argument("--unit", choices=["kg", "diaper"])
    parser.add_argument("--product-url", action="append", default=[])
    parser.add_argument("--search-url", action="append", default=[],
                        help="Add an HTTPS results page or search URL with {query}; repeat for more shops")
    discovery = parser.add_mutually_exclusive_group()
    discovery.add_argument("--web", action="store_true", help="also discover retailers via Brave Search")
    discovery.add_argument("--google", action="store_true", help="check the first six organic Google Bulgaria results")
    parser.add_argument("--location", default="София България", help="location for web discovery")
    parser.add_argument("--sites", help="comma-separated store names or domains, or all")
    parser.add_argument("--max-pages", type=int, choices=range(1, 51), default=3)
    args = parser.parse_args()
    if args.web and not os.environ.get("BRAVE_SEARCH_API_KEY"):
        parser.error("--web requires BRAVE_SEARCH_API_KEY")
    selection = args.sites
    choices = ", ".join(store.name for store in STORES)
    if selection is None and sys.stdin.isatty():
        selection = input(f"Websites to search ({choices}; Enter for all): ")
    selected = []
    for value in (selection or "all").split(","):
        key = value.strip().lower()
        if key == "lily":
            key = "lilly"
        if key == "all":
            selected.extend(STORES)
            continue
        domain = urlsplit(key if "://" in key else "//" + key).hostname
        matches = [s for s in STORES if key == s.name.lower() or
                   (domain or "").removeprefix("www.") == urlsplit(s.base_url).hostname.removeprefix("www.")]
        if not matches:
            parser.error(f"Unsupported website: {value}. Choose from {choices}.")
        selected.extend(matches)
    args.stores = list(dict.fromkeys(selected))
    for url in [*args.search_url, *args.product_url]:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            parser.error("Provide a full HTTPS store URL.")
        if url in args.search_url and parts.path in ("", "/") and not parts.query:
            parser.error("--search-url needs a results or category page. Search the shop first and copy the URL.")
        if re.search(r"[{}]", url.replace("{query}", "").replace("{query_plus}", "")):
            parser.error("Supported search placeholders are {query} and {query_plus}.")
        domain = parts.hostname.removeprefix("www.")
        if url in args.search_url or not any(urlsplit(s.base_url).hostname.removeprefix("www.") == domain for s in args.stores):
            args.stores.append(Store(domain, f"https://{parts.netloc}", url if url in args.search_url else ""))
    if args.category == "diapers" and args.size is None:
        parser.error("diapers require --size")
    if args.unit and args.unit != {"coffee": "kg", "diapers": "diaper"}[args.category]:
        parser.error("unit does not match category")
    asyncio.run(run(args))
