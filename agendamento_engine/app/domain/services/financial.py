from decimal import Decimal, ROUND_HALF_UP

def calculate_commission(service_price: Decimal, percentage: Decimal) -> Decimal:
    return (service_price * percentage / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_net_value(service_price: Decimal, commission: Decimal) -> Decimal:
    return (service_price - commission).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)