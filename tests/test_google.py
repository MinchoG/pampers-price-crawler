import io
import json
from urllib.parse import parse_qs, urlsplit

from pampers_prices import compare


def test_google_bg_reads_six_organic_links_in_order(monkeypatch):
    urls = [f"https://shop{i}.bg/product" for i in range(9)]
    def respond(url, timeout):
        params = parse_qs(urlsplit(url).query)
        assert params["gl"] == params["hl"] == ["bg"]
        return io.BytesIO(json.dumps({"ads": [{"link": "https://ad.example"}],
                                     "organic_results": [{"link": u} for u in urls]}).encode())
    monkeypatch.setenv("SERPAPI_API_KEY", "test")
    monkeypatch.setattr(compare, "urlopen", respond)
    assert compare.google_links("Pampers Premium Care размер 1") == urls[:6]
