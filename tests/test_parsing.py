from decimal import Decimal

from pampers_prices.parsing import extract_count, extract_price, extract_size, parse_offers


def test_extracts_pack_count_and_size():
    title = "Пелени Pampers Premium Care Размер 1, 2-5 kg, 72 броя"
    assert extract_size(title) == 1
    assert extract_count(title) == 72


def test_multiplies_multipack_count():
    assert extract_count("Pampers пелени размер 1, 3 x 48 бр") == 144


def test_prefers_euro_price_on_dual_currency_page():
    assert extract_price("13,01 € 25,45 лв.") == Decimal("13.01")


def test_parses_jsonld_and_rejects_wipes_and_wrong_size():
    html = '''
    <script type="application/ld+json">
    {"@context":"https://schema.org","@graph":[
      {"@type":"Product","name":"Пелени Pampers Premium Care Размер 1 x50 броя","url":"/p1",
       "offers":{"price":"13.20","availability":"https://schema.org/InStock"}},
      {"@type":"Product","name":"Pampers мокри кърпички размер 1 x60 броя","url":"/w1",
       "offers":{"price":"3.20","availability":"https://schema.org/InStock"}},
      {"@type":"Product","name":"Пелени Pampers Premium Care Размер 2 x72 броя","url":"/p2",
       "offers":{"price":"16.20","availability":"https://schema.org/InStock"}}
    ]}
    </script>
    '''
    offers = parse_offers(html, "Shop", "https://shop.example", "Pampers Premium Care", 1)
    assert len(offers) == 1
    assert offers[0].pieces == 50
    assert offers[0].price_per_piece == Decimal("0.264")
    assert offers[0].url == "https://shop.example/p1"


def test_product_card_prefers_final_price_over_old_price():
    html = '''
    <form class="product-item">
      <a class="product-item-link" href="/p1">Пелени Pampers Harmonie Размер 1 New born 50 бр</a>
      <span data-price-amount="17.65" data-price-type="oldPrice">17.65 €</span>
      <span data-price-amount="12.18" data-price-type="finalPrice">12.18 €</span>
      <button>Добави в количка</button>
    </form>
    '''
    offers = parse_offers(html, "Galen", "https://galen.bg", "Pampers", 1)
    assert len(offers) == 1
    assert offers[0].price_eur == Decimal("12.18")
    assert offers[0].price_per_piece == Decimal("0.2436")

