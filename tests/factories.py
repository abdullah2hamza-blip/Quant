from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np

from quant.config import load_settings
from quant.data import Bars, timestamp, write_bars

ROOT = Path(__file__).resolve().parents[1]


def small_settings():
    return replace(load_settings(ROOT / "configs/research/btc-trend.toml"), fast=3, slow=8,
                   pairs=((2, 5), (3, 8), (6, 12)), initial_pair=(3, 8), warmup=60,
                   vol_window=10, trailing=120, min_history=180, selection_interval=20,
                   dev_start=date(2020, 1, 1), dev_end=date(2020, 2, 9),
                   selection_start=date(2020, 2, 10), selection_end=date(2020, 2, 19),
                   reserved_start=date(2020, 2, 20), reserved_end=date(2020, 2, 29))


def sample_bars(count=360, seed=19):
    rng = np.random.default_rng(seed)
    returns = rng.normal(.001, .01, count)
    close = 100 * np.exp(np.cumsum(returns))
    opening = np.r_[100., close[:-1]]
    times = timestamp(date(2020, 1, 1)) + np.arange(count, dtype=np.int64) * 14400000
    values = np.column_stack([opening, np.maximum(opening, close) * 1.01,
                              np.minimum(opening, close) * .99, close, np.full(count, 1000.)])
    return Bars(times, values, times + 14400000 - 1, "4h", {})


def write_fixture(path, bars=None):
    bars = bars if bars is not None else sample_bars()
    write_bars(path, bars, {"provider": "synthetic-test", "symbol": "BTCUSDT", "instrument": "spot"})
    return path
