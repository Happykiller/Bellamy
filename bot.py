#!/usr/bin/env python3
import os
import sys
import json
import time
from decimal import Decimal
from dotenv import load_dotenv

import ccxt  # pip install ccxt

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
SYMBOL = os.getenv("SYMBOL", "BTC/USDT")  # trading pair


def mk_exchange():
  """
  Create and return a Binance exchange client configured for Spot Testnet.

  - Uses API key and secret from environment variables.
  - Enables sandbox mode (https://testnet.binance.vision).
  """
  if not API_KEY or not API_SECRET:
    print("❌ Missing BINANCE_API_KEY or BINANCE_API_SECRET in .env", file=sys.stderr)
    sys.exit(1)

  exchange = ccxt.binance({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "spot"},  # Spot market, not futures
  })

  exchange.set_sandbox_mode(True)  # activate testnet
  return exchange


def fetch_ticker_last(exchange, symbol: str) -> Decimal:
  """
  Fetch the last traded price for the given symbol.
  Returns a Decimal to avoid float precision issues.
  """
  ticker = exchange.fetch_ticker(symbol)
  last = ticker.get("last") or ticker.get("close")
  return Decimal(str(last)) if last is not None else Decimal("0")


def place_market_order(exchange, symbol: str, side: str, amount: Decimal):
  """
  Place a market buy/sell order on the given symbol.

  :param exchange: ccxt exchange client
  :param symbol: trading pair, e.g., BTC/USDT
  :param side: "buy" or "sell"
  :param amount: quantity of base currency (e.g., BTC)
  """
  assert side in ("buy", "sell")
  order = exchange.create_order(symbol, "market", side, float(amount))
  return order


def print_order_summary(order: dict):
  """
  Print a minimal summary of an order returned by ccxt.
  Shows id, symbol, side, type, status, amount, filled, cost, avg price.
  """
  id_ = order.get("id")
  symbol = order.get("symbol")
  side = order.get("side")
  type_ = order.get("type")
  status = order.get("status")
  amount = order.get("amount")
  filled = order.get("filled")
  cost = order.get("cost")  # cost in quote currency (e.g., USDT)
  price = order.get("price")  # may be None for market orders

  print("\n🧾 Order summary")
  print(json.dumps({
    "id": id_, "symbol": symbol, "side": side, "type": type_,
    "status": status, "amount": amount, "filled": filled,
    "cost": cost, "avg_price": (cost / filled if cost and filled else None)
  }, indent=2, default=str))


def usage_and_exit():
  """Show usage instructions and exit."""
  print(
    "Usage:\n"
    "  python bot.py buy  <amount_btc>\n"
    "  python bot.py sell <amount_btc>\n"
    "  python bot.py price\n"
    "\nExamples:\n"
    "  python bot.py price\n"
    "  python bot.py buy  0.001\n"
    "  python bot.py sell 0.001\n"
  )
  sys.exit(1)
    
def print_balance(exchange):
  """
  Fetch and print wallet balances (free, used, total) for all currencies.
  """
  balance = exchange.fetch_balance()
  print("\n💰 Wallet balances:")
  for asset, info in balance["total"].items():
    total = balance["total"][asset]
    if total and total > 0:
      free = balance["free"][asset]
      used = balance["used"][asset]
      print(f" - {asset}: total={total}, free={free}, used={used}")

def main():
    """CLI entry point for the trading bot."""
    if len(sys.argv) < 2:
        usage_and_exit()

    cmd = sys.argv[1].lower()
    exchange = mk_exchange()

    if cmd == "price":
        last = fetch_ticker_last(exchange, SYMBOL)
        print(f"📈 {SYMBOL} last = {last}")
        return
      
    if cmd == "balance":
      print_balance(exchange)
      return

    if cmd in ("buy", "sell"):
        if len(sys.argv) < 3:
            usage_and_exit()
        try:
            amount = Decimal(sys.argv[2])
        except Exception:
            print("❌ Invalid amount", file=sys.stderr)
            sys.exit(1)

        # Ensure the symbol exists on this exchange
        markets = exchange.load_markets()
        if SYMBOL not in markets:
            print(f"❌ Market {SYMBOL} not found on this exchange/testnet.", file=sys.stderr)
            sys.exit(1)

        print(f"⏳ Placing {cmd.upper()} order {amount} {SYMBOL} (market) on testnet...")
        order = place_market_order(exchange, SYMBOL, cmd, amount)

        # Wait a bit before fetching updated order status
        time.sleep(0.5)
        oid = order.get("id")
        if oid:
            try:
                order = exchange.fetch_order(oid, SYMBOL)
            except Exception:
                # Some testnet endpoints may not support fetch_order immediately
                pass

        print_order_summary(order)
        return

    usage_and_exit()


if __name__ == "__main__":
    main()
