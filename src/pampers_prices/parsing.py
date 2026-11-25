from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .models import Offer

PRICE_RE = re.compile(r"(?<!\d)(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:€|EUR|евро)", re.I)
LEV_PRICE_RE = re.compile(r"(?<!\d)(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:лв\.?|BGN)", re.I)
COUNT_PATTERNS = (
    re.compile(r"(?:x|х|×)\s*(\d{1,3})\s*(?:бр(?:оя)?\.?)?", re.I),
    re.compile(r"(\d{1,3})\s*(?:бр(?:оя)?\.?|pieces?|pcs?)", re.I),
)
SIZE_PATTERNS = (
    re.compile(r"(?:размер|size|номер|№|S)\s*[-:]?\s*(\d)", re.I),
    re.compile(r"\b(\d)\s*(?:new\s*born|newborn)\b", re.I),
)
UNAVAILABLE = re.compile(r"изчерпан|няма\s+наличност|out\s+of\s+stock|unavailable", re.I)
DIAPER_WORD = re.compile(r"пелен|diaper", re.I)
WIPES_WORD = re.compile(r"кърп|wipe", re.I)


def parse_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None


def extract_price(text: str) -> Decimal | None:
    """Prefer the first euro price; Bulgaria's fixed conversion handles BGN-only pages."""
    prices = [parse_decimal(value) for value in PRICE_RE.findall(text)]
    if prices:
        return next((p for p in prices if p is not None), None)
    lev_prices = [parse_decimal(value) for value in LEV_PRICE_RE.findall(text)]
    lev = next((p for p in lev_prices if p is not None), None)
    return (lev / Decimal("1.95583")) if lev is not None else None


def extract_count(title: str) -> int | None:
    matches: list[int] = []
    for pattern in COUNT_PATTERNS:
        matches.extend(int(value) for value in pattern.findall(title))
    # Multipacks such as 3 x 48 should represent the total number of diapers.
    multi = re.search(r"(\d{1,2})\s*[xх×]\s*(\d{1,3})\s*(?:бр(?:оя)?\.?)?", title, re.I)
    if multi:
        return int(multi.group(1)) * int(multi.group(2))
    return matches[-1] if matches else None


def extract_size(title: str) -> int | None:
    for pattern in SIZE_PATTERNS:
        match = pattern.search(title)
        if match:
            return int(match.group(1))
    return None


def is_matching_diaper(title: str, search_term: str, requested_size: int) -> bool:
    wanted_words = [word.casefold() for word in re.findall(r"[\w-]+", search_term) if len(word) > 1]
    folded_title = title.casefold()
    return (
        bool(wanted_words)
        and all(word in folded_title for word in wanted_words)
        and bool(DIAPER_WORD.search(title))
        and not bool(WIPES_WORD.search(title))
        and extract_size(title) == requested_size
    )


def _jsonld_items(soup: BeautifulSoup):
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                yield item
                stack.extend(v for v in item.values() if isinstance(v, (dict, list)))


def parse_jsonld(
    html: str, store: str, base_url: str, search_term: str, requested_size: int
) -> list[Offer]:
    soup = BeautifulSoup(html, "html.parser")
    offers: list[Offer] = []
    for item in _jsonld_items(soup):
        if item.get("@type") != "Product":
            continue
        title = str(item.get("name", ""))
        if not is_matching_diaper(title, search_term, requested_size):
            continue
        offer_data = item.get("offers", {})
        if isinstance(offer_data, list):
            offer_data = offer_data[0] if offer_data else {}
        if not isinstance(offer_data, dict):
            continue
        price = parse_decimal(str(offer_data.get("price", "")))
        pieces = extract_count(title)
        url = item.get("url") or offer_data.get("url") or base_url
        availability = str(offer_data.get("availability", ""))
        if price and pieces and "OutOfStock" not in availability:
            offers.append(Offer(store, title, requested_size, pieces, price, urljoin(base_url, str(url))))
    return offers


def parse_product_cards(
    html: str, store: str, base_url: str, search_term: str, requested_size: int
) -> list[Offer]:
    """Fallback for stores whose listing cards do not provide Product JSON-LD."""
    soup = BeautifulSoup(html, "html.parser")
    selectors = (
        "[data-testid*='product']", ".product-item", ".product-box", ".card-item",
        ".product", "article", "li.item.product",
    )
    seen: set[tuple[str, Decimal, int]] = set()
    results: list[Offer] = []
    for selector in selectors:
        for card in soup.select(selector):
            if not isinstance(card, Tag):
                continue
            text = " ".join(card.get_text(" ", strip=True).split())
            if not is_matching_diaper(text, search_term, requested_size) or UNAVAILABLE.search(text):
                continue
            title_node = card.select_one("h1, h2, h3, h4, [class*='title'], a[title]")
            title = (title_node.get("title") if title_node and title_node.get("title") else
                     title_node.get_text(" ", strip=True) if title_node else text[:240])
            pieces = extract_count(title) or extract_count(text)
            # Prefer machine-readable current/final price attributes. This avoids
            # selecting an old price or discount percentage from a sale card.
            price_node = card.select_one(
                '[data-price-type="finalPrice"][data-price-amount], '
                '[data-price-type="finalPrice"] [data-price-amount], '
                '[itemprop="price"][content], meta[itemprop="price"]'
            )
            price_raw = None
            if price_node:
                price_raw = price_node.get("data-price-amount") or price_node.get("content")
            price = parse_decimal(str(price_raw)) if price_raw is not None else extract_price(text)
            link = card.select_one("a[href]")
            url = urljoin(base_url, link.get("href", "")) if link else base_url
            if not pieces or not price:
                continue
            key = (url, price, pieces)
            if key not in seen:
                seen.add(key)
                results.append(Offer(store, title, requested_size, pieces, price, url))
        if results:
            break
    return results


def parse_offers(
    html: str, store: str, base_url: str, search_term: str, requested_size: int
) -> list[Offer]:
    by_key: dict[tuple[str, Decimal, int], Offer] = {}
    for offer in parse_jsonld(html, store, base_url, search_term, requested_size) + parse_product_cards(
        html, store, base_url, search_term, requested_size
    ):
        by_key[(offer.url, offer.price_eur, offer.pieces)] = offer
    return list(by_key.values())

