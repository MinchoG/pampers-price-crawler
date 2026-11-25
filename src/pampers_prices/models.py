from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Offer:
    store: str
    title: str
    size: int
    pieces: int
    price_eur: Decimal
    url: str
    available: bool = True

    @property
    def price_per_piece(self) -> Decimal:
        return self.price_eur / self.pieces

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["price_eur"] = float(self.price_eur)
        result["price_per_piece_eur"] = float(self.price_per_piece)
        return result

