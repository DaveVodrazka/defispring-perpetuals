import asyncio
import datetime
import json
from starknet_py.contract import Contract
from starknet_py.net.full_node_client import FullNodeClient
import requests
import time

TIMESTAMP_NOW = time.time()
MATH_64 = 2**64
NODE_URL = "https://starknet-mainnet.public.blastapi.io"
LONG = 0
SHORT = 1


AMM_ADDRESS = 0x047472E6755AFC57ADA9550B6A3AC93129CC4B5F98F51C73E0644D129FD208D9

# pools
ETH_USDC_CALL = "eth-usdc-call"
ETH_USDC_PUT = "eth-usdc-put"
BTC_USDC_CALL = "btc-usdc-call"
BTC_USDC_PUT = "btc-usdc-put"
ETH_STRK_CALL = "eth-strk-call"
ETH_STRK_PUT = "eth-strk-put"
STRK_USDC_CALL = "strk-usdc-call"
STRK_USDC_PUT = "strk-usdc-put"

POOL_ADDRESSES = {
    ETH_USDC_CALL: 0x70CAD6BE2C3FC48C745E4A4B70EF578D9C79B46FFAC4CD93EC7B61F951C7C5C,
    ETH_USDC_PUT: 0x466E3A6731571CF5D74C5B0D9C508BFB71438DE10F9A13269177B01D6F07159,
    BTC_USDC_CALL: 0x35DB72A814C9B30301F646A8FA8C192FF63A0DC82BEB390A36E6E9EBA55B6DB,
    BTC_USDC_PUT: 0x1BF27366077765C922F342C8DE257591D1119EBBCBAE7A6C4FF2F50EDE4C54C,
    ETH_STRK_CALL: 0x6DF66DB6A4B321869B3D1808FC702713B6CBB69541D583D4B38E7B1406C09AA,
    ETH_STRK_PUT: 0x4DCD9632353ED56E47BE78F66A55A04E2C1303EBCB8EC7EA4C53F4FDF3834EC,
    STRK_USDC_CALL: 0x2B629088A1D30019EF18B893CEBAB236F84A365402FA0DF2F51EC6A01506B1D,
    STRK_USDC_PUT: 0x6EBF1D8BD43B9B4C5D90FB337C5C0647B406C6C0045DA02E6675C43710A326F,
}

# underlying assets
BTC = "bitcoin"
ETH = "ethereum"
USDC = "usd-coin"
STRK = "starknet"

UNDERLYINGS = {
     ETH_USDC_CALL: 'ETH',
     ETH_USDC_PUT: 'USDC',
     BTC_USDC_CALL: 'WBTC',
     BTC_USDC_PUT: 'USDC',
     ETH_STRK_CALL: 'ETH',
     ETH_STRK_PUT: 'STRK',
     STRK_USDC_CALL: 'STRK',
     STRK_USDC_PUT: 'USDC',
}

# starts with 0, gets updated when the script starts
# PRICES = {
#     ETH: 0,
#     BTC: 0,
#     USDC: 0,
#     STRK: 0,
# }

# hardcoded values for testing - coingecko starts returning 429 after few runs
PRICES = {
    ETH: 3479.7861977177963,
    BTC: 67493.32767383542,
    USDC: 0.9999836448271266,
    STRK: 2.1333836830118784,
}


def get_pool_trade_events(pool: str):
    response = requests.get(
        f"https://api.carmine.finance/api/v1/mainnet/{pool}/trades", timeout=5
    )
    if response.status_code != 200:
        raise Exception("API call failed")

    data = response.json()

    if data["status"] == "success":
        data = data["data"]
    else:
        raise Exception("API call failed")

    # filter out events for options past maturity
    return [d for d in data if d.get("maturity") > TIMESTAMP_NOW]


def get_weighted_average_maturity(events: list[dict], side: int) -> float | None:
    side_specific = [d for d in events if d.get("option_side") == side]
    numerator = sum(int(d["tokens_minted"], 0) * d["maturity"] for d in side_specific)
    denominator = sum(int(d["tokens_minted"], 0) for d in side_specific)
    weighted_average = numerator / denominator if denominator else None
    return weighted_average


