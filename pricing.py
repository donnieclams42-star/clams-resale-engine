import statistics

CONDITION_MULTIPLIERS = {
    "A":1.0,
    "B":0.85,
    "C":0.70,
    "Parts":0.50
}

def analyze_market(sold_prices,active_prices,condition,profit,local_factor):

    sold_prices=sorted(sold_prices)

    sold_median=statistics.median(sold_prices)

    multiplier=CONDITION_MULTIPLIERS.get(condition,1)

    adjusted=sold_median*multiplier
    local=adjusted*local_factor

    max_buy=local*(1-profit)
    sell_target=local/(1-profit)

    active_median=statistics.median(active_prices) if active_prices else 0

    return{
        "sold_median":round(sold_median,2),
        "active_median":round(active_median,2),
        "max_buy":round(max_buy,2),
        "sell_target":round(sell_target,2)
    }