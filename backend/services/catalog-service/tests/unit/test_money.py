from contracts.money import rubles_to_kopecks


def test_rubles_to_kopecks_converts_typical_price() -> None:
    assert rubles_to_kopecks(19.99) == 1999


def test_rubles_to_kopecks_converts_zero() -> None:
    assert rubles_to_kopecks(0.0) == 0


def test_rubles_to_kopecks_rounds_half_kopeck_up() -> None:
    assert rubles_to_kopecks(19.995) == 2000