def get_open_positions(events: list[dict], pool: str, side: int) -> float | None:
    side_specific = [d for d in events if d.get("option_side") == side]

    decimals = 18  # LP has 18 decimals

    if pool in [ETH_USDC_PUT, STRK_USDC_PUT, BTC_USDC_PUT]:
        is_put = True
        asset_price = PRICES[USDC]

    elif pool in [ETH_STRK_PUT]:
        is_put = True
        asset_price = PRICES[STRK]

    elif pool in [ETH_USDC_CALL, ETH_STRK_CALL]:
        is_put = False
        asset_price = PRICES[ETH]

    elif pool in [BTC_USDC_CALL]:
        is_put = False
        asset_price = PRICES[BTC]

    elif pool in [STRK_USDC_CALL]:
        is_put = False
        asset_price = PRICES[STRK]

    balance = 0.0

    for event in side_specific:
        size = int(event["tokens_minted"], 0) / 10**decimals
        if is_put:
            size = size * event["strike_price"]
        size = size * asset_price

        if event["action"] == "TradeOpen":
            balance += size
        elif event["action"] == "TradeClose":
            balance -= size

    return balance


def get_token_prices():
    for token in [ETH, BTC, USDC, STRK]:
        currency = "usd"
        days = "14"
        url = f"https://api.coingecko.com/api/v3/coins/{token}/market_chart?vs_currency={currency}&days={days}"

        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"Failed getting {token} price: {response.status_code}")
        data = response.json()
        prices = [item[1] for item in data["prices"]]
        average_price = sum(prices) / len(prices)
        PRICES[token] = average_price


def get_asset_price_for_pool(pool: str, amount: float | int):
    digits = 18
    price = PRICES[ETH]
    if pool in [ETH_USDC_PUT, BTC_USDC_PUT, STRK_USDC_PUT]:
        digits = 6
        price = PRICES[USDC]
    elif pool in [ETH_STRK_PUT, STRK_USDC_CALL]:
        price = PRICES[STRK]
    elif pool == BTC_USDC_CALL:
        digits = 8
        price = PRICES[BTC]

    return amount / 10**digits * price


async def get_pool_locked_unlocked(pool: str, amm: Contract):
    unlocked = await amm.functions["get_unlocked_capital"].call(POOL_ADDRESSES[pool])
    value = await amm.functions["get_value_of_pool_position"].call(POOL_ADDRESSES[pool])
    parsed_value = value[0]["mag"] / MATH_64

    return get_asset_price_for_pool(pool, unlocked[0] + parsed_value)


async def main():
    get_token_prices()
    # check that the prices are available globally
    for t in PRICES:
        if PRICES[t] == 0:
            raise Exception(f"price of {t} was not set")

    client = FullNodeClient(node_url=NODE_URL)
    amm = await Contract.from_address(
        address=AMM_ADDRESS, provider=client, proxy_config=False
    )

    latest_block = await client.get_block_number()
    final = {}
    date = datetime.datetime.fromtimestamp(TIMESTAMP_NOW).isoformat()

    for pool in POOL_ADDRESSES:
        tvl = await get_pool_locked_unlocked(pool, amm)
        events = get_pool_trade_events(pool)
        final[pool] = {
            "protocol": "Carmine",
            "date": date,
            "market": "TODO",
            "tokenSymbol": UNDERLYINGS[pool],
            "block_height": latest_block,
            "funding_rate": 0,
            "price": "TODO",
            "tvl": tvl,
            "open_shorts": get_open_positions(events, pool, SHORT),
            "open_longs": get_open_positions(events, pool, LONG),
            "maturity_shorts": get_weighted_average_maturity(events, SHORT),
            "maturity_longs": get_weighted_average_maturity(events, LONG),
            "fees_protocol": 0,
            "fees_users": "TODO",
            "etl_timestamp": TIMESTAMP_NOW,
        }
    with open("./test/carmine.json", "w") as json_file:
        json.dump(final, json_file, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
