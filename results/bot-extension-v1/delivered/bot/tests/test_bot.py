from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import json
import sqlite3

import numpy as np
import pytest

import bot_core
from bot_core import load_csv, settings, signal, should_trade, verify_paper_core
from bot_io import BinancePaper, AlpacaPaper, ApiError, PublicFeed, BINANCE, PUBLIC, floor_quantity
from bot_runtime import Store, cycle, process_lock
from paper_engine.data import Bars, write_bars
from paper_engine.engine import features, trade_to_weight
from trend_bot import main


@pytest.fixture
def s():
    return replace(settings(cash=1000), fast=2, slow=4, warmup=8, vol_window=3,
        pairs=((2, 4), (3, 5)), selection_interval=3, trailing=4, min_history=12, initial_pair=(2, 4))


@pytest.fixture
def bars(s):
    times = 1504224000000 + np.arange(30, dtype=np.int64) * s.seconds * 1000
    close = 100 * np.exp(np.cumsum(.001 + .0003 * np.sin(np.arange(30))))
    values = np.c_[close, close * 1.01, close * .99, close, np.ones(30)]
    return Bars(times, values, times + s.seconds * 1000 - 1, "4h", {"csv_sha256": "synthetic-fixture", "symbol": "BTCUSDT"})


def store_at(path, bars, s, **kwargs):
    return Store(path, bars, s, policy="fixed", mode="sim", offline=True, **kwargs)


def test_reviewed_code_and_paper_constants():
    assert verify_paper_core()["verified_modules"] == 4
    p = settings()
    assert (p.interval, p.fast, p.slow, p.vol_target, p.vol_window, p.annualization, p.band, p.base_cost) == ("4h", 50, 200, .2, 180, 2190, .1, 25)
    assert p.pairs == ((25, 100), (50, 200), (100, 400))
    assert (p.warmup, p.trailing, p.min_history, p.selection_interval) == (2000, 4380, 6380, 180)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_starting_cash(value):
    with pytest.raises(ValueError): settings(cash=value)


def test_fee_accounting_cannot_borrow_like_old_bot():
    cash, qty, notional, fee = trade_to_weight(1000, 0, 100, 1, .003)
    assert cash == 0 and qty * 100 + fee == pytest.approx(1000)
    assert notional == pytest.approx(1000 / 1.003)
    assert fee > 0
    cash, qty, _, _ = trade_to_weight(cash, qty, 100, 0, .003)
    assert qty == 0 and cash > 0


def test_band_entries_and_complete_exits_bypass_small_size():
    assert should_trade(.01, 0, 0, .1)
    assert should_trade(0, .00001, .000001, .1)
    assert not should_trade(.5, .55, 1, .1)
    assert should_trade(.5, .8, 1, .1)


def test_future_prices_cannot_change_prior_target(bars, s):
    f = features(bars, s)
    changed = bars.values.copy(); changed[25:, :4] *= 10
    g = features(Bars(bars.times, changed, bars.close_times, bars.interval, bars.provenance), s)
    for key in f.targets:
        np.testing.assert_array_equal(f.targets[key][:25], g.targets[key][:25])
    sig = signal(bars, s)
    assert sig["target"] == f.targets[(2, 4)][-1]
    assert sig["earliest_execution_ms"] == bars.close_times[-1] + 1


def test_duplicate_and_restart_never_refill(tmp_path, bars, s):
    path=tmp_path / "sim.sqlite"; now=int(bars.close_times[-1])+100
    first=store_at(path,bars,s)
    event=cycle(first,s,policy="fixed",now=now,price=100)
    assert event["status"]=="simulated_fill"
    assert event["cash_after"]>=0 and event["coins_after"]>0
    assert event["equity_before"]-event["equity_after"]==pytest.approx(event["assumed_cost"])
    after=first.get("account"); first.db.close()
    restarted=store_at(path,bars,s)
    assert cycle(restarted,s,policy="fixed",now=now,price=100)["status"]=="duplicate_skipped"
    assert restarted.get("account")==after
    assert restarted.db.execute("select count(*) from events").fetchone()[0]==1
    restarted.db.close()


