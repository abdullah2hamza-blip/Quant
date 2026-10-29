"""Bounded HTTP transport and explicit paper/testnet broker adapters."""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from datetime import datetime
import hashlib
import hmac
import json
import math
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

import numpy as np
from paper_engine.data import Bars, audit

PUBLIC = "https://data-api.binance.vision"
BINANCE = "https://testnet.binance.vision"
ALPACA = "https://paper-api.alpaca.markets"


class ApiError(RuntimeError):
    def __init__(self, status: int, code=None):
        self.status, self.code = status, code
        super().__init__(f"Broker/data request failed: HTTP{status}, code{code}; no automatic order retry")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("API redirects are rejected")


class Http:
    def request(self, base, method, path, *, params=None, payload=None, headers=None):
        if base not in (PUBLIC, BINANCE, ALPACA, "https://data.alpaca.markets") or not path.startswith("/") or "?" in path:
            raise ValueError("Unsupported API endpoint")
        url = base + path + (("?" + urlencode(params)) if params else "")
        body = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
        req = Request(url, data=body, method=method, headers={"User-Agent": "BTC-Paper-Research/3.0", **({"Content-Type": "application/json"} if body else {}), **(headers or {})})
        try:
            with build_opener(NoRedirect).open(req, timeout=15) as response:
                raw = response.read(5_000_001)
                if len(raw) > 5_000_000:
                    raise RuntimeError("Oversized API response")
                return json.loads(raw)
        except HTTPError as error:
            try:
                data = json.loads(error.read(65536))
                code = data.get("code")
            except (ValueError, AttributeError):
                code = None
            raise ApiError(error.code, code) from None
        except (URLError, TimeoutError, OSError) as error:
            # Do not expose signed URLs or retry a possibly executed POST.
            raise RuntimeError("Transport failed; reconcile the recorded order intent before any resubmission") from None


def positive(value, name):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Invalid " + name)
    return value


def floor_quantity(quantity: float, step: str) -> str:
    q, increment = Decimal(str(quantity)), Decimal(step)
    if not q.is_finite() or q < 0 or not increment.is_finite() or increment <= 0:
        raise ValueError("Invalid quantity increment")
    return format((q / increment).to_integral_value(rounding=ROUND_DOWN) * increment, "f")


class PublicFeed:
    def __init__(self, http=None):
        self.http = http or Http()

    def update(self, bars: Bars, now: int) -> Bars:
        step = int(bars.close_times[-1] - bars.times[-1] + 1)
        cursor, rows = int(bars.times[-1]) + step, []
        # Only append; original history and EMA initialization remain immutable.
        while cursor + step <= now:
            batch = self.http.request(PUBLIC, "GET", "/api/v3/klines", params={"symbol": "BTCUSDT", "interval": bars.interval, "startTime": cursor, "endTime": now - 1, "limit": 1000})
            if not isinstance(batch, list):
                raise ValueError("Malformed kline response")
            if any(not isinstance(r, list) or len(r) != 12 for r in batch):
                raise ValueError("Malformed kline row")
            closed = [r for r in batch if int(r[0]) + step <= now]
            if not closed:
                break
            if any(len(r) != 12 or int(r[6]) != int(r[0]) + step - 1 for r in closed):
                raise ValueError("Invalid public kline shape or close time")
            if int(closed[0][0]) < cursor or any(int(a[0]) >= int(b[0]) for a, b in zip(closed[:-1], closed[1:])):
                raise ValueError("Revised, duplicate or unordered appended data")
            rows.extend(closed)
            cursor = int(closed[-1][0]) + step
        if rows:
            times = np.r_[bars.times, np.asarray([int(r[0]) for r in rows], dtype=np.int64)]
            values = np.vstack((bars.values, np.asarray([[float(v) for v in r[1:6]] for r in rows])))
            bars = Bars(times, values, times + step - 1, bars.interval,
                        {**bars.provenance, "live_append_provider": PUBLIC, "appended_rows": len(rows)})
        checked = audit(bars, as_of_ms=now, allow_gaps=True)
        if checked["zero_volume_bars"]:
            raise ValueError("Zero-volume appended candle requires explicit upstream quarantine")
        return bars

    def price(self):
        d = self.http.request(PUBLIC, "GET", "/api/v3/ticker/bookTicker", params={"symbol": "BTCUSDT"})
        bid, ask = positive(d["bidPrice"], "bid"), positive(d["askPrice"], "ask")
        if ask < bid or (ask - bid) / bid > .005:
            raise ValueError("Crossed or wider-than50bps public quote")
        return (bid + ask) / 2


