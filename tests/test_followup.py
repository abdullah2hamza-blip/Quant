import json

import numpy as np
import pytest

from quant.followup import METHODS, ROOT, SPEC, agrapa_stake, coherent_eb_log_components, eb_log_factor, load_spec, run, simulate
from quant.ledger import Ledger


def test_complete_separately_specified_factorial_rejects_missing_case(tmp_path):
    spec = load_spec(ROOT/SPEC)
    assert len(spec["cases"]) == 25
    assert spec["cases"][-1]["prefix_weak"]
    spec["cases"].pop()
    path = tmp_path/"bad.json"
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError,match="factorial"):
        load_spec(path)


def test_empirical_bernstein_robust_factor_uses_both_endpoints():
    lambdas = np.array([.025,.05,.1,.2,.4])
    center = np.array([.9])
    low,high = np.array([-.8]),np.array([.8])
    robust = np.minimum(eb_log_factor(low,center,lambdas),eb_log_factor(high,center,lambdas))
    grid = np.linspace(-.8,.8,101)[:,None]
    assert np.all(eb_log_factor(grid,center,lambdas)>=robust-1e-14)
    # For another valid predictable center the factor can decrease with utility;
    # evaluating only the lower endpoint would be optimistic.
    x = np.array([.8,.9])
    values = eb_log_factor(x,np.array([-1.,-1.]),np.array([.4]))[:,0]
    assert values[1]<values[0]


def test_five_sums_reproduce_full_path_profile_and_dominate_local_minima():
    a = np.array([.2,-.1,.3,.1])
    d = np.array([.4,-.4,.4,-.4])
    center = np.array([0.,.1,-.1,.2])
    lo,hi = .02,.15
    grid = np.array([.025,.05,.1,.2,.4])
    sums = np.array([a.sum(),d.sum(),np.sum((a-center)**2),np.sum((a-center)*d),np.sum(d*d)])
    result = coherent_eb_log_components(sums,lo,hi,grid)
    direct = np.minimum(eb_log_factor(a-d*lo,center,grid).sum(axis=0),eb_log_factor(a-d*hi,center,grid).sum(axis=0))
    local = np.minimum(eb_log_factor(a-d*lo,center,grid),eb_log_factor(a-d*hi,center,grid)).sum(axis=0)
    np.testing.assert_allclose(result,direct,atol=1e-15)
    assert np.all(result>=local-1e-15)
    for theta in np.linspace(lo,hi,51):
        assert np.all(eb_log_factor(a-d*theta,center,grid).sum(axis=0)>=result-1e-15)


def test_one_sided_agrapa_uses_prior_sums_and_stays_strong_null_only():
    x = np.array([.2,-.1,.3])
    np.testing.assert_equal(agrapa_stake(np.zeros(1),np.zeros(1),0),[.1])
    stake = agrapa_stake(np.array([x.sum(),-1.,0.]),np.array([(x*x).sum(),1.,0.]),3)
    np.testing.assert_allclose(stake,[.8,0.,0.])
    # A predictable calendar stake can fail under a prefix-weak null.
    deterministic = np.r_[np.full(400,-.06),np.full(400,.06)]
    assert np.max(np.cumsum(deterministic))<1e-10
    stake = np.r_[np.zeros(400),np.full(400,.8)]
    assert np.log1p(stake*deterministic).sum()>np.log(250)


def test_smoke_is_deterministic_and_retains_world_level_timing_and_truth():
    spec = load_spec(ROOT/SPEC)
    case = next(c for c in spec["cases"] if c["turnover_pattern"] == "alternating" and c["cost_information"] == "contracting" and c["effect"] == .05)
    report,arrays = simulate(spec,case,smoke=True)
    again,other = simulate(spec,case,smoke=True)
    assert report["kind"] == "smoke" and report["worlds"] == 128 and report["steps"] == 60
    assert arrays["hits"].shape == (len(METHODS),128,10)
    assert arrays["true_null"].tolist() == [False]+[True]*9
    for key in arrays:
        np.testing.assert_array_equal(arrays[key],other[key])
    assert [t["calibration_n"] for t in report["trace"]] == [32,61,91]
    assert np.all(arrays["final_log_components"][9]>=arrays["final_log_components"][7]-1e-9)
    assert np.all(arrays["final_log_components"][7]>=arrays["final_log_components"][8]-1e-9)
    assert np.all((arrays["selected"]>=-1)&(arrays["selected"]<10))


def test_prefix_diagnostic_does_not_advertise_an_adaptive_bet_guarantee():
    spec = load_spec(ROOT/SPEC)
    report,_ = simulate(spec,spec["cases"][-1],smoke=True)
    for name in METHODS:
        if "agrapa" in name:
            assert "unsupported" in report["methods"][name]["guarantee"]
        else:
            assert "prefix-weak" in report["methods"][name]["guarantee"]


def test_unfrozen_substantive_attempt_is_recorded_as_failed(tmp_path):
    ledger = tmp_path/"ledger.sqlite"
    with pytest.raises(ValueError,match="requires a reviewed"):
        run(tmp_path/"out",None,ledger_path=ledger)
    rows = Ledger(ledger).rows()
    assert len(rows) == 1 and rows[0]["status"] == "failed"
    assert not (tmp_path/"out").exists()


def test_empty_calibration_intersection_suspends_cost_evidence(monkeypatch):
    from quant import followup
    def disjoint(total,n,cap,delta):
        if n == 32:
            return np.zeros_like(total),np.full_like(total,.03)
        return np.full_like(total,.1),np.full_like(total,.2)
    monkeypatch.setattr(followup,"_calibration_bounds",disjoint)
    spec = load_spec(ROOT/SPEC)
    case = next(c for c in spec["cases"] if c["cost_information"] == "contracting")
    _,arrays = simulate(spec,case,smoke=True)
    assert arrays["cost_conflict"].all() and arrays["cost_coverage_failed"].all()
    assert not arrays["hits"][[1,2,4,5,7,8,9]].any()


def test_case_failure_preserves_partial_manifest_and_terminal_attempts(tmp_path,monkeypatch):
    from quant import followup
    def fail(*args,**kwargs):
        raise RuntimeError("injected case failure")
    monkeypatch.setattr(followup,"simulate",fail)
    ledger = tmp_path/"ledger.sqlite"
    output = tmp_path/"partial"
    with pytest.raises(RuntimeError,match="injected case"):
        run(output,None,smoke=True,ledger_path=ledger)
    assert json.loads((output/"manifest.json").read_text())["cases"] == []
    rows = Ledger(ledger).rows()
    assert len(rows) == 2 and all(r["status"] == "failed" for r in rows)


def test_unused_final_calibration_conflict_is_separate_from_testing_coverage(monkeypatch):
    from quant import followup
    def conflict_only_after_last_label(total,n,cap,delta):
        if n<92:
            return np.zeros_like(total),np.full_like(total,.1)
        return np.full_like(total,.15),np.full_like(total,.2)
    monkeypatch.setattr(followup,"_calibration_bounds",conflict_only_after_last_label)
    spec = load_spec(ROOT/SPEC)
    case = next(c for c in spec["cases"] if c["cost_information"] == "contracting")
    report,arrays = simulate(spec,case,smoke=True)
    assert not arrays["cost_conflict"].any()
    assert not arrays["cost_coverage_failed"].any()
    assert arrays["cost_conflict_after_final_unused_calibration"].all()
    assert report["cost_conflict"]["estimate"] == 0
    assert report["cost_conflict_after_final_unused_calibration"]["estimate"] == 1
