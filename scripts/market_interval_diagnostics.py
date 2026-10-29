"""Post-outcome finite-sample centering diagnostic; no replacement inference."""
from __future__ import annotations

import csv
import io
from pathlib import Path

import numpy as np

from quant.data import digest, json_write
from scripts.build_publication_artifacts import paired_path_difference, verify_results


def expected_mbb_mean(values, block: int) -> float:
    values=np.asarray(values,dtype=float)
    n=len(values)
    if (values.ndim!=1 or not np.isfinite(values).all() or isinstance(block,bool)
            or not isinstance(block,int) or not 1<=block<=n):
        raise ValueError('Need a finite series and a feasible integer block')
    cumulative=np.r_[0.,np.cumsum(values)]
    starts=n-block+1
    complete,remainder=divmod(n,block)
    full=(cumulative[block:]-cumulative[:-block]).mean()
    truncated=(cumulative[remainder:remainder+starts]-cumulative[:starts]).mean() if remainder else 0.
    return float((complete*full+truncated)/n)


def build(results: Path, output: Path) -> dict:
    _,_,_,markets=verify_results(results)
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for name,report in markets.items():
        seconds={'1h':3600,'4h':14400,'1d':86400}[report['case']['interval']]
        annual=365*86400/seconds
        for cost in report['scenarios']:
            values=paired_path_difference(results/'market'/name/'paths.npz',report,cost)
            for days in (15,30,60):
                block=days*86400//seconds
                if block>len(values):continue
                observed=float(values.mean()*annual)
                expected=expected_mbb_mean(values,int(block))*annual
                rows.append({'case':name,'cost_bps':float(cost),'block_days':days,'observations':len(values),
                    'nominal_blocks':len(values)/block,'observed_annual_log_difference':observed,
                    'expected_resample_annual_log_difference':expected,'edge_weighting_shift':expected-observed,
                    'original_five_block_reporting_rule_met':len(values)>=5*block})
    record={'kind':'Post-outcome deterministic block-centering diagnostic; no new or replaced confidence intervals',
        'input_registry_sha256':digest(results/'registry.json'),'rows':rows,
        'interpretation':'Non-circular overlapping blocks weight sample edges differently. This expected-resample diagnostic does not validate mixing, stability, finite-sample coverage, or a selected corrected interval.'}
    json_write(output/'diagnostics.json',record)
    buf=io.StringIO(newline=''); writer=csv.DictWriter(buf,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader();writer.writerows(rows);(output/'diagnostics.csv').write_text(buf.getvalue(),encoding='utf-8')
    selected=[r for r in rows if r['case'] in ('binance_matched_1h','binance_matched_1d') and r['cost_bps']==25 and r['block_days']==30]
    lines=[r'\begin{tabular}{lrrr}',r'\toprule',r'Case & Nominal blocks & Observed & Expected resample\\',r'\midrule']
    for row in selected:
        label='Hourly' if row['case'].endswith('1h') else 'Daily'
        lines.append(f"{label} & {row['nominal_blocks']:.1f} & {100*row['observed_annual_log_difference']:.3f}\\% & {100*row['expected_resample_annual_log_difference']:.3f}\\%\\\\")
    lines += [r'\bottomrule',r'\end{tabular}']
    (output/'edge-table.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    trace={'input_registry_sha256':record['input_registry_sha256'],'source_sha256':digest(Path(__file__)),
           'output_sha256':{p.name:digest(p) for p in output.iterdir() if p.is_file() and p.name!='traceability.json'}}
    json_write(output/'traceability.json',trace)
    return trace
