"""Synthetic fixtures for the post-protocol extension; no vendor/network input."""
from dataclasses import replace
from datetime import date,timedelta
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

import numpy as np
import pytest

from quant.config import load_settings
from quant.data import Bars,digest,json_write,timestamp
from quant.ledger import Ledger
from scripts import bot_extension_study as ext


PROJECT=Path(__file__).resolve().parents[1]


def fixture_spec(n=750):
    s=ext.load_spec(PROJECT/ext.SPEC)
    s["prehistory_start"]="2017-09-01"
    s["score_start"]=(date(2017,9,1)+timedelta(days=334)).isoformat()
    s["score_end"]=(date(2017,9,1)+timedelta(days=n-1)).isoformat()
    s["bootstrap"]={"draws":100,"block_days":[15,30,60],"seed":20261023,"confidence":.95}
    return s


def fixture_bars(n=750):
    t=np.arange(n,dtype=np.int64)*86400000+timestamp(date(2017,9,1))
    i=np.arange(n);close=100*np.exp(.0004*i+.08*np.sin(i/17)+.03*np.sin(i/4))
    opening=close*np.exp(.003*np.cos(i/5))
    values=np.c_[opening,np.maximum(opening,close)*1.01,np.minimum(opening,close)*.99,close,np.ones(n)]
    return Bars(t,values,t+86400000-1,"1d",{})


@pytest.fixture
def calculated(tmp_path):
    spec=fixture_spec();bars=fixture_bars();base=load_settings(PROJECT/"configs/research/btc-trend.toml")
    report,arrays,trades=ext.compute(bars,spec,base)
    out=tmp_path/"computed";out.mkdir();json_write(out/"trades.json",trades);np.savez_compressed(out/"paths.npz",**arrays)
    return report,arrays,trades,out,{"spec":spec},bars


def test_fixed_design_rejects_parameter_change(tmp_path):
    s=ext.load_spec(PROJECT/ext.SPEC);s["band"]=.15;p=tmp_path/"bad.json";json_write(p,s)
    with pytest.raises(ValueError,match="new version"):ext.load_spec(p)


def test_shared_validity_and_past_only_signal():
    bars=fixture_bars();base=load_settings(PROJECT/"configs/research/btc-trend.toml").at_interval("1d")
    a,valid=ext.matched_targets(bars,base)
    other=bars.values.copy();other[501:,:4]*=1.3
    changed=Bars(bars.times,other,bars.close_times,"1d",{})
    b,valid2=ext.matched_targets(changed,base)
    for name in a:np.testing.assert_array_equal(a[name][:501],b[name][:501])
    assert not valid[:333].any() and valid[333]
    assert np.array_equal(np.isfinite(a["sma"]),valid)
    assert np.array_equal(np.isfinite(a["ema"]),valid)


def test_gap_resets_matched_validity():
    bars=fixture_bars(900);mask=np.ones(900,dtype=bool);mask[400]=False;bars=bars.take(mask)
    s=load_settings(PROJECT/"configs/research/btc-trend.toml").at_interval("1d")
    t,valid=ext.matched_targets(bars,s)
    assert not valid[400:733].any() and valid[733]
    assert not np.isfinite(t["sma"][400:733]).any()


def test_all_paths_match_risk_settings_and_exact_fees(calculated):
    report,arrays,trades,out,f,bars=calculated
    assert len(report["scenarios"])==5
    assert all(len(r["metrics"])==8 and len(r["contrasts"])==2 for r in report["scenarios"].values())
    for label in ("20","40"):
        s=report["settings_by_target"][label]
        assert (s["warmup"],s["band"],s["vol_window"],s["fast"],s["slow"])==(334,.1,30,9,34)
    ext.verify_paths(report,out,f)
    for cost in report["scenarios"]:
        for name in ext.BOOKS:
            p=f"cost{cost}__{name}__";nav=arrays[p+"nav"]
            np.testing.assert_allclose(nav,arrays[p+"cash"]+arrays[p+"coins"]*bars.values[:,3],atol=1e-12,rtol=0)
            assert np.all(arrays[p+"cash"]>=0) and np.all(arrays[p+"coins"]>=0)
            for t in trades[cost][name]:
                i=t["bar_index"]
                assert t["price"]==bars.values[i,0]
                assert t["target_weight_after_cost"]==arrays["target__"+name][i-1]


def test_saved_corruption_rejected_before_finalization(calculated):
    report,arrays,trades,out,f,_=calculated
    arrays["cost25__sma_20__nav"][-1]*=1.1
    np.savez_compressed(out/"paths.npz",**arrays)
    with pytest.raises(ValueError,match="Endpoint return"):ext.verify_paths(report,out,f)