def test_stale_decision_is_not_backfilled_as_a_trade(tmp_path,bars,s):
    st=store_at(tmp_path/"x.sqlite",bars,s)
    assert cycle(st,s,policy="fixed",now=int(bars.close_times[-1])+1_000_000,price=100)["status"]=="stale_skipped"
    assert st.get("account")=={"cash":1000,"coins":0}
    st.db.close()


def test_gap_holds_coins_and_resets_warmup(tmp_path,bars,s):
    gapped=bars.take(np.arange(len(bars))!=25)
    st=store_at(tmp_path/"x.sqlite",gapped,s)
    with st.db: st.set("account",{"cash":10,"coins":2})
    result=cycle(st,s,policy="fixed",now=int(gapped.close_times[-1])+100,price=100)
    assert result["status"]=="warmup_paused"
    assert st.get("account")=={"cash":10,"coins":2}
    st.db.close()


def test_zero_volatility_never_invents_a_position(bars,s):
    values=bars.values.copy(); values[:,:4]=100
    flat=Bars(bars.times,values,bars.close_times,bars.interval,bars.provenance)
    assert signal(flat,s)["ready"] is False


def test_lock_and_kill_switch(tmp_path,bars,s):
    state=tmp_path/"x.sqlite"
    with process_lock(state):
        with pytest.raises(RuntimeError,match="locked"):
            with process_lock(state): pass
    assert not state.with_suffix(".sqlite.lock").exists()
    kill=tmp_path/"STOP"; kill.write_text("stop")
    st=store_at(state,bars,s)
    assert cycle(st,s,policy="fixed",now=int(bars.close_times[-1])+100,price=100,kill_file=kill)["status"]=="stopped"
    assert st.db.execute("select count(*) from events").fetchone()[0]==0
    st.db.close()


def test_changed_source_account_or_policy_cannot_reuse_state(tmp_path,bars,s):
    path=tmp_path/"x.sqlite";st=store_at(path,bars,s);st.db.close()
    with pytest.raises(ValueError,match="differs"):
        store_at(path,bars,s,account_identity="different-account")
    with pytest.raises(ValueError,match="differs"):
        Store(path,bars,s,policy="adaptive",mode="sim",offline=True)
    old=tmp_path/"old.json";old.write_text('{"cash":1000,"qty":1}')
    with pytest.raises(ValueError,match="legacy"):
        store_at(old,bars,s)
    unrelated=tmp_path/"research.sqlite"
    with sqlite3.connect(unrelated) as db:db.execute('create table attempts(id text)')
    with pytest.raises(ValueError,match="recognized"):
        store_at(unrelated,bars,s)
    with sqlite3.connect(unrelated) as db:
        assert db.execute("select name from sqlite_master where type='table'").fetchall()==[('attempts',)]


def test_source_edit_during_run_stops_new_orders(tmp_path,bars,s,monkeypatch):
    import bot_runtime
    st=store_at(tmp_path/"x.sqlite",bars,s)
    monkeypatch.setattr(bot_runtime,'source_fingerprint',lambda:'changed')
    with pytest.raises(RuntimeError,match='source changed'):
        cycle(st,s,policy='fixed',now=int(bars.close_times[-1])+100,price=100)
    assert st.get('account')=={'cash':1000,'coins':0}
    st.db.close()


class Broker:
    mode="binance"
    def __init__(self, response=None):
        self.posts=[]; self.query_result=response;self.fail=False
    def balance(self):return 1000.,0.
    def price(self):return 100.
    def open_orders(self):return []
    def prepare(self,side,qty,price,client_id):return {"side":side,"qty":qty,"client_id":client_id}
    def submit(self,order):
        self.posts.append(order)
        if self.fail:raise RuntimeError("ambiguous timeout")
        return {"status":"FILLED","clientOrderId":order["client_id"]}
    def query(self,identifier):return self.query_result
    def complete(self,order):return order["status"]=="FILLED"


