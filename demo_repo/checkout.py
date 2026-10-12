FREE_SHIPPING_THRESHOLD = 50
SHIPPING_FEE = 8

def shipping_fee(total: float) -> int:
    if total > FREE_SHIPPING_THRESHOLD:
        return 0
    return SHIPPING_FEE