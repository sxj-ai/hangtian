"""Integrity guards for private curation records; not scientific-quality tests."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest


def load(name):
    path=Path(__file__).resolve().parents[1]/"scripts"/(name+".py")
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(tmp_path):
    sha="a"*64
    report={"status":"passed","checked_fact_ids":["F1"],"origin":"synthetic_test_only"}
    payload=json.dumps(report).encode()
    (tmp_path/"verification.json").write_bytes(payload)
    record={"schema_version":"case-record-sidecar-1","case_id":"C0001","status":"accepted",
        "case_type":"single_source","family_id":"synthetic","parent_case_ids":[],"source_hashes":[sha],
        "source_artifacts":[{"telemetry_sha256":sha,"context_sha256":None,"label_sha256":None,"alignment":"telemetry_only"}],
        "scene":"Synthetic integrity test only",
        "windows":[{"source_sha256":sha,"rows":[0,10],"role":"whole_process","selection_reason":"fixture"}],
        "facts":[{"fact_id":"F1","source_sha256":sha,"rows":[0,10],"channels":["x"],"operation":"median",
                  "parameters":{},"result":1,"unit":None,"verification_status":"passed"}],
        "claims":[{"statement":"fixture","verdict":"supported","fact_ids":["F1"],"scope_and_limits":"fixture only"}],
        "limitations":["synthetic"],"distinction":{"disposition":"core","nearest_case_ids":[],"merge_into":None,"reason":"fixture"},
        "public_scope":{"record_selection":["R1"],"neutral_context":[],"leakage_review":"passed"},
        "verification":{"status":"passed","report_file":"verification.json","report_sha256":hashlib.sha256(payload).hexdigest(),"method":"synthetic check"},
        "review":{"decision":"accept","reviewed_content_sha256":None,"reviewer":"synthetic reviewer","independence":"none, fixture",
                  "blocking_issues":[],"rationale":"test only"}}
    m=load("validate_case_record")
    report["checked_facts_sha256"]=m.facts_digest(record)
    payload=json.dumps(report).encode()
    (tmp_path/"verification.json").write_bytes(payload)
    record["verification"]["report_sha256"]=hashlib.sha256(payload).hexdigest()
    record["review"]["reviewed_content_sha256"]=m.content_digest(record)
    return record


def test_review_binding_expires_when_evidence_or_scope_changes(case,tmp_path):
    m=load("validate_case_record")
    m.validate_record(case,tmp_path,{"a"*64:10})
    for field in ("facts","public_scope"):
        changed=copy.deepcopy(case)
        if field=="facts":changed["facts"][0]["result"]=999
        else:changed["public_scope"]["record_selection"]=["different"]
        with pytest.raises(ValueError,match="stale review"):
            m.validate_record(changed,tmp_path,{"a"*64:10})


def test_unknown_fact_and_invalid_bounds_are_rejected(case,tmp_path):
    m=load("validate_case_record")
    changed=copy.deepcopy(case);changed["claims"][0]["fact_ids"]=["invented"]
    with pytest.raises(ValueError,match="Unknown claim"):
        m.validate_record(changed,tmp_path,{"a"*64:10})
    for bounds in ([10,10],[0,11],[9,2]):
        changed=copy.deepcopy(case);changed["windows"][0]["rows"]=bounds
        with pytest.raises(ValueError,match="source rows"):
            m.validate_record(changed,tmp_path,{"a"*64:10})


def test_claimed_acceptance_cannot_omit_or_tamper_verification(case,tmp_path):
    m=load("validate_case_record")
    changed=copy.deepcopy(case);changed["verification"]["status"]="pending"
    changed["review"]["reviewed_content_sha256"]=m.content_digest(changed)
    with pytest.raises(ValueError,match="raw verification"):
        m.validate_record(changed,tmp_path,{"a"*64:10})
    (tmp_path/"verification.json").write_text('{"status":"passed"}')
    with pytest.raises(ValueError,match="hash mismatch"):
        m.validate_record(case,tmp_path,{"a"*64:10})


def test_external_verification_path_is_rejected(case,tmp_path):
    m=load("validate_case_record")
    case["verification"]["report_file"]="../outside.json"
    case["review"]["reviewed_content_sha256"]=m.content_digest(case)
    with pytest.raises(ValueError,match="outside artifact"):
        m.validate_record(case,tmp_path,{"a"*64:10})


def test_old_raw_report_cannot_validate_changed_fact_even_with_new_review(case,tmp_path):
    m=load("validate_case_record")
    case["facts"][0]["result"]=999
    case["review"]["reviewed_content_sha256"]=m.content_digest(case)
    with pytest.raises(ValueError,match="checked facts"):
        m.validate_record(case,tmp_path,{"a"*64:10})


def test_only_untested_claims_cannot_be_accepted(case,tmp_path):
    m=load("validate_case_record")
    case["claims"][0]["verdict"]="untested"
    case["review"]["reviewed_content_sha256"]=m.content_digest(case)
    with pytest.raises(ValueError,match="lacks evidence"):
        m.validate_record(case,tmp_path,{"a"*64:10})


def test_auxiliary_source_change_invalidates_raw_verification(case,tmp_path):
    m=load("validate_case_record")
    case["source_artifacts"][0]["context_sha256"]="b"*64
    case["source_artifacts"][0]["alignment"]="rowwise_exact_time"
    case["review"]["reviewed_content_sha256"]=m.content_digest(case)
    with pytest.raises(ValueError,match="checked facts"):
        m.validate_record(case,tmp_path,{"a"*64:10})


def test_recovery_uses_elapsed_clock_not_consecutive_record_count():
    m=load("audit_case_capacity")
    assert m.runs([0,1,1,0,1])==[(1,3),(4,5)]
    assert m.sustained_offset([0,6,6,6],[0,4,4,9],5,3)=={"index":1,"offset_s":4.0}
    assert m.sustained_offset([0,6,0,6],[0,4,4,9],5,2)["index"] is None


def test_capacity_audit_cannot_write_under_raw_data(tmp_path):
    m=load("audit_case_capacity")
    raw=tmp_path/"raw";raw.mkdir()
    with pytest.raises(ValueError,match="outside the raw dataset"):
        m.audit(raw,tmp_path/"unused.json",raw/"new")
    assert not (raw/"new").exists()
