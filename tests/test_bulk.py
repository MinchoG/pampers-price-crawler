from decimal import Decimal

from pampers_prices.compare import rank_offers


def test_bulk_price_and_sale_order():
    def offer(price, count):
        price = Decimal(price)
        return (price / count, price, count, "Pack", "Shop", f"/{count}", "keyword")
    bulk = offer("42", 156)
    regular = offer("14.05", 50)
    sale = offer("13.01", 50)
    assert rank_offers([([regular, bulk], [])]) == [bulk, regular]
    assert rank_offers([([bulk, sale], [])]) == [sale, bulk]
