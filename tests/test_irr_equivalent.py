from exchange_money_bot.services.irr_fiat_rates import rial_equivalent


def test_rial_equivalent_usd() -> None:
    assert rial_equivalent(10, "USD", usd_rial=50_000, eur_rial=55_000) == 500_000


def test_rial_equivalent_eur() -> None:
    assert rial_equivalent(2, "EUR", usd_rial=50_000, eur_rial=60_000) == 120_000


def test_rial_equivalent_missing_rate() -> None:
    assert rial_equivalent(1, "USD", usd_rial=None, eur_rial=1) is None
    assert rial_equivalent(1, "XXX", usd_rial=1, eur_rial=1) is None
