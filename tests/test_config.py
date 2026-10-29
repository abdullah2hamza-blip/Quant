from pathlib import Path

import pytest

from quant.config import load_settings
from tests.factories import ROOT


def test_reference_config_and_clock_duration_conversion():
    settings = load_settings(ROOT / "configs/research/btc-trend.toml")
    hourly = settings.at_interval("1h")
    assert hourly.fast == 200 and hourly.slow == 800
    assert hourly.annualization == 8760
    daily = settings.at_interval("1d")
    assert daily.fast == 9 and daily.slow == 34
    assert daily.min_history == daily.warmup + daily.trailing


@pytest.mark.parametrize("old,new", [
    ('mode = "research"', 'mode = "live"'),
    ('warmup_bars = 2000', 'warmup_bars = 1'),
    ('maximum_exposure = 1.0', 'maximum_exposure = 2.0'),
    ('fast_bars = 50', 'fast_bars = true'),
    ('annualization_bars = 2190', 'annualization_bars = 252'),
    ('minimum_history_before_scoring_bars = 6380', 'minimum_history_before_scoring_bars = 1'),
    ('base_cost_bps_per_side = 25.0', 'base_cost_bps_per_side = nan'),
    ('schema_version = 1', 'schema_version = 1\nignored_setting = 3'),
])
def test_invalid_or_silently_ignored_config_rejected(tmp_path, old, new):
    path = tmp_path / "bad.toml"
    path.write_text((ROOT / "configs/research/btc-trend.toml").read_text().replace(old, new))
    with pytest.raises(ValueError):
        load_settings(path)