def test_trade_timing_corruption_rejected(calculated):
    report,_,trades,out,f,_=calculated
    t=trades["25"]["sma_20"][0];t["decision_time"]=t["execution_time"]
    json_write(out/"trades.json",trades)
    with pytest.raises(ValueError,match="anticipates"):ext.verify_paths(report,out,f)


def test_scored_gap_is_rejected():
    bars=fixture_bars();mask=np.ones(len(bars),dtype=bool);mask[600]=False
    with pytest.raises(ValueError,match="missing daily"):
        ext.compute(bars.take(mask),fixture_spec(),load_settings(PROJECT/"configs/research/btc-trend.toml"))


def minimal_bot(root):
    """Fictional, actual-shaped installation chain; no production checks mocked."""
    bot=root/"bot";bot.mkdir()
    def put(name,payload):
        p=bot/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(payload);return p
    put("bot_core.py",b"# fictional source\n");put("legacy_daily.py",b"# fictional daily source\n")
    put("requirements.txt",b"numpy\n");put("pyproject.toml",b"[project]\nname='fixture'\n");put("uv.lock",b"fixture\n")
    put("config/paper.toml",b"fixture paper config\n");put("config/legacy_daily.json",b"{}\n")
    modules={}
    for name in ("config","data","engine","stats"):
        p=put("paper_engine/"+name+".py",b"# fictional module\n");modules[p.relative_to(bot).as_posix()]=digest(p)
    for name in ext.SEEDS:put(name,b"fictional vendor input never distributed\n")
    archive=bot/"legacy/original-v2.zip";archive.parent.mkdir();originals={}
    with ZipFile(archive,"w") as z:
        import hashlib
        for i in range(14):
            n=f"part{i}.py";payload=f"# original {i}\n".encode();z.writestr(n,payload);originals[n]=hashlib.sha256(payload).hexdigest()
    json_write(bot/"paper-origin.json",{"original_archive_in_bot":"legacy/original-v2.zip","original_archive_sha256":digest(archive),"original_files":originals,"paper_modules":modules,"paper_config_sha256":digest(bot/"config/paper.toml")})
    fp=ext.bot_fingerprint(bot);source={"source_fingerprint":fp}
    arrays={};scenarios={}
    books=("legacy_daily","paper_ema_daily_reference","cash","buy_hold","legacy_volatility_target")
    for cost in ("0","10","25","50","100"):
        scenarios[cost]={"metrics":{},"initial_state":{}}
        for name in books:
            arrays[f"cost{cost}__{name}__nav"]=np.array([1.,1.05])
            scenarios[cost]["metrics"][name]={"total_return":1.05/1.-1}
            scenarios[cost]["initial_state"][name]={"nav":1.}
    report={"policy":"legacy_daily","settings":{"source":"old path","vol_target":.4,"warmup":150,"band":.15},"data":{"local_path":"old vendor path"},"audit":{"as_of":"old time"},"source":source,"scenarios":scenarios}
    json_write(bot/"validation/legacy-report.json",report);np.savez_compressed(bot/"validation/legacy-paths.npz",**arrays);json_write(bot/"validation/legacy-trades.json",{})
    replay=root/"installed-replay";replay.mkdir();json_write(replay/"selections.json",[])
    outputs={"report.json":digest(bot/"validation/legacy-report.json"),"paths.npz":digest(bot/"validation/legacy-paths.npz"),"trades.json":digest(bot/"validation/legacy-trades.json"),"selections.json":digest(replay/"selections.json")}
    json_write(bot/"validation/legacy-attempt.json",{"status":"completed","source_fingerprint":fp,"outputs":outputs})
    for name in ("report","paths","trades"):
        suffix="npz" if name=="paths" else "json";shutil.copy2(bot/f"validation/legacy-{name}.{suffix}",replay/f"{name}.{suffix}")
    json_write(replay/"attempt.json",{"status":"completed","source_fingerprint":fp,"outputs":outputs})
    receipts={p.name:{"sha256":digest(p)} for p in (bot/"validation").iterdir()}
    json_write(bot/"validation/quality.json",{"source":source,"receipts":receipts})
    json_write(root/"previous-installation.json",{"status":"completed"});(root/"installed-tests.txt").write_text("50 passed\n")
    inv={p.relative_to(bot).as_posix():ext.record(p) for p in bot.rglob("*") if p.is_file()}
    installed={"status":"completed","source":source,"inventory":inv,"files_installed":len(inv),"original_backup_sha256":digest(archive),"previous_installation_sha256":digest(root/"previous-installation.json"),"installed_tests":{"log_sha256":digest(root/"installed-tests.txt")},"policy_checks":{"legacy_daily":{"report_sha256":digest(replay/"report.json")}}}
    json_write(root/"installation.json",installed)
    # Historical capture validates seeds; a distributed collection omits them.
    for name in ext.SEEDS:(bot/name).unlink()
    return root


