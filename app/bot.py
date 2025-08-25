#!/usr/bin/env python3
import sys
import json
import time
import ccxt  # pip install ccxt
import numpy as np
import pandas as pd
from decimal import Decimal
from decimal import Decimal, ROUND_HALF_UP

from app.config import EnvConfig, load_env_vars

NBSP = "\u00A0"

envs:EnvConfig = load_env_vars()

def _to_decimal(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal(0)

def format_value(x, decimals=2, strip_trailing=True) -> str:
    """
    General French formatting: thousands with NBSP + ',' as decimal separator.
    Example: 12345.5 (decimals=2) -> '12 345,50'
    """
    d = _to_decimal(x).quantize(Decimal(10) ** -decimals, rounding=ROUND_HALF_UP)
    q = f"{d:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", NBSP)
    if strip_trailing and decimals > 0:
        # Remove trailing zeros and trailing comma
        q = q.rstrip("0").rstrip(",")
    return q

def fetch_ohlcv_df(exchange, symbol: str, timeframe: str = "1d", limit: int = 100) -> pd.DataFrame:
    """
    Fetch OHLCV data and return a tidy pandas DataFrame with:
    time (ms), open, high, low, close, volume, and a datetime index.
    """
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    if not raw or len(raw) == 0:
        raise RuntimeError("No OHLCV data returned")

    df = pd.DataFrame(raw, columns=["time", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df.set_index("datetime", inplace=True)
    return df[["open", "high", "low", "close", "volume", "time"]]


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=window, min_periods=window).mean()


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    Average True Range (Wilder). Returns a pandas Series aligned with df index.

    TR_t = max(
        high_t - low_t,
        |high_t - close_{t-1}|,
        |low_t  - close_{t-1}|
    )

    ATR = SMA(TR, window)  (Wilder uses RMA, SMA is acceptable if you prefer it)
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    # Wilder's ATR uses an RMA (smoothed moving average). Here is SMA for simplicity:
    atr_sma = tr.rolling(window=window, min_periods=window).mean()

    # If you prefer Wilder's smoothing (RMA), uncomment below and comment SMA above:
    # rma = tr.ewm(alpha=1/window, adjust=False).mean()
    # return rma

    return atr_sma


def compute_indicators(exchange, symbol: str, timeframe: str = "1d") -> dict:
    """
    Compute MA20 and ATR14 on the requested timeframe.
    Returns the last values (most recent candle) and the latest df for further use.
    """
    # Need at least 20 for MA20 and 14 for ATR, take margin (e.g., 120)
    df = fetch_ohlcv_df(exchange, symbol, timeframe=timeframe, limit=120)

    df["MA20"] = sma(df["close"], 20)
    df["ATR14"] = atr(df, 14)

    last_row = df.iloc[-1]
    last_ma20 = float(last_row["MA20"]) if not np.isnan(last_row["MA20"]) else None
    last_atr14 = float(last_row["ATR14"]) if not np.isnan(last_row["ATR14"]) else None
    last_close = float(last_row["close"])

    return {
        "timeframe": timeframe,
        "last_close": last_close,
        "MA20": last_ma20,
        "ATR14": last_atr14,
        "df": df,  # keep it if you want to examine the whole history
    }

def mk_exchange():
  """
  Create and return a Binance exchange client configured for Spot Testnet.

  - Uses API key and secret from environment variables.
  - Enables sandbox mode (https://testnet.binance.vision).
  """
  if not envs.binance_api_key or not envs.binance_api_secret:
    print("❌ Missing BINANCE_API_KEY or BINANCE_API_SECRET in .env", file=sys.stderr)
    sys.exit(1)

  exchange = ccxt.binance({
    "apiKey": envs.binance_api_key,
    "secret": envs.binance_api_secret,
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
      print(f" - {asset}: total={format_value(total)}, free={format_value(free)}, used={format_value(used)}")

def main():
    """CLI entry point for the trading bot."""
    if len(sys.argv) < 2:
        usage_and_exit()

    cmd = sys.argv[1].lower()
    exchange = mk_exchange()

    if cmd == "price":
        last = fetch_ticker_last(exchange, 'BTC/USDT')
        print(f"📈 BTC/USDT last = {format_value(last)}")
        return
      
    if cmd == "balance":
      print_balance(exchange)
      return
    
    if cmd == "indicators":
        # Optional: pass timeframe as 3rd arg (default 1d)
        timeframe = sys.argv[2] if len(sys.argv) >= 3 else "1d"
        data = compute_indicators(exchange, 'BTC/USDT', timeframe)
        print("\n📊 Indicators")
        print(json.dumps({
            "symbol": 'BTC/USDT',
            "timeframe": data["timeframe"],
            "last_close": format_value(data["last_close"]),
            "MA20": format_value(data["MA20"]),
            "ATR14": format_value(data["ATR14"])
        }, indent=2, ensure_ascii=False))
        # Example of dynamic trigger levels:
        if data["MA20"] and data["ATR14"]:
            buy_lvl = data["MA20"] - 2 * data["ATR14"]
            tp_lvl  = data["last_close"] + 3 * data["ATR14"]
            sl_lvl  = data["last_close"] - 1.5 * data["ATR14"]
            print("\n🎯 Dynamic levels")
            print(json.dumps({
                "buy_level": format_value(buy_lvl),
                "take_profit": format_value(tp_lvl),
                "stop_loss": format_value(sl_lvl)
            }, indent=2, ensure_ascii=False))
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
        if 'BTC/USDT' not in markets:
            print(f"❌ Market BTC/USDT not found on this exchange/testnet.", file=sys.stderr)
            sys.exit(1)

        print(f"⏳ Placing {cmd.upper()} order {amount} BTC/USDT (market) on testnet...")
        order = place_market_order(exchange, 'BTC/USDT', cmd, amount)

        # Wait a bit before fetching updated order status
        time.sleep(0.5)
        oid = order.get("id")
        if oid:
            try:
                order = exchange.fetch_order(oid, 'BTC/USDT')
            except Exception:
                # Some testnet endpoints may not support fetch_order immediately
                pass

        print_order_summary(order)
        return

    usage_and_exit()


if __name__ == "__main__":
    main()