def test_order_timeout_persists_intent_and_never_blindly_retries(tmp_path,bars,s):
    st=store_at(tmp_path/"x.sqlite",bars,s);broker=Broker();broker.fail=True
    now=int(bars.close_times[-1])+100
    with pytest.raises(RuntimeError,match="ambiguous"):
        cycle(st,s,policy="fixed",now=now,broker=broker)
    assert len(st.pending())==1 and len(broker.posts)==1
    with pytest.raises(RuntimeError,match="Do not resubmit"):
        cycle(st,s,policy="fixed",now=now,broker=broker)
    assert len(broker.posts)==1
    broker.query_result={"status":"FILLED"}
    assert cycle(st,s,policy="fixed",now=now,broker=broker)["status"]=="duplicate_skipped"
    assert not st.pending() and len(broker.posts)==1
    st.db.close()


def test_partial_fill_blocks_new_orders(tmp_path,bars,s):
    st=store_at(tmp_path/"x.sqlite",bars,s);broker=Broker({"status":"PARTIALLY_FILLED"})
    decision=int(bars.close_times[-1])
    with st.db:st.db.execute("INSERT INTO orders VALUES (?,?,?,?,?)",("id",decision,"{}",None,"pending"))
    with pytest.raises(RuntimeError,match="partially filled"):
        cycle(st,s,policy="fixed",now=decision+100,broker=broker)
    assert not broker.posts
    st.db.close()


def test_terminal_response_crash_before_event_is_recovered(tmp_path,bars,s):
    st=store_at(tmp_path/"x.sqlite",bars,s);broker=Broker({"status":"FILLED"})
    decision=int(bars.close_times[-1])
    with st.db:st.db.execute("INSERT INTO orders VALUES (?,?,?,?,?)",("id",decision,"{}",'{"status":"FILLED"}',"terminal"))
    assert cycle(st,s,policy="fixed",now=decision+100,broker=broker)["status"]=="duplicate_skipped"
    assert not broker.posts
    st.db.close()


def test_slow_quote_or_metadata_cannot_submit_after_execution_window(tmp_path,bars,s):
    st=store_at(tmp_path/"x.sqlite",bars,s);broker=Broker()
    decision=int(bars.close_times[-1])
    result=cycle(st,s,policy="fixed",now=decision+100,broker=broker,clock=lambda:decision+999_999)
    assert result["status"]=="execution_window_or_kill_switch_changed" and not broker.posts
    st.db.close()


@pytest.mark.parametrize("quantity,step,expected",[(.123456,"0.001","0.123"),(1.,"0.01","1.00"),(.0001,"0.001","0.000")])
def test_quantities_round_down_without_extra_spending(quantity,step,expected):
    result=Decimal(floor_quantity(quantity,step))
    assert result==Decimal(expected)
    assert result<=Decimal(str(quantity)) and result/Decimal(step)==(result/Decimal(step)).to_integral_value()


def test_csv_manifest_corruption_and_duplicate_candles_fail(tmp_path,bars,s):
    path=tmp_path/"data.csv";write_bars(path,bars,{"symbol":"BTCUSDT"})
    assert len(load_csv(path,s))==len(bars)
    with path.open("a") as f:f.write("garbage\n")
    with pytest.raises(ValueError,match="hash"):
        load_csv(path,s)
    path=tmp_path/"legacy.csv"
    path.write_text("timestamp,open,high,low,close,volume\n1504224000000,1,2,1,2,1\n1504224000000,1,2,1,2,1\n")
    with pytest.raises(ValueError,match="Duplicate"):
        load_csv(path,s)


def test_online_clocks_cannot_be_forged_and_alpaca_basis_is_explicit(capsys):
    assert main(["binance","--offline","--once","--as-of-ms","1","--price","1"])==2
    assert main(["alpaca","--once"])==2
    assert "quote-basis" in capsys.readouterr().err


def test_doctor_runs_without_credentials_or_network(capsys):
    assert main(["doctor"])==0
    assert json.loads(capsys.readouterr().out)["adaptive_edge_established"] is False


def test_research_check_command_creates_fresh_state_parent_and_propagates_failure(tmp_path,monkeypatch):
    import importlib.util
    from types import SimpleNamespace
    spec=importlib.util.spec_from_file_location('check_entry',bot_core.HOME/'research/checks.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.__file__=str(tmp_path/'research/checks.py')
    def child(command,cwd):
        base=Path(command[command.index('--basetemp')+1])
        assert base.parent.is_dir() and cwd==tmp_path
        return SimpleNamespace(returncode=7)
    monkeypatch.setattr(module.subprocess,'run',child)
    assert module.main()==7