class BinancePaper:
    mode, symbol, terminal = "binance", "BTCUSDT", {"FILLED", "CANCELED", "REJECTED", "EXPIRED", "EXPIRED_IN_MATCH"}

    def __init__(self, http=None):
        self.http = http or Http()
        self.key, self.secret = os.environ.get("BINANCE_TESTNET_KEY"), os.environ.get("BINANCE_TESTNET_SECRET")
        if not self.key or not self.secret:
            raise ValueError("Set BINANCE_TESTNET_KEY and BINANCE_TESTNET_SECRET; no production credentials are used")
        self.identity = hashlib.sha256((BINANCE + self.key).encode()).hexdigest()

    def signed(self, method, path, params=None):
        server = self.http.request(BINANCE, "GET", "/api/v3/time")
        p = {**(params or {}), "timestamp": int(server["serverTime"]), "recvWindow": 5000}
        p["signature"] = hmac.new(self.secret.encode(), urlencode(p).encode(), hashlib.sha256).hexdigest()
        return self.http.request(BINANCE, method, path, params=p, headers={"X-MBX-APIKEY": self.key})

    def balance(self):
        account = self.signed("GET", "/api/v3/account")
        if not account.get("canTrade"):
            raise RuntimeError("Testnet account cannot trade")
        balances = {b["asset"]: b for b in account["balances"]}
        for asset in ("BTC", "USDT"):
            b = balances.get(asset, {})
            if float(b.get("locked", 0)) > 1e-12:
                raise RuntimeError("Locked inventory requires reconciliation")
        return float(balances.get("USDT", {}).get("free", 0)), float(balances.get("BTC", {}).get("free", 0))

    def price(self):
        q = self.http.request(BINANCE, "GET", "/api/v3/ticker/bookTicker", params={"symbol": self.symbol})
        bid, ask = positive(q["bidPrice"], "bid"), positive(q["askPrice"], "ask")
        if ask < bid or (ask - bid) / bid > .005:
            raise ValueError("Invalid or wider-than50bps testnet quote")
        return (bid + ask) / 2

    def open_orders(self):
        return self.signed("GET", "/api/v3/openOrders", {"symbol": self.symbol})

    def prepare(self, side, qty, price, client_id):
        info = self.http.request(BINANCE, "GET", "/api/v3/exchangeInfo", params={"symbol": self.symbol})["symbols"][0]
        if info.get("status") != "TRADING" or info.get("baseAsset") != "BTC" or info.get("quoteAsset") != "USDT":
            raise ValueError("Unexpected testnet instrument")
        filters = {f["filterType"]: f for f in info["filters"]}
        lot = filters["LOT_SIZE"]
        quantity = floor_quantity(qty, lot["stepSize"])
        market = filters.get("MARKET_LOT_SIZE", {})
        if float(market.get("stepSize", 0)) > 0:
            quantity = floor_quantity(float(quantity), market["stepSize"])
        q = float(quantity)
        if q == 0:
            return None
        for f in (lot, market):
            if f and (q < float(f["minQty"]) or q > float(f["maxQty"])):
                return None
        for name in ("MIN_NOTIONAL", "NOTIONAL"):
            f = filters.get(name, {})
            # Conservative validation also applies limits when exchange rules
            # would waive them for markets; average-price filters can still reject.
            if q * price < float(f.get("minNotional", 0)) or q * price > float(f.get("maxNotional", "inf")):
                return None
        return {"symbol": self.symbol, "side": side.upper(), "type": "MARKET", "quantity": quantity,
                "newClientOrderId": client_id, "newOrderRespType": "FULL"}

    def submit(self, order):
        response = self.signed("POST", "/api/v3/order", order)
        self.validate_order(response, order["newClientOrderId"])
        return response

    def validate_order(self, order, client_id):
        if order.get("clientOrderId") != client_id or order.get("symbol") != self.symbol:
            raise RuntimeError("Order identity mismatch; retain and reconcile the durable intent")

    def query(self, client_id):
        try:
            response = self.signed("GET", "/api/v3/order", {"symbol": self.symbol, "origClientOrderId": client_id})
            self.validate_order(response, client_id)
            return response
        except ApiError as error:
            if error.code == -2013:
                return None
            raise

    def complete(self, order):
        return order.get("status") in self.terminal


