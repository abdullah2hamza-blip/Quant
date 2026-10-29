"""Independent price-based feature and cash-flow audit of the exploratory bot study.

This deliberately does not call the strategy feature builder, simulator or metric
builder. It checks accepted outputs against the separately pinned vendor CSV.
Saved-result/archive integrity verification remains a separate prerequisite.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from quant.data import digest, json_write
from scripts.bot_extension_study import verify

ROOT = Path(__file__).resolve().parents[1]


def independent_targets(times, close):
    n = len(close)
    valid = np.zeros(n, dtype=bool)
    targets = {name: np.full(n, np.nan) for name in
               ('sma_20', 'ema_20', 'sma_40', 'ema_40', 'volatility_20', 'volatility_40')}
    segment = 0
    fast = slow = float(close[0])
    for i, price in enumerate(close):
        if i == 0 or times[i] - times[i-1] != 86400000:
            segment = i
            fast = slow = float(price)
        else:
            fast += (price-fast) * (2/10)
            slow += (price-slow) * (2/35)
        if i-segment+1 < 334:
            continue
        daily = np.diff(np.log(close[i-30:i+1]))
        vol = float(np.std(daily, ddof=1) * np.sqrt(365))
        if not np.isfinite(vol) or vol <= 1e-12:
            continue
        valid[i] = True
        vote = sum(price > sum(close[i-w+1:i+1])/w
                   for w in (40, 50, 60, 80, 100, 150))/6
        for label, target in (('20', .2), ('40', .4)):
            risk = min(1., target/vol)
            targets['sma_'+label][i] = vote*risk
            targets['ema_'+label][i] = risk if fast > slow else 0.
            targets['volatility_'+label][i] = risk
    targets['cash'] = np.zeros(n)
    targets['buy_hold'] = np.full(n, np.nan)
    targets['buy_hold'][np.flatnonzero(valid)[0]:] = 1.
    return valid, targets


def check_prices(arrays, trades, report, times, opening, close):
    if not np.array_equal(arrays['open_time_ms'], times):
        raise ValueError('Saved time grid differs from vendor input')
    valid, targets = independent_targets(times, close)
    if not np.array_equal(valid, arrays['common_valid']):
        raise ValueError('Independent common feature gate differs')
    max_target_error = 0.
    for name, expected in targets.items():
        actual = arrays['target__'+name]
        if not np.allclose(actual, expected, rtol=0, atol=2e-10, equal_nan=True):
            raise ValueError('Independent rolling/EMA target differs: '+name)
        max_target_error = max(max_target_error, float(np.nanmax(abs(actual-expected))))
    max_valuation_error = max_cash_error = max_coin_error = 0.
    path_count = event_count = 0
    start = report['score_start_index']
    for cost, scenario in report['scenarios'].items():
        fee = float(cost)/10000
        for name, metric in scenario['metrics'].items():
            prefix = f'cost{cost}__{name}__'
            nav, cash, coins = (arrays[prefix+x] for x in ('nav', 'cash', 'coins'))
            fees, turns = (arrays[prefix+x] for x in ('costs', 'turnover'))
            if nav[0] != 1 or cash[0] != 1 or coins[0] != 0:
                raise ValueError('Incorrect initial account')
            residual = np.max(abs(nav-cash-coins*close))
            max_valuation_error = max(max_valuation_error, float(residual))
            if residual > 1e-10 or np.min(cash) < -1e-12 or np.min(coins) < -1e-12:
                raise ValueError('Vendor-price valuation or no-borrowing failure')
            events = {event['bar_index']:event for event in trades[cost][name]}
            if len(events) != len(trades[cost][name]):
                raise ValueError('Duplicate order')
            for i in range(1, len(times)):
                target = arrays['target__'+name][i-1]
                before = cash[i-1] + coins[i-1]*opening[i]
                eligible = times[i]-times[i-1] == 86400000 and np.isfinite(target)
                transition = eligible and ((target == 0 and coins[i-1] > 0)
                                            or (target > 0 and coins[i-1] == 0))
                resize = eligible and abs(target-coins[i-1]*opening[i]/before) >= .1
                expected_order = transition or resize
                event = events.get(i)
                # Zero notional below the simulator's numerical-order cutoff
                # has no economic effect, even when the decision gate is true.
                if expected_order and event is None and abs(target*before-coins[i-1]*opening[i]) > 1e-13*before:
                    raise ValueError('Missing eligible order')
                if event is not None and not expected_order:
                    raise ValueError('Order violates prior-close/gap/open-band gate')
                dc, dq = cash[i]-cash[i-1], coins[i]-coins[i-1]
                notional = dq*opening[i]
                loss = abs(notional)*fee
                cash_error = abs(dc+notional+loss)
                coin_error = abs(dq-(event['signed_notional']/opening[i] if event else 0.))
                max_cash_error = max(max_cash_error, float(cash_error))
                max_coin_error = max(max_coin_error, float(coin_error))
                if cash_error > 1e-10 or coin_error > 1e-12 or abs(fees[i]-loss) > 1e-10:
                    raise ValueError('Vendor-price cash, coin or cost conservation fails')
                if event:
                    after = cash[i]+coins[i]*opening[i]
                    if (event['price'] != opening[i]
                            or abs(coins[i]*opening[i]/after-target) > 1e-10
                            or abs(turns[i]-abs(notional)/before) > 1e-10):
                        raise ValueError('Execution price, post-fee weight or turnover differs')
                    event_count += 1
                elif abs(dc) > 1e-10 or abs(dq) > 1e-12 or turns[i] != 0:
                    raise ValueError('Account movement without an order')
            values = nav[start-1:]
            returns = values[1:]/values[:-1]-1
            expected = {'total_return': values[-1]/values[0]-1,
                        'maximum_drawdown': np.min(values/np.maximum.accumulate(values)-1),
                        'annualized_volatility': np.std(returns, ddof=1)*np.sqrt(365),
                        'mean_exposure': np.mean(coins[start:]*close[start:]/nav[start:])}
            if any(abs(metric[k]-v) > 1e-10 for k,v in expected.items()):
                raise ValueError('Independent scored risk/return metric differs')
            path_count += 1
    return {'account_paths_checked': path_count, 'full_history_trade_events_checked': event_count,
            'history_rows': len(times), 'scored_rows': len(times)-start,
            'maximum_target_absolute_error': max_target_error,
            'maximum_nav_identity_absolute_error': max_valuation_error,
            'maximum_cash_flow_absolute_error': max_cash_error,
            'maximum_coin_flow_absolute_error': max_coin_error}


def audit(collection: Path, csv_path: Path):
    verified = verify(collection)
    if digest(csv_path) != verified['freeze']['input']['sha256']:
        raise ValueError('Daily CSV differs from the frozen input')
    with csv_path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    times = np.array([int(row['open_time_ms']) for row in rows], dtype=np.int64)
    opening = np.array([float(row['open']) for row in rows])
    close = np.array([float(row['close']) for row in rows])
    path = collection/verified['registry']['matched']
    trades = json.loads((path/'trades.json').read_text())
    with np.load(path/'paths.npz', allow_pickle=False) as arrays:
        checked = check_prices(arrays, trades, verified['report'], times, opening, close)
    return {'status':'passed independent vendor-price feature and account audit',
            'finished_at':datetime.now(timezone.utc).isoformat(),
            'audit_source_sha256':digest(Path(__file__)),
            'registry_sha256':digest(collection/'registry.json'), 'input_csv_sha256':digest(csv_path),
            **checked,
            'scope':'Independent direct rolling features and vendor-price account/decision identities; archived-source replay separately checks all interval outputs. No new observations or coverage guarantee.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection',type=Path,default=ROOT/'results/bot-extension-v1')
    parser.add_argument('--csv',type=Path,default=ROOT/'data/btc-1d-through-2026-10-20.csv')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Preserve prior audits; choose a fresh output')
    result = audit(args.collection,args.csv)
    json_write(args.output,result)
    print(json.dumps(result,indent=2))
