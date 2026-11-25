from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from .crawler import STORES, crawl
from .models import Offer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank Pampers packs by euro price per diaper.")
    parser.add_argument("--query", required=True, help='product or brand phrase, e.g. "Pampers Premium Care"')
    parser.add_argument("--size", type=int, required=True, choices=range(0, 9), metavar="N")
    parser.add_argument("--limit", type=int, default=20, help="maximum ranked offers to print")
    parser.add_argument("--timeout", type=int, default=25, help="navigation timeout per page in seconds")
    parser.add_argument("--max-pages", type=int, default=3, choices=range(1, 51), metavar="1-50")
    parser.add_argument("--search-size", action="store_true", help="also append the size to store search terms")
    parser.add_argument("--json", dest="json_path", type=Path, help="also save results as JSON")
    return parser


def render(offers: list[Offer], size: int, limit: int) -> str:
    chosen = offers[:limit]
    if not chosen:
        return f"No available Pampers size {size} offers were found."
    headers = ("#", "Store", "Pack", "Price", "€/piece", "Product")
    rows = [
        (str(rank), o.store, str(o.pieces), f"€{o.price_eur:.2f}", f"€{o.price_per_piece:.4f}", o.title)
        for rank, o in enumerate(chosen, 1)
    ]
    widths = [max(len(row[i]) for row in [headers, *rows]) for i in range(len(headers))]
    lines = ["  ".join(value.ljust(widths[i]) for i, value in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)) for row in rows)
    lines.append("\nLinks:")
    lines.extend(f"{i}. {offer.url}" for i, offer in enumerate(chosen, 1))
    return "\n".join(lines)


def main() -> None:
    args = build_parser().parse_args()
    offers, errors = asyncio.run(crawl(
        args.query, args.size, args.timeout, max_pages=args.max_pages, search_size=args.search_size
    ))
    print(render(offers, args.size, args.limit))
    counts = Counter(offer.store for offer in offers)
    search_query = f"{args.query} {args.size}" if args.search_size else args.query
    print(f"\nStore searches for {search_query!r}, size {args.size}, up to {args.max_pages} pages per store")
    for store in STORES:
        count = counts[store.name]
        if store.name in errors:
            status = f"Search error: {errors[store.name]} ({count} offers parsed)"
        elif count:
            status = f"{count} matching offer(s) parsed before display limit"
        else:
            status = "No matching offers parsed. Check the search page directly."
        print(f"- {store.name}: {status}\n  {store.url_for(search_query)}")
    if args.json_path:
        args.json_path.write_text(
            json.dumps([offer.as_dict() for offer in offers], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()