class AlpacaPaper:
    mode, symbol = "alpaca", "BTC/USD"
    terminal = {"filled", "canceled", "expired", "rejected", "done_for_day"}

    def __init__(self, http=None):
        self.http = http or Http()
        key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_API_SECRET")
        if not key or not secret:
            raise ValueError("Set ALPACA_API_KEY and ALPACA_API_SECRET for the paper account")
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.identity = hashlib.sha256((ALPACA + key).encode()).hexdigest()

    def call(self, method, path, **kwargs):
        return self.http.request(ALPACA, method, path, headers=self.headers, **kwargs)

    def balance(self):
        account = self.call("GET", "/v2/account")
        if account.get("trading_blocked") or account.get("account_blocked") or account.get("status") != "ACTIVE":
            raise RuntimeError("Paper account is not active for trading")
        positions = self.call("GET", "/v2/positions")
        if any(p["symbol"].replace("/", "") != "BTCUSD" for p in positions):
            raise ValueError("Use a dedicated BTC/USD and cash paper account")
        coins = sum(float(p["qty"]) for p in positions)
        return float(account["cash"]), coins

    def price(self):
        d = self.http.request("https://data.alpaca.markets", "GET", "/v1beta3/crypto/us/latest/quotes", params={"symbols": self.symbol}, headers=self.headers)
        q = d["quotes"][self.symbol]
        bid, ask = positive(q["bp"], "bid"), positive(q["ap"], "ask")
        age = time.time() - datetime.fromisoformat(q["t"].replace("Z", "+00:00")).timestamp()
        if not 0 <= age <= 30 or ask < bid or (ask - bid) / bid > .005:
            raise ValueError("Stale, crossed or wider-than50bps Alpaca quote")
        return (bid + ask) / 2

    def open_orders(self):
        return self.call("GET", "/v2/orders", params={"status": "open", "symbols": self.symbol})

    def prepare(self, side, qty, price, client_id):
        assets = self.call("GET", "/v2/assets", params={"asset_class": "crypto"})
        asset = next(a for a in assets if a["symbol"] == self.symbol)
        if not asset.get("tradable") or asset.get("status") != "active":
            raise ValueError("Alpaca BTC/USD is not tradable")
        quantity = floor_quantity(qty, asset["min_trade_increment"])
        if float(quantity) < float(asset["min_order_size"]):
            return None
        return {"symbol": self.symbol, "qty": quantity, "side": side, "type": "market", "time_in_force": "gtc", "client_order_id": client_id}

    def submit(self, order):
        response = self.call("POST", "/v2/orders", payload=order)
        self.validate_order(response, order["client_order_id"])
        return response

    def validate_order(self, order, client_id):
        if order.get("client_order_id") != client_id or order.get("symbol", "").replace("/", "") != "BTCUSD":
            raise RuntimeError("Order identity mismatch; retain and reconcile the durable intent")

    def query(self, client_id):
        try:
            response = self.call("GET", "/v2/orders:by_client_order_id", params={"client_order_id": client_id})
            self.validate_order(response, client_id)
            return response
        except ApiError as error:
            if error.status == 404:
                return None
            raise

    def complete(self, order):
        return order.get("status") in self.terminal
