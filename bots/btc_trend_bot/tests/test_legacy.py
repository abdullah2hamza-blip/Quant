"""Independent signal arithmetic and shared execution contracts for daily SMA."""
from datetime import date
import importlib.util
import json
import math
from pathlib import Path
import statistics

import numpy as np
import pytest

from bot_core import HOME, signal
from bot_runtime import Store, cycle
from legacy_daily import settings, targets
from paper_engine.data import Bars
from paper_engine.engine import simulate
from trend_bot import main


@pytest.fixture
def daily():
    n = 200
    times = 1504224000000 + np.arange(n, dtype=np.int64) * 86400000
    close = 100 * np.exp(np.cumsum(.002 + .035 * np.sin(np.arange(n) / 4)))
    opening = close * (1 + .005 * np.cos(np.arange(n)))
    values = np.c_[opening, np.maximum(opening, close) * 1.01,
                   np.minimum(opening, close) * .99, close, np.ones(n)]
    return Bars(times, values, times + 86399999, '1d',
                {'csv_sha256': 'synthetic-daily-fixture', 'symbol': 'BTCUSDT'})


def test_daily_defaults_are_separate_and_ema_remains_default(capsys, tmp_path):
    assert main(['doctor']) == 0
    paper = json.loads(capsys.readouterr().out)
    assert paper['policy'] == 'fixed' and paper['paper_matches']
    seed = tmp_path / 'seed.csv'
    seed.touch()
    assert main(['doctor', '--policy', 'legacy_daily', '--data', str(seed)]) == 0
    legacy = json.loads(capsys.readouterr().out)
    assert legacy['policy'] == 'legacy_daily' and not legacy['paper_matches']
    assert legacy['data_exists']
    assert main(['doctor', '--policy', 'legacy_daily', '--interval', '4h']) == 2
    assert 'requires --interval 1d' in capsys.readouterr().err
    s = settings()
    assert (s.interval, s.vol_target, s.vol_window, s.warmup, s.band, s.base_cost) == ('1d', .4, 30, 150, .15, 25)


def test_daily_signal_matches_independent_sma_and_sample_volatility(daily):
    s = settings()
    result, risk = targets(daily, s)
    assert np.isnan(result[:149]).all()
    close = daily.values[:, 3].tolist()
    for i in range(149, len(daily)):
        # Python statistics and direct slices are independent of NumPy's estimator.
        returns = [math.log(close[j]) - math.log(close[j-1]) for j in range(i-29, i+1)]
        expected_risk = min(1, .4 / (statistics.stdev(returns) * math.sqrt(365)))
        votes = sum(close[i] > statistics.mean(close[i+1-k:i+1]) for k in (40, 50, 60, 80, 100, 150))
        assert risk[i] == pytest.approx(expected_risk, rel=2e-13)
        assert result[i] == pytest.approx(votes / 6 * expected_risk, rel=2e-13)
    assert signal(daily, s, 'legacy_daily')['target'] == result[-1]
    changed = daily.values.copy(); changed[180:, :4] *= 2
    future = Bars(daily.times, changed, daily.close_times, '1d', daily.provenance)
    np.testing.assert_array_equal(targets(future, s)[0][:180], result[:180])


def test_daily_gaps_restart_full_warmup_and_flat_prices_pause(daily):
    s = settings()
    gap = daily.take(np.arange(len(daily)) != 160)
    result, _ = targets(gap, s)
    assert np.isnan(result[160:]).all()
    assert not signal(gap, s, 'legacy_daily')['ready']
    values = daily.values.copy(); values[:, :4] = 100
    flat = Bars(daily.times, values, daily.close_times, '1d', daily.provenance)
    assert not signal(flat, s, 'legacy_daily')['ready']


def test_daily_runtime_and_next_open_replay_agree_and_restart_is_idempotent(tmp_path, daily):
    s = settings(cash=1000)
    weights, _ = targets(daily, s)
    replay = simulate(daily, weights, s, 25, 'legacy_daily')
    first = daily.take(np.arange(len(daily)) < 149)
    path = tmp_path / 'daily.sqlite'
    store = Store(path, first, s, policy='legacy_daily', mode='sim', offline=True)
    for i in range(149, len(daily)):
        history = daily.take(np.arange(len(daily)) < i)
        store.append(history)
        event = cycle(store, s, policy='legacy_daily', now=int(daily.times[i]), price=float(daily.values[i, 0]))
        account = store.get('account')
        assert account['cash'] == pytest.approx(replay.cash[i], rel=1e-12, abs=1e-12)
        assert account['coins'] == pytest.approx(replay.coins[i], rel=1e-12, abs=1e-12)
        assert account['cash'] >= 0 and account['coins'] >= 0
    store.db.close()
    restarted = Store(path, first, s, policy='legacy_daily', mode='sim', offline=True)
    assert cycle(restarted, s, policy='legacy_daily', now=int(daily.times[-1]), price=float(daily.values[-1, 0]))['status'] == 'duplicate_skipped'
    restarted.db.close()
    with pytest.raises(ValueError, match='State/config/source/account'):
        Store(path, first, s, policy='fixed', mode='sim', offline=True)


def test_daily_cli_chooses_seed_interval_and_its_own_state(monkeypatch, tmp_path):
    import bot_runtime
    def run(args, s):
        assert args.data == HOME / 'data/btc-1d.csv'
        assert args.state == HOME / 'state/legacy-daily.sqlite'
        assert s.interval == '1d'
        return 0
    monkeypatch.setattr(bot_runtime, 'run', run)
    assert main(['sim', '--policy', 'legacy_daily', '--once']) == 0


@pytest.mark.parametrize('interval', ['4h', '1d'])
def test_data_fetch_default_filename_matches_interval(monkeypatch, interval):
    spec = importlib.util.spec_from_file_location('fetch_entry', HOME / 'research/get_data.py')
    module = importlib.util.module_from_spec(spec)
    # The script is normally executed with research/ on sys.path.
    import sys
    monkeypatch.syspath_prepend(str(HOME / 'research'))
    spec.loader.exec_module(module)
    observed = []
    def fetch(start, end, output, **kwargs):
        observed.append((output, kwargs['interval']))
    monkeypatch.setattr(module, 'fetch_binance', fetch)
    assert module.main(['--interval', interval, '--end', '2026-10-20']) == 0
    assert observed == [(HOME / f'data/btc-{interval}.csv', interval)]
