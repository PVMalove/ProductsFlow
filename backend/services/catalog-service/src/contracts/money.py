"""Money-конвертация для контрактов catalog (ADR 0016: RUB — целые копейки).

`Product.price` в домене остаётся `float`-рублями (issue #366 не мигрирует
схему) — эта функция конвертирует на границе контракта, а не хранимые
данные."""

from decimal import ROUND_HALF_UP, Decimal


def rubles_to_kopecks(price: float) -> int:
    """Конвертирует рубли (float) в целые копейки через `Decimal(str(price))`,
    не `round(price * 100)` — избегает float-дрейфа на деньгах. Половина
    копейки округляется вверх (`ROUND_HALF_UP`)."""
    kopecks = (Decimal(str(price)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(kopecks)
