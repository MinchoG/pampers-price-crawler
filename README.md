# Pampers Price Crawler

Browse [Diaperhunt](https://diaperhunt.mincho.dev) for Pampers Premium Care prices by size in Bulgaria. Run the local tool to compare other diaper ranges by price per piece or coffee by price per kilogram.

Configured retailers include Ozone, eMAG, Galen, SOpharmacy, dm, Notino,
Pipi Market, Lilly Drogerie, Remedium, eBag, Vis Vitalis, Apteki 36.6,
Raya Toys, Baby.bg and Bubu.bg. Several discovery routes use diaper or Pampers catalogues.

Diaperhunt can make mistakes. Confirm prices, quantities and availability with
the retailer before ordering. No retailer or other website funds its creator.

## Install

### Diaperhunt snapshot site

`diaperhunt/` contains a static Bulgarian price comparison for Pampers Premium
Care in sizes 0–8. Selecting a size reads the same snapshot for every visitor.
To refresh locally from the installed environment, run
`python -m pampers_prices.snapshot` from the repository root. Serve it with
`python -m http.server 8080 --directory diaperhunt` and open localhost:8080.
The production site uses a separate private repository for its daily refresh
and deployment. The bundled snapshot lets you preview this public version locally.
The CLI below also supports your own keywords and retailer URLs.

### Double-click price check (Mac and Windows)

Download the repository using **Code → Download ZIP**, then extract it
into a folder you plan to keep. You need Python 3.11 or
newer. On Mac open **Check diaper prices.command**. On Windows open
**Check diaper prices.bat**. First use installs the crawler and its browser
dependencies and requires internet access. Press Enter twice for Pampers
Premium Care size 1, or enter another brand and size. Open the same file
whenever you want fresh prices. If your Mac lacks execute permission after
extracting the ZIP, use the terminal installation below.

### Terminal installation

Python 3.11 or newer is required.

```bash
git clone https://github.com/MinchoG/pampers-price-crawler.git
cd pampers-price-crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium  # optional when Google Chrome is already installed
```

For an existing checkout, start in the project directory and skip the clone.
On Windows PowerShell use `py -3 -m venv .venv` and `.\.venv\Scripts\Activate.ps1`.
On Linux, use `playwright install --with-deps chromium` if system browser libraries are missing.
Verify installation with `price-check --help` and `python -m pytest -q`.

## price-check parameters

| Option | Purpose |
| --- | --- |
| `--category diapers\|coffee` | Required. Compare by diaper or kilogram. |
| `--query TEXT` | Required product or brand phrase. Quote multiword names. |
| `--size N` | Required for diapers, 0–8. |
| `--unit diaper\|kg` | Optional explicit unit matching the category. |
| `--sites all` or `--sites dm,eMAG` | Choose configured retailers by name or domain. Interactive runs prompt if omitted. |
| `--search-url URL` | Add a results or category page for this run. Use `{query}` or `{query_plus}` for a reusable search pattern. Repeatable. |
| `--product-url URL` | Check an HTTPS product page directly, including at a new retailer. Repeatable. |
| `--max-pages N` | Search page cap per route, 1–50, default 3. |
| `--google` | Try six organic Bulgarian Google results. Uses SerpApi if `SERPAPI_API_KEY` is set. Otherwise tries the local browser and offers manual URL input in an interactive terminal if blocked. |
| `--web` | Enable Brave discovery using `BRAVE_SEARCH_API_KEY`. Choose either this or Google. |
| `--location TEXT` | Location text for Brave queries, default София България. Google mode targets Bulgaria. |

## Run

The category-based CLI searches for candidate links and checks individual product
pages for matching quantities, an in-stock offer, and a price in EUR.

```bash
price-check --category diapers --query "Pampers Premium Care" --size 1
price-check --category coffee --query "Lavazza Qualità Oro" --unit kg
price-check --category diapers --query "Pampers Active Baby" --size 4 --sites dm,Galen
```

### Include another store

Open the retailer in your browser, search for the product, and copy the results
URL. Supply it with `--search-url`. A category page also works. This example
checks dm and adds the Pipi Market product catalogue to the same comparison:

```bash
price-check --category diapers --query "Pampers Premium Care" --size 2 --sites dm \
  --search-url 'https://www.pipimarket.bg/seria/pampers-premium-care/'
```

For a reusable search, replace the search words in the retailer's actual URL
with `{query}`, for example `--search-url 'https://galen.bg/catalogsearch/result/?q={query}'`.
If you have the exact product link, use `--product-url`:

```bash
price-check --category diapers --query "Pampers Premium Care" --size 1 --sites Galen \
  --product-url 'https://www.dm-drogeriemarkt.bg/p/d/2705091/pampers-premium-care-peleni-razmer-1-2-5-kg'
```

Repeat either option to include more URLs. Custom URLs apply to that run.
For a permanent addition, register a `Store` in `src/pampers_prices/crawler.py`.
New retailers may need a parser for their price, availability, or pack format.

Use `--sites all` for a non-interactive store selection.
Diaper discovery includes an XXL pack search. Rankings use the full pack price
divided by the total diaper count, before shipping. Larger packs win exact ties.
For local web discovery beyond the selected stores, set `BRAVE_SEARCH_API_KEY`
and add `--web --location "София България"`. This initial market uses Bulgarian
search terms and verifies EUR offers.
The verifier currently reads Product JSON-LD. Pages lacking usable structured
offers appear as unverified when a candidate link is available.

```bash
pampers-prices --query "Pampers" --size 1
```

Useful options:

```bash
pampers-prices --query "Pampers Premium Care" --size 1 --limit 10 --json results-size-1.json
```

`--query` is sent to every store's search page and is also checked against product titles. `--size` is a strict filter applied after searching. The ranking excludes out-of-stock products, baby wipes, and products whose size cannot be verified. Price per piece is calculated as `current pack price / number of diapers`.

## Notes

### Browser and pricing

- Websites change their HTML periodically. The parser first uses structured product data and then falls back to common product-card markup.
- The crawler uses installed Google Chrome on macOS when available. Set `PAMPERS_CRAWLER_BROWSER=/path/to/browser` to override it.
- Prices exclude delivery charges and loyalty/app-only discounts unless the displayed current price includes them.
- Crawling may be restricted by a store's terms or anti-bot controls. Use a modest frequency and review each store's terms before scheduling it.
- One failing store does not stop the remaining stores; failures appear as warnings.

## Test

To propose a change, fork this repository, commit on a feature branch, and
open a pull request against `main`. For retailer changes include a product
or search link and the expected pack quantity and price calculation.

```bash
pytest
```

