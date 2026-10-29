"""Frozen post-outcome bot evidence and matched-settings daily ablation.

No strategy selection, new holdout, market e-process or trading interface.
Source ZIPs contain no vendor candles. Saved-result verification/building does
not require vendor CSVs; a replay requires the exact separately restored input.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import platform
import shutil
import sqlite3
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

import numpy as np

from quant.config import load_settings
from quant.data import Bars, audit, digest, iso, json_write, read_bars, timestamp
from quant.engine import features, metrics, simulate
from quant.ledger import Ledger, utc_now
from quant.stats import paired_block_bootstrap


ROOT = Path(__file__).resolve().parents[1]
SPEC = "configs/research/bot-extension-study-v1.json"
BOOKS = ("sma_20", "ema_20", "sma_40", "ema_40", "cash", "buy_hold", "volatility_20", "volatility_40")
GUARDED = ("scripts/bot_extension_study.py", SPEC, "src/quant/__init__.py", "src/quant/config.py",
           "src/quant/data.py", "src/quant/engine.py", "src/quant/ledger.py", "src/quant/stats.py")
SEEDS = {"data/btc-1d.csv", "data/btc-1d.manifest.json", "data/btc-4h.csv", "data/btc-4h.manifest.json"}
FIELDS = ("nav", "cash", "coins", "weights", "costs", "turnover")
LIMIT = "Post-outcome exploratory matched settings; no fresh holdout, causal alpha, multiplicity-adjusted/sequential inference or future-profitability claim"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def seal(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def safe(name):
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and "\\" not in name and ":" not in name and all(x not in ("", ".", "..") for x in name.split("/"))


def local(root, name):
    p = (Path(root)/name).resolve()
    if not p.is_relative_to(Path(root).resolve()):
        raise ValueError("Study path escapes its root")
    return p


def record(path):
    return {"sha256": digest(path), "bytes": Path(path).stat().st_size}


def check_record(path, expected):
    if not Path(path).is_file() or record(path) != expected:
        raise ValueError("Changed or missing study payload: "+str(path))


def load_spec(path):
    spec = read_json(path)
    expected = {"schema_version": 1, "study_id": "post-protocol-bot-extension-v1",
                "status": "exploratory_after_outcome_inspection_no_strategy_selection", "interval": "1d",
                "initial_equity": 1., "ema_pair": [9,34], "sma_windows": [40,50,60,80,100,150],
                "volatility_targets": [.2,.4], "volatility_window": 30, "annualization": 365,
                "warmup": 334, "band": .1, "maximum_exposure": 1., "costs_bps": [0,10,25,50,100],
                "base_cost_bps": 25, "books": list(BOOKS), "prehistory_start": "2017-09-01",
                "score_start": "2025-01-01", "score_end": "2026-10-20",
                "bootstrap": {"draws":5000,"block_days":[15,30,60],"seed":20261023,"confidence":.95}}
    paths = {"protocol", "base_config", "input_csv", "input_audit", "bot_directory"}
    if set(spec) != set(expected)|paths or any(spec[k] != v or isinstance(spec[k],bool) for k,v in expected.items()):
        raise ValueError("Changed exploratory specification; declare a new version")
    if any(not isinstance(spec[k],str) or not safe(spec[k]) for k in paths):
        raise ValueError("Invalid study input path")
    return spec


def guard(root, spec):
    return {name:digest(local(root,name)) for name in sorted({*GUARDED,spec["protocol"],spec["base_config"]})}


def check_guard(root, expected):
    if any(digest(local(root,n)) != sha for n,sha in expected.items()):
        raise ValueError("An executed scientific source/config/protocol changed")


def bot_fingerprint(bot):
    bot = Path(bot)
    files = [*bot.glob("*.py"),*bot.glob("paper_engine/*.py"),*bot.glob("research/*.py"),
             *bot.glob("tests/*.py"),*bot.glob("config/*"),bot/"requirements.txt",bot/"paper-origin.json",bot/"pyproject.toml",bot/"uv.lock"]
    h = hashlib.sha256()
    for p in sorted(files):
        if p.is_file():
            h.update(p.relative_to(bot).as_posix().encode()+b"\0"+p.read_bytes())
    return h.hexdigest()


def stable_delivered(report):
    report = json.loads(json.dumps(report))
    for group,key in (("audit","as_of"),("data","local_path"),("settings","source")):
        report[group].pop(key,None)
    return report


def compare_npz(a, b):
    with np.load(a,allow_pickle=False) as x,np.load(b,allow_pickle=False) as y:
        if set(x.files) != set(y.files):
            raise ValueError("Installed/delivered array inventory differs")
        for k in x.files:
            if x[k].dtype != y[k].dtype or x[k].shape != y[k].shape or not np.array_equal(x[k],y[k]):
                raise ValueError("Installed/delivered account array differs: "+k)


def verify_delivered(folder):
    """Verify captured evidence without resolving historical absolute paths."""
    folder = Path(folder);bot = folder/"bot"
    installed = read_json(folder/"installation.json")
    inv = installed["inventory"]
    if installed.get("status") != "completed" or installed["files_installed"] != len(inv) or not SEEDS <= set(inv):
        raise ValueError("Incomplete installed-bot receipt")
    for name,expected in inv.items():
        if not safe(name): raise ValueError("Unsafe installed inventory")
        if name not in SEEDS: check_record(bot/name,expected)
    actual = {p.relative_to(bot).as_posix() for p in bot.rglob("*") if p.is_file()}
    if actual != set(inv)-SEEDS:
        raise ValueError("Captured bot source/evidence inventory differs")
    quality = read_json(bot/"validation/quality.json")
    legacy = read_json(bot/"validation/legacy-report.json")
    fingerprint = bot_fingerprint(bot)
    if any(r["source"]["source_fingerprint"] != fingerprint for r in (installed,quality,legacy)):
        raise ValueError("Delivered source fingerprint differs from receipts")
    for name,expected in quality["receipts"].items():
        if not safe(name) or digest(bot/"validation"/name) != expected["sha256"]:
            raise ValueError("Changed bot validation receipt")
    origin = read_json(bot/"paper-origin.json")
    for name,sha in origin["paper_modules"].items():
        if not safe(name) or digest(bot/name) != sha: raise ValueError("Changed delivered numerical core")
    if digest(bot/"config/paper.toml") != origin["paper_config_sha256"]:
        raise ValueError("Changed delivered paper configuration")
    archive = bot/origin["original_archive_in_bot"]
    if digest(archive) != origin["original_archive_sha256"] or installed["original_backup_sha256"] != digest(archive):
        raise ValueError("Original bot archive identity differs")
    with ZipFile(archive) as z:
        originals = {name.replace("\\","/"):sha for name,sha in origin["original_files"].items()}
        if len(originals)!=14 or set(z.namelist()) != set(originals) or any(not safe(n) or Path(n).suffix.lower() not in (".py",".md",".txt") for n in originals):
            raise ValueError("Original fourteen-file source inventory differs")
        for name,sha in originals.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=sha: raise ValueError("Changed original bot source")
    if digest(folder/"previous-installation.json") != installed["previous_installation_sha256"]:
        raise ValueError("Earlier installation receipt changed")
    if digest(folder/"installed-tests.txt") != installed["installed_tests"]["log_sha256"]:
        raise ValueError("Installed test log changed")
    attempt = read_json(bot/"validation/legacy-attempt.json")
    other = folder/"installed-replay"
    other_attempt = read_json(other/"attempt.json")
    paths = {"paths.npz":bot/"validation/legacy-paths.npz", "report.json":bot/"validation/legacy-report.json",
             "trades.json":bot/"validation/legacy-trades.json", "selections.json":other/"selections.json"}
    for receipt,base in ((attempt,None),(other_attempt,other)):
        if receipt["status"] != "completed" or receipt["source_fingerprint"] != fingerprint:
            raise ValueError("Delivered/installed replay is not source-bound and completed")
        for name,sha in receipt["outputs"].items():
            if name not in paths or digest((base/name) if base else paths[name]) != sha:
                raise ValueError("Replay attempt receipt does not bind its outputs")
    if digest(other/"report.json") != installed["policy_checks"]["legacy_daily"]["report_sha256"]:
        raise ValueError("Installed report differs from installation receipt")
    if stable_delivered(read_json(other/"report.json")) != stable_delivered(legacy):
        raise ValueError("Installed scientific report differs from delivered version")
    compare_npz(other/"paths.npz",bot/"validation/legacy-paths.npz")
    if read_json(other/"trades.json") != read_json(bot/"validation/legacy-trades.json"):
        raise ValueError("Installed/delivered trade records differ")
    with np.load(bot/"validation/legacy-paths.npz",allow_pickle=False) as z:
        if set(legacy["scenarios"])!={"0","10","25","50","100"} or legacy["policy"]!="legacy_daily" or legacy["settings"]["vol_target"]!=.4 or legacy["settings"]["warmup"]!=150 or legacy["settings"]["band"]!=.15:
            raise ValueError("Delivered bot design differs from the preserved implementation")
        for cost,scenario in legacy["scenarios"].items():
            if set(scenario["metrics"])!={"legacy_daily","paper_ema_daily_reference","cash","buy_hold","legacy_volatility_target"}:
                raise ValueError("Delivered policy inventory differs")
            for name,m in scenario["metrics"].items():
                nav=z[f"cost{cost}__{name}__nav"];initial=scenario["initial_state"][name]["nav"]
                if not math.isclose(float(nav[-1]/initial-1),m["total_return"],abs_tol=1e-13,rel_tol=0):
                    raise ValueError("Delivered return disagrees with its account path")
    return {"source_fingerprint":fingerprint,"installed_inventory_entries_verified_before_freeze":len(inv),
            "preserved_non_seed_payloads":len(inv)-len(SEEDS),"vendor_seed_inventory_not_distributed":{n:inv[n] for n in sorted(SEEDS)},
            "original_archive_sha256":digest(archive),"legacy_metrics_by_cost":{c:r["metrics"]["legacy_daily"] for c,r in legacy["scenarios"].items()},
            "legacy_report_sha256":digest(paths["report.json"]),"scope":"Preserved delivered .15-band/150-warmup SMA; separate from the matched .10-band/334-warmup extension"}


def capture_delivered(root, spec, output):
    bot = local(root,spec["bot_directory"]);i=read_json(bot/"validation/installation.json")
    # Validate ALL historical installation entries before excluding vendor seeds.
    for name,expected in i["inventory"].items():
        if not safe(name): raise ValueError("Unsafe installed inventory")
        check_record(bot/name,expected)
    for name,expected in i["inventory"].items():
        if name in SEEDS: continue
        target=output/"bot"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(bot/name,target);check_record(target,expected)
    shutil.copy2(bot/"validation/installation.json",output/"installation.json")
    # Capture local historical receipt targets once, then never follow their
    # absolute provenance paths during verification or relocated execution.
    for key,dest in (("previous_installation_receipt","previous-installation.json"),):
        source=local(root,i[key]);shutil.copy2(source,output/dest)
    source=local(root,i["installed_tests"]["log"]);shutil.copy2(source,output/"installed-tests.txt")
    replay=local(root,i["policy_checks"]["legacy_daily"]["replay_output"])
    (output/"installed-replay").mkdir()
    for name in ("attempt.json","report.json","paths.npz","trades.json","selections.json"):
        shutil.copy2(replay/name,output/"installed-replay"/name)
    return verify_delivered(output)


def freeze(output, *, root=ROOT, spec_path=None):
    root=Path(root).resolve();output=Path(output);spec_path=Path(spec_path or root/SPEC)
    ledger=Ledger(root/"runs/research.sqlite");identifier=ledger.start("bot_extension_freeze",{"output":str(output),"spec":str(spec_path)},phase="post_outcome_exploratory",code=digest(Path(__file__)))
    try:
        spec=load_spec(spec_path);g=guard(root,spec)
        if digest(spec_path)!=digest(root/SPEC):raise ValueError("Archive must contain the actual machine specification")
        if output.exists(): raise ValueError("Preserve earlier extension attempts; output already exists")
        data=local(root,spec["input_csv"]);manifest=data.with_suffix(".manifest.json");audit_path=local(root,spec["input_audit"])
        checked=read_json(audit_path)
        input_record=record(data);manifest_sha=digest(manifest)
        if checked["csv_sha256"]!=input_record["sha256"] or checked["manifest_sha256"]!=manifest_sha:
            raise ValueError("Daily independent audit does not bind the inputs")
        output.mkdir(parents=True);(output/"inputs").mkdir()
        shutil.copy2(manifest,output/"inputs/daily.manifest.json");shutil.copy2(audit_path,output/"inputs/daily-audit.json")
        delivered=capture_delivered(root,spec,output/"delivered")
        if delivered["vendor_seed_inventory_not_distributed"]["data/btc-1d.csv"]["sha256"]!=input_record["sha256"]:
            raise ValueError("Delivered and new daily source bytes differ")
        files={n:local(root,n) for n in g}
        for n in ("pyproject.toml","uv.lock",".python-version","README.md","tests/test_bot_extension.py"):
            files[n]=local(root,n)
        for p in (output/"delivered").rglob("*"):
            if p.is_file() and p.suffix.lower() not in (".csv",".npz"):
                files["evidence/"+p.relative_to(output).as_posix()]=p
        members={}
        with ZipFile(output/"sources.zip","w",ZIP_DEFLATED) as z:
            for name,p in sorted(files.items()):
                if not safe(name):raise ValueError("Unsafe source snapshot member")
                payload=p.read_bytes();info=ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED;z.writestr(info,payload)
                members[name]={"sha256":hashlib.sha256(payload).hexdigest(),"bytes":len(payload)}
        check_guard(root,g)
        check_record(data,input_record)
        if digest(manifest)!=manifest_sha:raise ValueError("Daily manifest changed while freezing")
        frozen={"kind":"post_protocol_bot_extension_freeze","created_at":utc_now(),"attempt_id":identifier,"spec":spec,"spec_sha256":digest(spec_path),
                "guard":g,"runtime":{"python":platform.python_version(),"numpy":np.__version__},"source_snapshot":"sources.zip","source_snapshot_sha256":digest(output/"sources.zip"),
                "snapshot_members":members,"input":{"path":spec["input_csv"],**input_record,"manifest_sha256":manifest_sha,"distribution":"Vendor CSV excluded; full replay requires exact separately restored bytes"},
                "delivered":delivered,"preserved_inputs":{p.relative_to(output).as_posix():record(p) for p in sorted(output.rglob("*")) if p.is_file() and p.name!="sources.zip"},"scope":LIMIT}
        frozen["freeze_sha256"]=seal(frozen);json_write(output/"freeze.json",frozen)
        ledger.finish(identifier,"completed",{"output":str(output.resolve()),"freeze_file_sha256":digest(output/"freeze.json")})
        return frozen
    except Exception as error:
        ledger.finish(identifier,"failed",{"error":str(error),"partial_output":str(output)})
        raise


def verify_freeze(collection, *, root=None):
    collection=Path(collection);f=read_json(collection/"freeze.json");payload={k:v for k,v in f.items() if k!="freeze_sha256"}
    if f.get("kind")!="post_protocol_bot_extension_freeze" or f["freeze_sha256"]!=seal(payload):raise ValueError("Changed extension freeze")
    if set(f["guard"])!={*GUARDED,f["spec"]["protocol"],f["spec"]["base_config"]}:raise ValueError("Incomplete execution guard")
    archive=collection/f["source_snapshot"]
    if not safe(f["source_snapshot"]) or digest(archive)!=f["source_snapshot_sha256"]:raise ValueError("Changed extension source archive")
    with ZipFile(archive) as z:
        if len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!=set(f["snapshot_members"]):raise ValueError("Changed source inventory")
        for name,expected in f["snapshot_members"].items():
            if not safe(name) or Path(name).suffix.lower() in (".csv",".npz"):raise ValueError("Forbidden source snapshot payload")
            b=z.read(name)
            if {"sha256":hashlib.sha256(b).hexdigest(),"bytes":len(b)}!=expected:raise ValueError("Changed source member")
        for name,sha in f["guard"].items():
            if hashlib.sha256(z.read(name)).hexdigest()!=sha:raise ValueError("Archived execution source differs")
        if json.loads(z.read(SPEC))!=f["spec"] or hashlib.sha256(z.read(SPEC)).hexdigest()!=f["spec_sha256"]:raise ValueError("Archived specification differs")
    for name,expected in f["preserved_inputs"].items():
        if not safe(name):raise ValueError("Unsafe captured evidence path")
        check_record(collection/name,expected)
    if verify_delivered(collection/"delivered")!=f["delivered"]:raise ValueError("Delivered summary changed")
    if root is not None:check_guard(root,f["guard"])
    return f


def matched_targets(bars, settings, windows=(40,50,60,80,100,150)):
    f=features(bars,settings);vote=np.full(len(bars),np.nan);close=bars.values[:,3]
    edges=np.r_[0,np.flatnonzero(np.diff(bars.times)!=settings.seconds*1000)+1,len(bars)]
    for begin,end in zip(edges[:-1],edges[1:],strict=True):
        for i in range(begin+max(windows)-1,end):
            if f.valid[i]:vote[i]=sum(close[i]>np.mean(close[i+1-k:i+1]) for k in windows)/len(windows)
    return {"sma":vote*f.risk_weight,"ema":f.targets[(settings.fast,settings.slow)],"volatility":f.risk_weight},f.valid


def paired_difference(differences, spec):
    bs=spec["bootstrap"];x=np.asarray(differences)
    return {"cumulative_log_difference":float(x.sum()),"annualized_mean_log_difference":float(x.mean()*365),
            "bootstrap_by_block_days":{str(d):paired_block_bootstrap(x,block_length=d,draws=bs["draws"],seed=bs["seed"],annualization=365,confidence=bs["confidence"]) for d in bs["block_days"]},"scope":LIMIT}


def compute(bars, spec, base):
    """Pure computation, reusable by local synthetic fixtures and archived replay."""
    quality=audit(bars,allow_gaps=True,as_of_ms=timestamp(date.fromisoformat(spec["score_end"])+timedelta(days=1)))
    begin=int(np.searchsorted(bars.times,timestamp(date.fromisoformat(spec["score_start"]))))
    finish=timestamp(date.fromisoformat(spec["score_end"])+timedelta(days=1))
    if quality["zero_volume_bars"] or bars.times[0]!=timestamp(date.fromisoformat(spec["prehistory_start"])) or bars.times[-1]!=finish-86400000 or not 1<=begin<len(bars)-1 or bars.times[begin]!=timestamp(date.fromisoformat(spec["score_start"])):
        raise ValueError("Missing complete source/score boundaries or invalid volume")
    settings={};targets={};valid=None
    for risk in spec["volatility_targets"]:
        s=replace(base.at_interval("1d"),source=Path(spec["base_config"]),initial_equity=spec["initial_equity"],fast=spec["ema_pair"][0],slow=spec["ema_pair"][1],
                  warmup=spec["warmup"],vol_window=spec["volatility_window"],vol_target=risk,band=spec["band"],max_weight=spec["maximum_exposure"])
        result,mask=matched_targets(bars,s,tuple(spec["sma_windows"]))
        if valid is not None and not np.array_equal(valid,mask):raise ValueError("Risk targets changed common validity")
        valid=mask;label=str(round(risk*100))
        for name in ("sma","ema","volatility"):targets[name+"_"+label]=result[name]
        settings[label]=s
    if not valid[begin-1]:raise ValueError("Scored boundary lacks common completed feature history")
    if not np.all(np.diff(bars.times[begin-1:])==86400000):raise ValueError("Paired scored window has missing daily intervals")
    bh=np.full(len(bars),np.nan);bh[np.flatnonzero(valid)[0]:]=1.
    targets.update(cash=np.zeros(len(bars)),buy_hold=bh)
    arrays={"open_time_ms":bars.times,"close_time_ms":bars.close_times,"common_valid":valid}
    arrays.update({"target__"+name:targets[name] for name in BOOKS})
    scenarios={};trades={}
    for cost in spec["costs_bps"]:
        cs=format(cost,"g");books={};scenario={"metrics":{},"initial_state":{},"contrasts":{}}
        trades[cs]={}
        for name in BOOKS:
            s=settings["40" if name.endswith("40") else "20"]
            book=simulate(bars,targets[name],s,cost,name);books[name]=book
            scenario["metrics"][name]=metrics(book,bars,begin,len(bars),365,cost)
            scenario["initial_state"][name]={"nav":float(book.nav[begin-1]),"cash":float(book.cash[begin-1]),"coins":float(book.coins[begin-1]),"valuation_time":iso(bars.close_times[begin-1])}
            for field in FIELDS:arrays[f"cost{cs}__{name}__{field}"]=getattr(book,field)
            trades[cs][name]=book.trades
        for label in ("20","40"):
            a,b=books["sma_"+label],books["ema_"+label]
            scenario["contrasts"]["sma_"+label+"_minus_ema_"+label]=paired_difference(a.log_returns[begin:]-b.log_returns[begin:],spec)
        scenarios[cs]=scenario
    return {"schema_version":1,"kind":"post_outcome_exploratory_matched_bot_study","scope":LIMIT,"score_start":iso(bars.times[begin]),"score_end":iso(bars.close_times[-1]),
            "score_start_index":begin,"scored_bars":len(bars)-begin,"full_history_bars":len(bars),"common_valid_before_score":True,"settings_by_target":{k:json.loads(json.dumps(asdict(s),default=str)) for k,s in settings.items()},
            "audit":quality,"scenarios":scenarios,"books":list(BOOKS),"costs_bps":spec["costs_bps"],"risk_interpretation":"Matched target parameters; realized exposures/volatility may differ. SMA .10/334 variants are distinct from delivered .15/150 legacy_daily."},arrays,trades


def run(collection, *, root=ROOT):
    collection=Path(collection);root=Path(root).resolve();ledger=Ledger(root/"runs/research.sqlite")
    identifier=ledger.start("bot_extension_study",{"collection":str(collection),"scope":LIMIT},phase="post_outcome_exploratory",code=digest(Path(__file__)))
    output=collection/"attempts"/identifier
    try:
        if (collection/"registry.json").exists():raise ValueError("Accepted extension already exists; preserve prior evidence")
        f=verify_freeze(collection,root=root);spec=f["spec"]
        if f["runtime"]!={"python":platform.python_version(),"numpy":np.__version__}:raise ValueError("Frozen extension runtime differs")
        data=local(root,f["input"]["path"]);check_record(data,{k:f["input"][k] for k in ("sha256","bytes")})
        if data.with_suffix(".manifest.json").exists() and digest(data.with_suffix(".manifest.json"))!=f["input"]["manifest_sha256"]:raise ValueError("Restored daily manifest differs")
        # The exact CSV and captured manifest are separately hash-bound. Public
        # restoration need not recreate an old absolute source-manifest path.
        bars=read_bars(data,interval="1d",verify_manifest=False);base=load_settings(local(root,spec["base_config"]))
        output.mkdir(parents=True)
        report,arrays,trades=compute(bars,spec,base)
        report.update(freeze_file_sha256=digest(collection/"freeze.json"),source_snapshot_sha256=f["source_snapshot_sha256"],input_csv_sha256=f["input"]["sha256"])
        json_write(output/"report.json",report);np.savez_compressed(output/"paths.npz",**arrays);json_write(output/"trades.json",trades)
        verify_paths(report,output,f)
        check_guard(root,f["guard"]);check_record(data,{k:f["input"][k] for k in ("sha256","bytes")})
        with ledger.connect() as src,sqlite3.connect(collection/"attempt-ledger.sqlite") as dst:src.backup(dst)
        json_write(collection/"attempt-ledger.json",Ledger(collection/"attempt-ledger.sqlite").rows())
        registry={"kind":"bot_extension_result_collection","created_at":utc_now(),"run_attempt_id":identifier,"freeze_attempt_id":f["attempt_id"],"matched":output.relative_to(collection).as_posix(),
                  "counts":{"matched_books":8,"cost_scenarios":5,"matched_paths":40,"paired_contrasts":10,"paired_intervals":30,"preserved_delivered_paths":25},
                  "files":{p.relative_to(collection).as_posix():record(p) for p in sorted(collection.rglob("*")) if p.is_file()},
                  "runtime":f["runtime"],"scope":LIMIT,"ledger_snapshot_timing":"Pre-finalization snapshot: current run row remains started; terminal row copied to completion.json and originating ledger"}
        json_write(collection/"registry.json",registry)
        ledger.finish(identifier,"completed",{"registry_sha256":digest(collection/"registry.json"),"collection":str(collection.resolve())})
        json_write(collection/"completion.json",next(r for r in ledger.rows() if r["id"]==identifier))
        verify(collection)
        return registry
    except Exception as error:
        row=next(r for r in ledger.rows() if r["id"]==identifier)
        if row["status"]=="started":ledger.finish(identifier,"failed",{"error":str(error),"partial_output":str(output)})
        raise


def verify_paths(report,path,f):
    """Validate paths/estimands before finalizing a run, without vendor prices."""
    trades=read_json(path/"trades.json")
    if report["books"]!=list(BOOKS) or report["costs_bps"]!=f["spec"]["costs_bps"] or set(report["scenarios"])!={format(c,"g") for c in f["spec"]["costs_bps"]}:
        raise ValueError("Matched policy/cost inventory differs")
    with np.load(path/"paths.npz",allow_pickle=False) as z:
        start=report["score_start_index"];n=report["full_history_bars"]
        if z["open_time_ms"].shape!=(n,) or len(z["open_time_ms"])-start!=report["scored_bars"] or not z["common_valid"][start-1]:raise ValueError("Invalid saved score boundary")
        for cost,scenario in report["scenarios"].items():
            if set(scenario["metrics"])!=set(BOOKS) or set(trades[cost])!=set(BOOKS):raise ValueError("Matched book inventory differs")
            bp=f"cost{cost}__buy_hold__"
            close=np.divide(z[bp+"nav"]-z[bp+"cash"],z[bp+"coins"],out=np.zeros(n),where=z[bp+"coins"]>0)
            for name,m in scenario["metrics"].items():
                p=f"cost{cost}__{name}__";nav=z[p+"nav"];cash=z[p+"cash"];coins=z[p+"coins"];fees=z[p+"costs"]
                if any(z[p+k].shape!=(n,) or not np.isfinite(z[p+k]).all() for k in FIELDS) or np.any(nav<=0) or np.any(cash<-1e-12) or np.any(coins<-1e-12):raise ValueError("Invalid saved account path")
                initial=scenario["initial_state"][name]
                for field in ("nav","cash","coins"):
                    if float(z[p+field][start-1])!=initial[field]:raise ValueError("Inherited state differs")
                if not math.isclose(float(nav[-1]/nav[start-1]-1),m["total_return"],abs_tol=1e-13,rel_tol=0):raise ValueError("Endpoint return differs")
                inferred=cash+coins*close
                if not np.allclose(nav,inferred,atol=1e-10,rtol=1e-12):raise ValueError("Accounts do not agree on the underlying closing valuation")
                expected_weights=np.divide(coins*close,nav)
                if not np.allclose(expected_weights,z[p+"weights"],atol=1e-12,rtol=0):raise ValueError("Closing exposure differs")
                values=nav[start-1:];returns=values[1:]/values[:-1]-1;logs=np.log(values[1:]/values[:-1]);std=float(np.std(returns,ddof=1))
                expected_metrics={"mean_log_return":float(logs.mean()),"annualized_mean_log_return":float(logs.mean()*365),
                    "annualized_volatility":std*math.sqrt(365),"descriptive_sharpe":float(returns.mean()/std*math.sqrt(365)) if std>0 else None,
                    "maximum_drawdown":float(np.min(values/np.maximum.accumulate(values)-1)),"mean_exposure":float(z[p+"weights"][start:].mean()),
                    "time_in_market":float((z[p+"weights"][start:]>1e-10).mean()),"turnover":float(z[p+"turnover"][start:].sum()),"costs_in_start_nav_units":float(fees[start:].sum()/values[0])}
                if any(m[k]!=value if value is None else not math.isclose(m[k],value,abs_tol=1e-12,rel_tol=1e-12) for k,value in expected_metrics.items()):raise ValueError("Saved financial metric disagrees with its path")
                events={t["bar_index"]:t for t in trades[cost][name]}
                if len(events)!=len(trades[cost][name]) or any(type(i) is not int or not 1<=i<n for i in events):raise ValueError("Duplicate/invalid trade index")
                for i in range(1,n):
                    t=events.get(i);dc=cash[i]-cash[i-1];dq=coins[i]-coins[i-1]
                    if t is None:
                        if abs(dc)>1e-10 or abs(dq)>1e-12 or fees[i]!=0:raise ValueError("Account changed without a trade")
                    else:
                        if z["open_time_ms"][i]-z["open_time_ms"][i-1]!=86400000 or not np.isfinite(z["target__"+name][i-1]):raise ValueError("Trade crossed missing/invalid history")
                        notional=t["signed_notional"];price=t["price"]
                        if abs(dc+notional+t["assumed_cost"])>1e-10 or abs(dq-notional/price)>1e-12 or abs(t["assumed_cost"]-abs(notional)*float(cost)/10000)>1e-10 or fees[i]!=t["assumed_cost"]:raise ValueError("Trade accounting differs")
                        before=cash[i-1]+coins[i-1]*price;after=cash[i]+coins[i]*price
                        if not math.isclose(coins[i]*price/after,t["target_weight_after_cost"],abs_tol=1e-12,rel_tol=0) or not math.isclose(z[p+"turnover"][i],abs(notional)/before,abs_tol=1e-12,rel_tol=0):raise ValueError("Post-fee target or turnover differs")
                        if t["decision_time"]!=iso(z["close_time_ms"][i-1]) or t["execution_time"]!=iso(z["open_time_ms"][i]) or t["target_weight_after_cost"]!=z["target__"+name][i-1]:raise ValueError("Trade anticipates its signal")
                if sum(start<=i<n for i in events)!=m["trade_count"]:raise ValueError("Scored trade count differs")
            for label in ("20","40"):
                aa=z[f"cost{cost}__sma_{label}__nav"];bb=z[f"cost{cost}__ema_{label}__nav"]
                difference=np.diff(np.log(aa))[start-1:]-np.diff(np.log(bb))[start-1:]
                paired=scenario["contrasts"][f"sma_{label}_minus_ema_{label}"]
                if not math.isclose(float(difference.sum()),paired["cumulative_log_difference"],abs_tol=1e-13,rel_tol=0) or not math.isclose(float(difference.mean()*365),paired["annualized_mean_log_difference"],abs_tol=1e-13,rel_tol=0):raise ValueError("Paired estimand differs")
                for days,interval in paired["bootstrap_by_block_days"].items():
                    if interval["observations"]!=len(difference) or interval["block_length"]!=int(days) or interval["seed"]!=f["spec"]["bootstrap"]["seed"] or interval["draws"]!=f["spec"]["bootstrap"]["draws"]:raise ValueError("Bootstrap design differs")


def verify(collection):
    """No vendor CSV, Downloads path or market recomputation is needed."""
    collection=Path(collection);f=verify_freeze(collection);r=read_json(collection/"registry.json");c=read_json(collection/"completion.json")
    if r.get("kind")!="bot_extension_result_collection" or c["id"]!=r["run_attempt_id"] or c["kind"]!="bot_extension_study" or c["status"]!="completed" or c["code_hash"]!=f["guard"]["scripts/bot_extension_study.py"] or c["details"]["outcome"]["registry_sha256"]!=digest(collection/"registry.json"):
        raise ValueError("Missing source-bound completed extension receipt")
    if r["freeze_attempt_id"]!=f["attempt_id"] or r["runtime"]!=f["runtime"] or r["counts"]!={"matched_books":8,"cost_scenarios":5,"matched_paths":40,"paired_contrasts":10,"paired_intervals":30,"preserved_delivered_paths":25}:raise ValueError("Collection design differs")
    if any(p.suffix.lower()==".csv" for p in collection.rglob("*") if p.is_file()):raise ValueError("Vendor CSV must not be distributed in this collection")
    for name,expected in r["files"].items():
        if not safe(name):raise ValueError("Unsafe collection inventory")
        check_record(collection/name,expected)
    path=local(collection,r["matched"]);report=read_json(path/"report.json")
    if report["freeze_file_sha256"]!=digest(collection/"freeze.json") or report["source_snapshot_sha256"]!=f["source_snapshot_sha256"] or report["input_csv_sha256"]!=f["input"]["sha256"]:
        raise ValueError("Result source/input identity differs")
    verify_paths(report,path,f)
    return {"registry":r,"freeze":f,"report":report,"delivered":f["delivered"]}


def write_csv(path, rows):
    with Path(path).open("w",newline="",encoding="utf-8") as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def build(collection, output):
    collection=Path(collection);output=Path(output);verified=verify(collection);r=verified["report"];d=verified["delivered"]
    if digest(Path(__file__))!=verified["freeze"]["guard"]["scripts/bot_extension_study.py"]:raise ValueError("Display builder differs from frozen source")
    output.mkdir(parents=True,exist_ok=True);rows=[];pairs=[]
    for cost,scenario in r["scenarios"].items():
        for name,m in scenario["metrics"].items():rows.append({"cost_bps":float(cost),"book":name,**{k:v for k,v in m.items() if not isinstance(v,(list,dict))}})
        for name,p in scenario["contrasts"].items():
            for days,b in p["bootstrap_by_block_days"].items():pairs.append({"cost_bps":float(cost),"contrast":name,"block_days":int(days),"annualized_mean_log_difference":p["annualized_mean_log_difference"],"lower":b["annualized_mean_difference_ci"][0],"upper":b["annualized_mean_difference_ci"][1],"draws":b["draws"],"seed":b["seed"]})
    write_csv(output/"metrics.csv",rows);write_csv(output/"paired.csv",pairs)
    macros={"BotDeliveredReturn":100*d["legacy_metrics_by_cost"]["25"]["total_return"],"BotDeliveredDrawdown":-100*d["legacy_metrics_by_cost"]["25"]["maximum_drawdown"],"BotDeliveredHighCostReturn":100*d["legacy_metrics_by_cost"]["100"]["total_return"]}
    for label,word in (("20","Twenty"),("40","Forty")):
        for method in ("sma","ema"):macros["Bot"+method.title()+word+"Return"]=100*r["scenarios"]["25"]["metrics"][method+"_"+label]["total_return"]
        p=r["scenarios"]["25"]["contrasts"]["sma_"+label+"_minus_ema_"+label]
        macros["Bot"+word+"Contrast"]=100*p["annualized_mean_log_difference"]
        for bound,index in (("Lower",0),("Upper",1)):macros["Bot"+word+"Contrast"+bound]=100*p["bootstrap_by_block_days"]["30"]["annualized_mean_difference_ci"][index]
    (output/"numbers.tex").write_text("% Generated from frozen exploratory records; returns and annual log contrasts in percent.\n"+"\n".join("\\newcommand{\\"+k+"}{"+f"{v:.4f}"+"}" for k,v in macros.items())+"\n",encoding="utf-8")
    lines=[r"\begin{longtable}{rlrrrrr}",r"\caption{Post-outcome matched daily settings. Returns, realized annual volatility, exposure and drawdown are percent; turnover is unscaled. No strategy is selected.}\label{tab:botextensionmetrics}\\",r"\toprule Cost & Book & Return & Vol. & Exposure & Turnover & Drawdown \\",r"\midrule\endfirsthead",r"\toprule Cost & Book & Return & Vol. & Exposure & Turnover & Drawdown \\",r"\midrule\endhead"]
    for x in rows:lines.append(f"{x['cost_bps']:g} & "+str(x['book']).replace("_",r"\_")+f" & {100*x['total_return']:.2f} & {100*x['annualized_volatility']:.2f} & {100*x['mean_exposure']:.2f} & {x['turnover']:.2f} & {100*x['maximum_drawdown']:.2f}"+r" \\")
    lines.extend([r"\bottomrule\end{longtable}",r"\begin{longtable}{rlrr}",r"\caption{SMA-minus-EMA annual mean-log differences in percent, at matched target settings. Approximate unadjusted 95\% 30-day block intervals; all 15/30/60-day intervals are in paired.csv.}\label{tab:botextensionpaired}\\",r"\toprule Cost & Contrast & Difference & Interval \\",r"\midrule\endfirsthead",r"\toprule Cost & Contrast & Difference & Interval \\",r"\midrule\endhead"])
    for x in pairs:
        if x["block_days"]==30:lines.append(f"{x['cost_bps']:g} & "+x["contrast"].replace("_",r"\_")+f" & {100*x['annualized_mean_log_difference']:.2f} & [{100*x['lower']:.2f}, {100*x['upper']:.2f}]"+r" \\")
    lines.append(r"\bottomrule\end{longtable}");(output/"table.tex").write_text("\n".join(lines)+"\n",encoding="utf-8")
    trace={"kind":"bot_extension_display_trace","registry_sha256":digest(collection/"registry.json"),"freeze_file_sha256":digest(collection/"freeze.json"),"source_snapshot_sha256":verified["freeze"]["source_snapshot_sha256"],"generator_sha256":digest(Path(__file__)),"counts":{"metrics_rows":len(rows),"paired_rows":len(pairs)},"macros":macros,"scope":LIMIT,
           "output_sha256":{n:digest(output/n) for n in ("metrics.csv","paired.csv","numbers.tex","table.tex")}}
    json_write(output/"traceability.json",trace);return trace


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("mode",choices=("freeze","run","verify","build"));parser.add_argument("--collection",type=Path,default=ROOT/"results/bot-extension-v1");parser.add_argument("--root",type=Path,default=ROOT);parser.add_argument("--output",type=Path,default=ROOT/"paper/generated/bot-extension");args=parser.parse_args()
    result=freeze(args.collection,root=args.root) if args.mode=="freeze" else run(args.collection,root=args.root) if args.mode=="run" else verify(args.collection) if args.mode=="verify" else build(args.collection,args.output)
    print(json.dumps(result,indent=2,allow_nan=False))
