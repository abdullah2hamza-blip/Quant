"""Supplied SMA signal with shared, audited no-borrowing execution.

This alternative is explicitly outside the paper's frozen EMA candidate family.
It requires all six SMA windows and resets at gaps. Resizing is evaluated at
the actual opening/execution valuation, consistently with the shared engine.
Those corrections differ from the supplied legacy close-trigger backtest.
"""
from dataclasses import asdict, replace
from datetime import timedelta
import json

import numpy as np

from bot_core import HOME, paired, settings as paper_settings, verify_paper_core
from paper_engine.data import audit, digest, iso, timestamp
from paper_engine.engine import metrics, simulate


def settings(cash=1.0):
    path=HOME/'config/legacy_daily.json'
    cfg=json.loads(path.read_text())
    expected={'schema_version':1,'strategy':'legacy_daily','interval':'1d','length_days':[40,50,60,80,100,150],
        'volatility_target':.4,'volatility_lookback':30,'warmup_bars':150,'rebalance_weight_band':.15,
        'maximum_exposure':1.,'base_cost_bps':25.,
        'status':'Exploratory corrected legacy alternative; not a registered paper strategy or fresh confirmation'}
    if cfg!=expected:
        raise ValueError('Legacy parameters changed; define and validate a new exploratory protocol')
    return replace(paper_settings('1d',cash),source=path,sha256=digest(path),warmup=150,
        vol_target=.4,vol_window=30,band=.15,min_history=150)


def targets(bars,s):
    if bars.interval!='1d' or s.interval!='1d':
        raise ValueError('legacy_daily requires native UTC daily candles')
    close=bars.values[:,3];n=len(close)
    out=np.full(n,np.nan);risk=np.full(n,np.nan)
    edges=np.r_[0,np.flatnonzero(np.diff(bars.times)!=s.seconds*1000)+1,n]
    lengths=(40,50,60,80,100,150)
    for begin,end in zip(edges[:-1],edges[1:],strict=True):
        for i in range(begin+149,end):
            vol=float(np.std(np.diff(np.log(close[i-30:i+1])),ddof=1)*np.sqrt(365))
            if not np.isfinite(vol) or vol<=1e-12:
                continue
            trend=sum(close[i]>np.mean(close[i+1-k:i+1]) for k in lengths)/len(lengths)
            risk[i]=min(1.,.4/vol)
            out[i]=trend*risk[i]
    return out,risk


def signal(bars,s):
    audit(bars,allow_gaps=True)
    values,risk=targets(bars,s)
    if not np.isfinite(values[-1]):
        return {'ready':False,'target':None,'reason':'legacy daily needs150 continuous candles and positive realized volatility'}
    return {'ready':True,'policy':'legacy_daily','target':float(values[-1]),'risk_weight':float(risk[-1]),
        'length_days':[40,50,60,80,100,150],'decision_time_ms':int(bars.close_times[-1]),
        'earliest_execution_ms':int(bars.close_times[-1])+1,'research_status':'exploratory corrected legacy alternative'}


def backtest(bars,s,start,end,*,draws=5000,seed=20261022,case_id='legacy_daily_exploratory'):
    if start>=end or draws<100:
        raise ValueError('Need ordered dates and at least100 bootstrap draws')
    finish=timestamp(end+timedelta(days=1))
    bars=bars.take((bars.times>=timestamp(s.dev_start))&(bars.times<finish))
    quality=audit(bars,allow_gaps=True)
    if quality['zero_volume_bars'] or bars.times[0]!=timestamp(s.dev_start) or bars.times[-1]!=finish-s.seconds*1000:
        raise ValueError('Need complete original prehistory and requested boundaries')
    begin=int(np.searchsorted(bars.times,timestamp(start)));stop=len(bars)
    weights,risk=targets(bars,s)
    if not 1<=begin<stop-1 or bars.times[begin]!=timestamp(start) or not np.isfinite(weights[begin-1]):
        raise ValueError('Missing evaluation start or sufficient prior daily history')
    from paper_engine.engine import features
    ps=paper_settings('1d',s.initial_equity)
    reference=features(bars,ps)
    if not reference.valid[begin-1]:
        raise ValueError('The matched daily EMA control lacks prior history')
    buy_hold=np.full(stop,np.nan);buy_hold[np.flatnonzero(np.isfinite(weights))[0]:]=1.
    scenarios={};arrays={'open_time_ms':bars.times[begin:],'close_time_ms':bars.close_times[begin:]};trades={}
    for cost in (25.,0.,10.,50.,100.):
        books={'legacy_daily':simulate(bars,weights,s,cost,'legacy_daily'),
            'paper_ema_daily_reference':simulate(bars,reference.targets[(ps.fast,ps.slow)],ps,cost,'paper_ema_daily_reference'),
            'cash':simulate(bars,np.zeros(stop),s,cost,'cash'),
            'buy_hold':simulate(bars,buy_hold,s,cost,'buy_hold'),
            'legacy_volatility_target':simulate(bars,risk,s,cost,'legacy_volatility_target')}
        result={'metrics':{},'initial_state':{}}
        for name,book in books.items():
            result['metrics'][name]=metrics(book,bars,begin,stop,365,cost)
            result['initial_state'][name]={'nav':float(book.nav[begin-1]),'cash':float(book.cash[begin-1]),
                'coins':float(book.coins[begin-1]),'valuation_time':iso(bars.close_times[begin-1])}
            for field in ('nav','cash','coins','weights','costs','turnover'):
                arrays[f'cost{cost:g}__{name}__{field}']=getattr(book,field)[begin:]
        result['legacy_minus_daily_ema']=paired(books['legacy_daily'],books['paper_ema_daily_reference'],bars,begin,stop,s,draws=draws,seed=seed)
        scenarios[f'{cost:g}']=result
        if cost==25:
            trades={name:[t for t in book.trades if begin<=t['bar_index']<stop] for name,book in books.items()}
    report={'schema_version':3,'policy':'legacy_daily','settings':json.loads(json.dumps(asdict(s),default=str)),
        'strategy_config':json.loads((HOME/'config/legacy_daily.json').read_text()),'source':verify_paper_core(),
        'audit':quality,'data':bars.provenance,'case_id':case_id,'score_start':iso(bars.times[begin]),
        'score_end':iso(bars.close_times[-1]),'scored_bars':stop-begin,'scenarios':scenarios,
        'interpretation':'Exploratory legacy SMA alternative with corrected execution. Not a paper-registered strategy or fresh holdout. Future profitability unproven.',
        'execution_differences_from_supplied_v2':['All150 daily candles required at inception and after gaps',
            'Band checked against opening valuation, not prior close','Exact post-fee weights; no cash borrowing'],
        'comparison_scope':'Daily EMA control is the paper clock-scaled9/34 rule at20% risk; it is not the native4h reference. Risk targets differ.'}
    return report,arrays,[trades,[]]