def test_delivered_chain_verifies_without_vendor_seeds(tmp_path):
    root=minimal_bot(tmp_path)
    result=ext.verify_delivered(root)
    assert len(result["vendor_seed_inventory_not_distributed"])==4
    assert not list(root.rglob("*.csv"))


@pytest.mark.parametrize("which",["source","report","archive","installation","installed"])
def test_delivered_chain_rejects_corruption(tmp_path,which):
    root=minimal_bot(tmp_path)
    paths={"source":"bot/legacy_daily.py","report":"bot/validation/legacy-report.json","archive":"bot/legacy/original-v2.zip","installation":"previous-installation.json","installed":"installed-replay/report.json"}
    with (root/paths[which]).open("ab") as f:f.write(b" changed")
    with pytest.raises((ValueError,json.JSONDecodeError)):ext.verify_delivered(root)


def test_failed_run_attempt_is_preserved(tmp_path):
    root=tmp_path/"root";root.mkdir();collection=tmp_path/"missing"
    with pytest.raises(FileNotFoundError):ext.run(collection,root=root)
    rows=Ledger(root/"runs/research.sqlite").rows()
    assert len(rows)==1 and rows[0]["status"]=="failed"
    assert "collection" in rows[0]["details"] and "error" in rows[0]["details"]["outcome"]


def test_source_freeze_integrity_and_narrow_guard(tmp_path):
    collection=tmp_path/"collection";delivered=collection/"delivered";delivered.mkdir(parents=True)
    minimal_bot(delivered);spec=ext.load_spec(PROJECT/ext.SPEC);g=ext.guard(PROJECT,spec)
    members={}
    with ZipFile(collection/"sources.zip","w") as z:
        for name in g:
            source=PROJECT/name;z.write(source,name);members[name]=ext.record(source)
    frozen={"kind":"post_protocol_bot_extension_freeze","spec":spec,"spec_sha256":digest(PROJECT/ext.SPEC),"guard":g,"source_snapshot":"sources.zip","source_snapshot_sha256":digest(collection/"sources.zip"),"snapshot_members":members,
            "preserved_inputs":{p.relative_to(collection).as_posix():ext.record(p) for p in delivered.rglob("*") if p.is_file()},"delivered":ext.verify_delivered(delivered)}
    frozen["freeze_sha256"]=ext.seal(frozen);json_write(collection/"freeze.json",frozen)
    assert ext.verify_freeze(collection)["spec"]==spec
    mirror=tmp_path/"mirror"
    for name in g:
        dest=mirror/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PROJECT/name,dest)
    (mirror/"scripts/unrelated_release_workflow.py").write_text("# intentionally outside scientific guard\n")
    ext.verify_freeze(collection,root=mirror)
    with (mirror/"src/quant/engine.py").open("a") as f:f.write("\n# changed executed code\n")
    with pytest.raises(ValueError,match="executed scientific"):ext.verify_freeze(collection,root=mirror)
    with (collection/"sources.zip").open("ab") as f:f.write(b" changed source archive")
    with pytest.raises(ValueError,match="source archive"):ext.verify_freeze(collection)


def test_display_units_counts_and_source_guard(calculated,tmp_path,monkeypatch):
    report,_,_,_,_,_=calculated
    delivered={"legacy_metrics_by_cost":{"25":{"total_return":.11878399817929419,"maximum_drawdown":-.2516628506306685},"100":{"total_return":-.08442664193957095}}}
    collection=tmp_path/"collection";collection.mkdir();(collection/"registry.json").write_text("{}\n");(collection/"freeze.json").write_text("{}\n")
    verified={"report":report,"delivered":delivered,"freeze":{"guard":{"scripts/bot_extension_study.py":digest(Path(ext.__file__))},"source_snapshot_sha256":"fixture"}}
    monkeypatch.setattr(ext,"verify",lambda _:verified)
    trace=ext.build(collection,tmp_path/"display")
    assert trace["counts"]=={"metrics_rows":40,"paired_rows":30}
    assert trace["macros"]["BotDeliveredReturn"]==pytest.approx(11.878399817929419)
    text=(tmp_path/"display/numbers.tex").read_text()
    assert r"\newcommand{\BotDeliveredReturn}{11.8784}" in text
    assert "13.6577" not in text
    verified["freeze"]["guard"]["scripts/bot_extension_study.py"]="bad source"
    with pytest.raises(ValueError,match="Display builder differs"):ext.build(collection,tmp_path/"bad-display")
