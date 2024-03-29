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

AMM_ADDRESS = 0x047472E6755AFC57ADA9550B6A3AC93129CC4B5F98F51C73E0644D129FD208D9

# pools
ETH_USDC_CALL = "ETH_USDC_CALL"
ETH_USDC_PUT = "ETH_USDC_PUT"
BTC_USDC_CALL = "wBTC_USDC_CALL"
BTC_USDC_PUT = "wBTC_USDC_PUT"
ETH_STRK_CALL = "ETH_STRK_CALL"
ETH_STRK_PUT = "ETH_STRK_PUT"
STRK_USDC_CALL = "STRK_USDC_CALL"
STRK_USDC_PUT = "STRK_USDC_PUT"

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

# starts with 0, gets updated when the script starts
PRICES = {
    ETH: 0,
    BTC: 0,
    USDC: 0,
    STRK: 0,
}


def fetch_events_from_api():
    response = requests.get(
        "https://api.carmine.finance/api/v1/mainnet/all-transactions", timeout=5
    )
    if response.status_code != 200:
        raise Exception("API call failed")

    data = response.json()

    if data["status"] == "success":
        data = data["data"]
    else:
        raise Exception("API call failed")

    trades = []

    for event in data:
        if event["option"] is not None:
            if event["option"]["maturity"] > TIMESTAMP_NOW:
                event.update(event.pop("option"))
                # convert strike_price from MATH_64
                event["strike_price"] = int(event["strike_price"], 0) / MATH_64
                trades.append(event)

    return trades


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


def store_to_json(d: dict):
    with open("./test/carmine.json", "w") as json_file:
        json.dump(d, json_file, indent=2)


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

    for pool in POOL_ADDRESSES:
        res = await get_pool_locked_unlocked(pool, amm)
        final[pool] = {
            "protocol": "Carmine",
            "date": datetime.datetime.now().isoformat(),
            "block_height": latest_block,
            "tvl": res,
        }
    store_to_json(final)


if __name__ == "__main__":
    asyncio.run(main())
