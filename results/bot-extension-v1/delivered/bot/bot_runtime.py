"""Restart-safe paper execution; no endpoint can submit production orders."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time

import numpy as np

from bot_core import load_csv, signal, should_trade, source_fingerprint
from bot_io import AlpacaPaper, BinancePaper, PublicFeed, positive
from paper_engine.data import Bars, audit, digest
from paper_engine.engine import trade_to_weight


@contextmanager
def process_lock(state: Path):
    state.parent.mkdir(parents=True, exist_ok=True)
    lock = state.with_suffix(state.suffix + ".lock")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise RuntimeError("State is locked by another process or an interrupted run; inspect the lock/PID before removing it") from None
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"pid": os.getpid(), "created_at": datetime.now(timezone.utc).isoformat()}, f)
        yield
    finally:
        lock.unlink()


class Store:
    def __init__(self, path: Path, seed: Bars, s, *, policy: str, mode: str, offline: bool, account_identity="local-simulation"):
        existed = path.exists()
        if path.exists():
            with path.open("rb") as f:
                if f.read(16) != b"SQLite format 3\x00":
                    raise ValueError("Use a new SQLite state; legacy JSON/cash must be reconciled explicitly")
        self.db = sqlite3.connect(path, timeout=5)
        if existed:
            tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables != {"meta", "candles", "events", "orders"}:
                self.db.close()
                raise ValueError("This SQLite file is not a recognized v3 bot state")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candles (t INTEGER PRIMARY KEY,o REAL,h REAL,l REAL,c REAL,v REAL);
        CREATE TABLE IF NOT EXISTS events (decision_ms INTEGER PRIMARY KEY, receipt TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS orders (client_id TEXT PRIMARY KEY, decision_ms INTEGER UNIQUE NOT NULL, payload TEXT NOT NULL, response TEXT, status TEXT NOT NULL);
        ''')
        binding = {"schema": 3, "config_sha256": s.sha256, "interval": s.interval, "symbol": s.symbol,
                   "policy": policy, "mode": mode, "offline": offline,
                   "seed_sha256": seed.provenance["csv_sha256"], "source_fingerprint": source_fingerprint(),
                   "account_identity": account_identity}
        previous = self.get("binding")
        if previous is not None and previous != binding:
            self.db.close()
            raise ValueError("State/config/source/account mode differs; reconcile and use a new state for a changed protocol")
        if previous is None:
            with self.db:
                self.set("binding", binding)
                self.set("account", {"cash": s.initial_equity, "coins": 0.0})
                self.set("provenance", seed.provenance)
                self.db.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?)", [(int(t), *map(float, v)) for t, v in zip(seed.times, seed.values, strict=True)])
        self.interval = s.interval
        self.step = s.seconds * 1000

    def get(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, key, value):
        self.db.execute("INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value, allow_nan=False)))

    def bars(self):
        rows = self.db.execute("SELECT * FROM candles ORDER BY t").fetchall()
        times = np.asarray([r[0] for r in rows], dtype=np.int64)
        return Bars(times, np.asarray([r[1:] for r in rows]), times + self.step - 1, self.interval, self.get("provenance"))

    def append(self, bars):
        existing = self.bars()
        n = len(existing)
        if len(bars) < n or not np.array_equal(existing.times, bars.times[:n]) or not np.array_equal(existing.values, bars.values[:n]):
            raise ValueError("Historical data revision detected")
        with self.db:
            self.db.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?)", [(int(t), *map(float, v)) for t, v in zip(bars.times[n:], bars.values[n:], strict=True)])
            self.set("provenance", bars.provenance)

    def event(self, decision, receipt, account=None):
        with self.db:
            if account is not None:
                self.set("account", account)
            self.db.execute("INSERT INTO events VALUES (?,?)", (decision, json.dumps(receipt, allow_nan=False)))

    def seen(self, decision):
        return self.db.execute("SELECT 1 FROM events WHERE decision_ms=?", (decision,)).fetchone() is not None

    def pending(self):
        return self.db.execute("SELECT o.client_id,o.decision_ms,o.payload FROM orders o LEFT JOIN events e ON e.decision_ms=o.decision_ms WHERE o.status='pending' OR e.decision_ms IS NULL").fetchall()


def reconcile(store: Store, broker):
    pending = store.pending()
    if len(pending) > 1:
        raise RuntimeError("Multiple outstanding intents require manual reconciliation")
    for identifier, decision, payload in pending:
        order = broker.query(identifier)
        if order is None:
            raise RuntimeError("Recorded order intent has no confirmed remote result. Do not resubmit; reconcile this client order ID manually: " + identifier)
        with store.db:
            store.db.execute("UPDATE orders SET response=?,status=? WHERE client_id=?", (json.dumps(order), "terminal" if broker.complete(order) else "pending", identifier))
        if not broker.complete(order):
            raise RuntimeError("Remote order is still open/partially filled; no new order can be submitted")
        if not store.seen(decision):
            store.event(decision, {"status": "reconciled", "client_order_id": identifier, "remote_order": order})


def cycle(store: Store, s, *, policy, now, price=None, feed=None, broker=None,
          max_delay_seconds=120, kill_file=None, clock=None):
    if store.get("binding")["source_fingerprint"] != source_fingerprint():
        raise RuntimeError("Bot source changed since state initialization; reconcile before restarting")
    if type(now) is not int or not 0 <= max_delay_seconds <= 300:
        raise ValueError("Need an integer UTC clock and execution delay between0 and300seconds")
    if broker is not None:
        reconcile(store, broker)
    if kill_file is not None and kill_file.exists():
        return {"status": "stopped", "reason": "kill file present; no new orders"}
    bars = store.bars()
    if feed is not None:
        bars = feed.update(bars, now)
        store.append(bars)
        if clock is not None:
            now = clock()
    quality = audit(bars, as_of_ms=now, allow_gaps=True)
    if quality["zero_volume_bars"]:
        raise ValueError("Cannot act on zero-volume candles")
    decision = int(bars.close_times[-1])
    if store.seen(decision):
        return {"status": "duplicate_skipped", "decision_time_ms": decision}
    receipt = {"decision_time_ms": decision, "observed_at_ms": now, "policy": policy,
               "execution_model": "current observable paper/testnet price; not a historical next-open fill"}
    delay = now - (decision + 1)
    if not 0 <= delay <= max_delay_seconds * 1000:
        receipt.update(status="stale_skipped", delay_ms=delay)
        store.event(decision, receipt)
        return receipt
    sig = signal(bars, s, policy)
    receipt["signal"] = sig
    if not sig["ready"]:
        receipt["status"] = "warmup_paused"
        store.event(decision, receipt)
        return receipt
    if broker is None:
        account = store.get("account")
        cash, coins = account["cash"], account["coins"]
        px = positive(price if price is not None else feed.price(), "execution price")
    else:
        if broker.open_orders():
            raise RuntimeError("Open external orders require reconciliation")
        cash, coins = broker.balance()
        px = positive(broker.price(), "broker price")
    if not all(math.isfinite(x) and x >= 0 for x in (cash, coins)) or cash + coins * px <= 0:
        raise ValueError("Insolvent, short or invalid account balances")
    equity, target = cash + coins * px, sig["target"]
    current = coins * px / equity
    receipt.update(price=px, cash_before=cash, coins_before=coins, equity_before=equity, target=target)
    if not should_trade(target, current, coins, s.band):
        receipt["status"] = "hold"
        store.event(decision, receipt, {"cash": cash, "coins": coins})
        return receipt
    # Sim uses the paper's25bps. Sandbox sizing reserves100bps of notional
    # for uncertain broker fees; actual fills/balances, not this estimate, are truth.
    rate = s.base_cost / 10000 if broker is None else .01
    new_cash, new_coins, notional, cost = trade_to_weight(cash, coins, px, target, rate)
    if abs(notional) <= 1e-14 * equity:
        receipt["status"] = "numerical_dust"
        store.event(decision, receipt, {"cash": cash, "coins": coins})
        return receipt
    if (kill_file is not None and kill_file.exists()) or (clock is not None and not 0 <= clock() - (decision + 1) <= max_delay_seconds * 1000):
        receipt["status"] = "execution_window_or_kill_switch_changed"
        store.event(decision, receipt)
        return receipt
    if broker is None:
        receipt.update(status="simulated_fill", signed_notional=notional, assumed_cost=cost,
                       cash_after=new_cash, coins_after=new_coins, equity_after=new_cash + new_coins * px,
                       cost_bps=s.base_cost, target_weight_after_cost=target)
        store.event(decision, receipt, {"cash": new_cash, "coins": new_coins})
        return receipt
    identifier = "btc3-" + hashlib.sha256(f"{broker.mode}:{policy}:{s.sha256}:{decision}".encode()).hexdigest()[:26]
    order = broker.prepare("buy" if notional > 0 else "sell", min(abs(notional) / px, coins) if notional < 0 else abs(notional) / px, px, identifier)
    if order is None:
        receipt["status"] = "exchange_minimum_or_size_limit"
        store.event(decision, receipt)
        return receipt
    if (kill_file is not None and kill_file.exists()) or (clock is not None and not 0 <= clock() - (decision + 1) <= max_delay_seconds * 1000):
        receipt["status"] = "execution_window_or_kill_switch_changed"
        store.event(decision, receipt)
        return receipt
    # Durable intent precedes POST. An ambiguous result survives any exception
    # or process exit and must be queried, never blindly retried.
    with store.db:
        store.db.execute("INSERT INTO orders VALUES (?,?,?,?,?)", (identifier, decision, json.dumps(order), None, "pending"))
    response = broker.submit(order)
    with store.db:
        store.db.execute("UPDATE orders SET response=?,status=? WHERE client_id=?", (json.dumps(response), "terminal" if broker.complete(response) else "pending", identifier))
    receipt.update(status="broker_submitted", client_order_id=identifier, remote_order=response,
                   sizing_fee_reserve_bps=100, fill_quality="Observe actual executed quantities/commissions; no invented fill")
    store.event(decision, receipt)
    return receipt


def run(args, s):
    if args.offline and (args.mode != "sim" or not args.once or args.as_of_ms is None or args.price is None):
        raise ValueError("Offline mode requires sim --once --as-of-ms <UTC milliseconds> --price <positive simulated price>")
    if not args.offline and (args.as_of_ms is not None or args.price is not None):
        raise ValueError("Artificial clocks/prices are prohibited for online and broker modes")
    if s.interval != "4h" and args.policy != "legacy_daily":
        raise ValueError("Execution uses the paper's4h protocol; other intervals are replay robustness only")
    if args.mode == "alpaca" and not args.allow_quote_basis:
        raise ValueError("Alpaca BTC/USD differs from Binance BTC/USDT; require explicit --allow-quote-basis")
    now = args.as_of_ms if args.offline else int(time.time() * 1000)
    seed = load_csv(args.data, s, as_of_ms=now)
    if seed.provenance.get("symbol", "BTCUSDT") != "BTCUSDT":
        raise ValueError("Execution requires Binance BTCUSDT seed history")
    broker = {"binance": BinancePaper, "alpaca": AlpacaPaper}.get(args.mode)
    broker = broker() if broker else None
    feed = None if args.offline else PublicFeed()
    with process_lock(args.state):
        store = Store(args.state, seed, s, policy=args.policy, mode=args.mode, offline=args.offline,
                      account_identity=broker.identity if broker else "local-simulation")
        try:
            while True:
                result = cycle(store, s, policy=args.policy, now=now, price=args.price, feed=feed, broker=broker,
                               max_delay_seconds=args.max_execution_delay_seconds, kill_file=args.kill_file,
                               clock=None if args.offline else lambda: int(time.time() * 1000))
                print(json.dumps(result, allow_nan=False), flush=True)
                if args.once or result["status"] == "stopped":
                    return 0
                # Poll cheaply between4h boundaries; duplicate candles never trade.
                time.sleep(20)
                now = int(time.time() * 1000)
        except KeyboardInterrupt:
            return 0
        finally:
            store.db.close()
