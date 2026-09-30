"""Deterministic tests only: no remote model calls and no real spacecraft claims."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest
from hangtian.contracts import (validate, verify_case, verify_tasks, verify_critique, recompute,
                               export_task, schema, SCHEMAS)
from hangtian.data import DataError, load_csv, evaluate, parse_time, check_lineage
from hangtian.mining import detect, group_candidates, make_package
from hangtian.models import DeepSeekModel, MockModel, NoRedirect
from hangtian.factory import run
from hangtian.tools import TelemetryTools

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "synthetic"


@pytest.fixture
def setup_data():
    config = json.loads((ROOT / "configs/pipeline.example.json").read_text())
    manifest = json.loads((BASE / "manifest.json").read_text())
    data = load_csv(manifest["experiments"][0], BASE)
    groups = group_candidates(detect(data, config["mining"]), config["mining"])
    package = make_package(data, groups[0], config["mining"])
    return config, manifest, data, package


@pytest.mark.parametrize("stat,expected", [("mean", 15), ("median", 15), ("min", 15), ("max", 15), ("count", 10)])
def test_analytic_stat(setup_data, stat, expected):
    data = setup_data[2]
    assert evaluate(data, {"op": "stat", "channel": "P_Load1", "window": {"start_row": 0, "stop_row": 10}, "stat": stat}) == expected


def test_analytic_delta(setup_data):
    assert evaluate(setup_data[2], {"op": "delta", "channel": "P_Load1",
        "before": {"start_row": 0, "stop_row": 10}, "after": {"start_row": 25, "stop_row": 30}}) == -15


def test_duplicates_preserved(setup_data):
    data = setup_data[2]
    assert len(data.times) == 60 and data.times[39] == data.times[40]
    assert evaluate(data, {"op": "duplicate_count", "window": {"start_row": 0, "stop_row": 60}}) == 1


def test_timezones():
    spec = {"time_kind": "datetime"}
    assert parse_time("2026-01-01T08:00:00+08:00", spec) == parse_time("2026-01-01T00:00:00Z", spec)


@pytest.mark.parametrize("window", [{"start_row": -1, "stop_row": 4}, {"start_row": 4, "stop_row": 4},
                                    {"start_row": 10, "stop_row": 3}, {"start_row": 0, "stop_row": 61}])
def test_bad_windows(setup_data, window):
    with pytest.raises(DataError): setup_data[2].span(window)


def test_no_silent_truncation(setup_data):
    with pytest.raises(DataError): load_csv(setup_data[1]["experiments"][0], BASE, max_rows=10)


def test_missing_not_zero(setup_data):
    data = copy.deepcopy(setup_data[2]); data.columns["P_Load1"][0] = None
    with pytest.raises(DataError): evaluate(data, {"op": "stat", "channel": "P_Load1", "stat": "mean", "window": {"start_row": 0, "stop_row": 3}})


def test_temporal_metric_rejects_duplicates(setup_data):
    with pytest.raises(DataError): evaluate(setup_data[2], {"op": "first_crossing", "channel": "P_Load1",
       "threshold": 0, "direction": "below", "window": {"start_row": 0, "stop_row": 60}})


def test_temporal_metric_exact(setup_data):
    assert evaluate(setup_data[2], {"op": "first_crossing", "channel": "P_Load1", "threshold": 1,
                                   "direction": "below", "window": {"start_row": 0, "stop_row": 30}}) == 20


def test_detector_categories(setup_data):
    events = detect(setup_data[2], setup_data[0]["mining"])
    assert {e["detector"] for e in events} >= {"median_step", "isolated_spike", "repeated_time", "context_transition", "all_selected_channels_zero"}


def test_bounded_groups(setup_data):
    events = [{"start_row": i, "stop_row": i+1} for i in range(0, 100, 2)]
    groups = group_candidates(events, setup_data[0]["mining"])
    assert len(groups) > 1
    assert all(g[-1]["stop_row"] - g[0]["start_row"] <= 12 for g in groups)


def test_deterministic_package(setup_data):
    cfg, _, data, package = setup_data
    again = make_package(data, group_candidates(detect(data, cfg["mining"]), cfg["mining"])[0], cfg["mining"])
    assert package == again


def test_recompute(setup_data):
    assert len(recompute(setup_data[3], setup_data[2])) == len(setup_data[3]["facts"])


def test_corrupt_fact_rejected(setup_data):
    package = copy.deepcopy(setup_data[3]); package["facts"][0]["value"] += 5
    with pytest.raises(DataError): recompute(package, setup_data[2])


def test_snapshot_mismatch(setup_data):
    package = copy.deepcopy(setup_data[3]); package["source_sha256"] = "bad"
    with pytest.raises(DataError): recompute(package, setup_data[2])


def test_cross_split_lineage(setup_data):
    a = copy.deepcopy(setup_data[1]["experiments"][0]); b = copy.deepcopy(a)
    b.update(experiment_id="EXP_OTHER", split="test")
    with pytest.raises(DataError): check_lineage([a, b], BASE)


def test_same_bytes_different_group(setup_data):
    a = copy.deepcopy(setup_data[1]["experiments"][0]); b = copy.deepcopy(a)
    b.update(experiment_id="EXP_OTHER", lineage_group="ANOTHER")
    with pytest.raises(DataError): check_lineage([a, b], BASE)


def test_role_contracts(setup_data):
    package = setup_data[3]; model = MockModel()
    case = model.call("case_curator", {"package": package}, "case"); verify_case(case, package)
    tasks = model.call("task_generator", {"package": package}, "tasks"); verify_tasks(tasks, package)
    review = model.call("task_critic", {"package": package, "tasks": tasks}, "critique")
    verify_critique(review, tasks, package)


@pytest.mark.parametrize("mutation", ["extra", "bad_fact", "bad_package", "duplicate_id", "duplicate_structure", "duplicate_answer", "no_decision"])
def test_bad_tasks_blocked(setup_data, mutation):
    p = setup_data[3]; tasks = MockModel().call("task_generator", {"package": p}, "tasks"); t = tasks["tasks"][0]
    if mutation == "extra": t["python_code"] = "raise Exception()"
    if mutation == "bad_fact": t["numeric_checks"][0]["fact_id"] = "F_invented"
    if mutation == "bad_package": tasks["package_id"] = "P_wrong"
    if mutation == "duplicate_id": tasks["tasks"][1]["local_id"] = t["local_id"]
    if mutation == "duplicate_structure": tasks["tasks"][1]["task_type"] = t["task_type"]
    if mutation == "duplicate_answer": t["numeric_checks"][1]["answer_key"] = t["numeric_checks"][0]["answer_key"]
    if mutation == "no_decision": t["investigation_decisions"] = []
    with pytest.raises(DataError): verify_tasks(tasks, p)


@pytest.mark.parametrize("decision", ["accept", "basic_only"])
def test_critic_cannot_override_blocking(setup_data, decision):
    p=setup_data[3]; m=MockModel(); tasks=m.call("task_generator", {"package": p}, "tasks")
    review=m.call("task_critic", {"package": p, "tasks": tasks}, "critique")
    review["reviews"][0]["decision"]=decision
    review["reviews"][0]["issues"][0]["severity"]="blocking"
    with pytest.raises(DataError): verify_critique(review,tasks,p)


def test_missing_review(setup_data):
    p=setup_data[3]; m=MockModel(); tasks=m.call("task_generator", {"package":p}, "tasks")
    review=m.call("task_critic", {"package":p,"tasks":tasks}, "critique");review["reviews"].pop()
    with pytest.raises(DataError):verify_critique(review,tasks,p)


def test_public_export(setup_data):
    p=setup_data[3];task=MockModel().call("task_generator", {"package":p}, "tasks")["tasks"][0]
    public,private=export_task(task,p,recompute(p,setup_data[2]),"mock")
    assert public["status"] == "fixture_only" and private["expected_measurements"]
    text=json.dumps(public)
    for banned in ("source_sha256", "source_hashes", "source_manifest", "expected_measurements", "fact_id", "semantic_rubric", "telemetry.csv"):
        assert banned not in text


def test_tools_scope_and_stop(setup_data):
    p=setup_data[3];task=MockModel().call("task_generator", {"package":p}, "tasks")["tasks"][0]
    public,_=export_task(task,p,recompute(p,setup_data[2]),"mock");tools=TelemetryTools(setup_data[2],public)
    assert tools.call("inspect_channels",{})["observation_id"]
    with pytest.raises(DataError):tools.call("read_window",{"window":{"start_row":0,"stop_row":60},"channels":["P_Load1"]})
    with pytest.raises(DataError):tools.call("read_window",{"window":public["permitted_window"],"channels":["PRIVATE_LABEL"]})
    assert tools.call("summarize_window",{"window":public["permitted_window"],"channel":"P_Load1","stat":"mean"})
    receipt=tools.call("submit_report",{"report":{"conclusion":"unresolved"}})
    assert receipt["result"]["correctness"]=="not_evaluated"
    with pytest.raises(DataError):tools.call("inspect_channels",{})


@pytest.mark.parametrize("flags", [(False,False),(True,False),(False,True)])
def test_no_implicit_remote(setup_data,tmp_path,flags):
    with pytest.raises(DataError):DeepSeekModel(setup_data[0],ROOT,tmp_path,*flags)


def test_redirect_never_forwarded():
    assert NoRedirect().redirect_request(None,None,302,"",{},"https://other.invalid") is None


def test_api_missing_key(setup_data,tmp_path,monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY",raising=False)
    model=DeepSeekModel(setup_data[0],ROOT,tmp_path,True,True)
    with pytest.raises(DataError):model.call("case_curator",{"package":setup_data[3]},"case")


@pytest.mark.parametrize("kind", list(SCHEMAS))
def test_schema_snapshots(kind):
    assert json.loads((ROOT / "schemas" / f"{kind}.schema.json").read_text()) == schema(kind)


def test_full_offline_run(setup_data,tmp_path):
    cfg,manifest,_,_=setup_data
    summary=run(manifest,BASE,cfg,MockModel(),tmp_path/"run",ROOT)
    assert summary["status"]=="fixture_only"
    assert summary["counts"]["failed_packages"]==0
    assert summary["counts"]["exported_tasks"]>0
    with pytest.raises(DataError):run(manifest,BASE,cfg,MockModel(),tmp_path/"run",ROOT)


def test_rejected_case_not_exported(setup_data,tmp_path):
    class Reject(MockModel):
        def call(self,role,payload,kind):
            result=super().call(role,payload,kind)
            if role=="case_curator":result["decision"]="defer"
            return result
    result=run(setup_data[1],BASE,setup_data[0],Reject(),tmp_path/"run",ROOT)
    assert result["counts"]["exported_tasks"]==0
    assert result["counts"]["deferred_or_rejected_cases"]>0


def test_bounded_repair(setup_data,tmp_path):
    class Repair(MockModel):
        def call(self,role,payload,kind):
            result=super().call(role,payload,kind)
            if role=="task_generator" and not payload.get("feedback"):
                result["tasks"][0]["numeric_checks"][0]["fact_id"]="F_bad"
            return result
    result=run(setup_data[1],BASE,setup_data[0],Repair(),tmp_path/"run",ROOT)
    assert result["counts"]["failed_packages"]==0
    assert result["counts"]["task_proposals"]>result["counts"]["exported_tasks"]
