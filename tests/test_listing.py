from decimal import Decimal

from bs4 import BeautifulSoup
from pampers_prices.compare import listing_offer


def test_listing_calculation_stays_with_its_product():
    soup = BeautifulSoup("""
      <section><article><a href="/a">Premium Care</a>
      <span>13,20 €</span><button>Добави в кошницата</button></article>
      <article><a href="/b">Another pack</a></article></section>
    """, "html.parser")
    first, second = soup.select("a")
    assert listing_offer(first, first.text, 50)[:2] == (Decimal("0.264"), Decimal("13.20"))
    assert listing_offer(second, second.text, 156) is None
