"""Small analytic fixtures: raw ordering, evidence gates, scope and resumption."""
import copy
import json
from pathlib import Path

import pytest

from hangtian.contracts import validate
from hangtian.data import DataError, digest, file_hash, write_json
from hangtian.materials import (MaterialTools, build_material, execute, leak_scan,
                               public_task, verify_proposal)
from hangtian.material_pipeline import checked_stage, equal_number, run_batch, task_review_gate, validate_answer


@pytest.fixture
def records():
    # Irregular timestamps: 3 records span 4 seconds. Never count rows as seconds.
    return {"R1": {"record_id": "R1", "series_id": "G1", "sequence_index": 1,
        "row_origin": 10, "time_s": [0., 1., 3., 4., 5., 7.],
        "channels": {"P_SA": [0., 5., 6., 7., 8., 0.], "I_Load1": [0., 2., 2., 2., 2., 0.], "Irradiation": [300.] * 6},
        "regions": {"low_irr": [10, 16], "full_cycle": [10, 16]}}}


def query(**kwargs):
    return {"record_id": "R1", "op": "stat", "region": "low_irr", "slice": "all",
            "channel": "P_SA", "stat": "median", **kwargs}


def onset(**kwargs):
    return {"record_id": "R1", "op": "first_sustained", "region": "low_irr", "slice": "all",
            "channel": "P_SA", "threshold": 5, "min_records": 3, **kwargs}


def test_elapsed_not_row_count_and_strict_threshold(records):
    result = execute(records, onset())
    assert result["value"] == 3 and result["onset_source_row"] == 12
    assert result["quality"]["gaps_gt_1s"] == 2


def test_absent_crossing_is_null(records):
    assert execute(records, onset(threshold=20))["value"] is None
    assert not equal_number(0, None)


def test_duplicate_preserved_but_temporal_metric_rejected(records):
    records["R1"]["time_s"][2] = 1
    assert execute(records, query())["quality"]["duplicate_extra_rows"] == 1
    assert execute(records, query())["quality"]["conflicting_timestamp_groups"] == 1
    with pytest.raises(DataError):
        execute(records, onset())


def test_scope_and_arbitrary_query_keys(records):
    tool = MaterialTools(records, ["R1"])
    with pytest.raises(DataError): tool.call(query(record_id="PRIVATE"))
    with pytest.raises(DataError): tool.call(query(channel="AnomalyLabel"))
    with pytest.raises(DataError): tool.call(query(code="print(1)"))
    with pytest.raises(DataError): tool.call(query(threshold=1))


def test_anchor_unavailable_is_not_fake_window(records):
    with pytest.raises(DataError): execute(records, query(slice="after_recovery30"))


def reference(records):
    q = query()
    f = {"fact_id": "F1", "query": q, "result": execute(records, q), "definition": "median", "unit": "W"}
    rule = {"interpretation_id": "C1", "statement": "The measured median exceeds 1.",
            "fact_ids": ["F1"], "expected_verdict": "supported", "basis_type": "analytic_fixture", "rationale": "6 > 1"}
    material = {"facts": [f], "interpretations": [rule], "material_id": "M1", "public_background": ["Synthetic fixture"],
                "record_catalog": [{"record_id": "R1"}], "channels": {}, "forbidden_public_strings": ["secret_fault_name"]}
    task = {"task_id": "T1", "slot_id": "S1", "title": "Assess the median", "prompt": "Compute and assess.",
            "measurement_ids": ["F1"], "interpretation_ids": ["C1"], "required_record_ids": ["R1"]}
    tool = MaterialTools(records, ["R1"])
    obs = tool.call(q)
    answer = {"measurements": [{"measurement_id": "F1", "value": obs["result"]["value"], "observation_id": obs["observation_id"]}],
        "interpretations": [{"interpretation_id": "C1", "verdict": "supported", "explanation": "Median exceeds one.", "observation_ids": [obs["observation_id"]]}],
        "limitations": ["Synthetic fixture only"]}
    return task, material, {"answer": answer, "observations": tool.observations}


def test_recompute_and_citation_validation(records):
    task, material, trajectory = reference(records)
    assert validate_answer(task, material, records, trajectory)["hard_pass"]


@pytest.mark.parametrize("fault", ["wrong_number", "fake_citation", "changed_observation", "wrong_verdict", "missing_measurement", "extra_measurement", "corrupt_reference"])
def test_validation_rejects_corruption(records, fault):
    task, material, tr = reference(records)
    if fault == "wrong_number": tr["answer"]["measurements"][0]["value"] += 1
    if fault == "fake_citation": tr["answer"]["interpretations"][0]["observation_ids"] = ["O_fake"]
    if fault == "changed_observation": tr["observations"][0]["result"]["value"] += 1
    if fault == "wrong_verdict": tr["answer"]["interpretations"][0]["verdict"] = "insufficient"
    if fault == "missing_measurement": tr["answer"]["measurements"] = []
    if fault == "extra_measurement": tr["answer"]["measurements"].append(copy.deepcopy(tr["answer"]["measurements"][0]))
    if fault == "corrupt_reference": material["facts"][0]["result"]["value"] += 1
    assert not validate_answer(task, material, records, tr)["hard_pass"]


def test_public_whitelist(records):
    task, material, _ = reference(records)
    material['record_catalog'][0]['quality'] = {'conflict_channels': ['PRIVATE_RESULT'], 'duplicate_extra_rows': 4}
    exported = public_task(task, material)
    raw = json.dumps(exported)
    assert 'PRIVATE_RESULT' not in raw and 'duplicate_extra_rows' not in raw
    assert "expected_verdict" not in raw and "rationale" not in raw and '"value"' not in raw
    leak_scan(exported, material)
    exported["prompt"] = "secret_fault_name"
    with pytest.raises(DataError): leak_scan(exported, material)


def test_resume_cache_integrity(tmp_path):
    counter = []
    def compute(): counter.append(1); return {"answer": 1}
    assert checked_stage(tmp_path, "one", {"x": 1}, compute) == {"answer": 1}
    checked_stage(tmp_path, "one", {"x": 1}, compute)
    assert len(counter) == 1
    with pytest.raises(DataError): checked_stage(tmp_path, "one", {"x": 2}, compute)
    path = tmp_path / "private/stages/one.json"
    cached = json.loads(path.read_text()); cached["result"]["answer"] = 4; write_json(path, cached)
    with pytest.raises(DataError): checked_stage(tmp_path, "one", {"x": 1}, compute)


def make_recipe(tmp_path, case="M1"):
    tele = tmp_path / "tele.csv"
    ctx = tmp_path / "ctx.csv"
    tele.write_text("Time,P_SA,I_Load1\n2026-01-01 00:00:00,0,0\n2026-01-01 00:00:02,6,2\n", encoding="utf-8")
    ctx.write_text("Time,Irradiation\n2026-01-01 00:00:00,300\n2026-01-01 00:00:02,300\n", encoding="utf-8")
    recipe = {"material_id": case, "data_origin": "synthetic", "split": "development", "title": "fixture", "low_irradiation_value": 300,
        "records": [{"record_id": "R1", "series_id": "G1", "sequence_index": 1, "lineage_group": "G1",
            "source_rows": [0, 2], "telemetry_path": "tele.csv", "context_path": "ctx.csv",
            "source_hashes": {"telemetry": file_hash(tele), "context": file_hash(ctx)}}],
        "channels": {c: {"unit": None} for c in ["P_SA", "I_Load1", "Irradiation"]},
        "facts": [{"fact_id": "F1", "query": query(), "definition": "median", "unit": "W"}],
        "interpretations": [], "task_slots": [], "public_background": ["fixture"], "limitations": ["fixture"],
        "forbidden_public_strings": [], "selection_rationale": "fixture", "evidence_sources": ["fixture"]}
    path = tmp_path / (case + ".json"); write_json(path, recipe)
    return path


def test_raw_hash_and_row_alignment(tmp_path):
    path = make_recipe(tmp_path)
    material, records = build_material(path, tmp_path / "out")
    assert material["facts"][0]["result"]["value"] == 3
    assert records["R1"]["time_s"] == [0, 2]
    ctx = tmp_path / "ctx.csv"
    ctx.write_text(ctx.read_text().replace("00:00:02", "00:00:01"))
    with pytest.raises(DataError): build_material(path, tmp_path / "changed")
    recipe = json.loads(path.read_text()); recipe["records"][0]["source_hashes"]["context"] = file_hash(ctx); write_json(path, recipe)
    with pytest.raises(DataError): build_material(path, tmp_path / "misaligned")


def config():
    settings = {"base_url": "https://example.invalid", "api_key_env": "UNUSED", "model": "fixture", "max_tokens": 512, "temperature": 0}
    return {"schema_version": "0.2", "max_api_calls": 1, "max_solver_steps": 2, "max_revisions": 0,
        "transport_retries": 0, "timeout_seconds": 30, "max_input_bytes": 100000, "max_response_bytes": 100000,
        "models": {r: settings.copy() for r in ["material_generator", "material_critic", "material_solver", "material_judge"]}}


def test_material_batch_two_cases_and_cross_split_block(tmp_path):
    a, b = make_recipe(tmp_path, "M1"), make_recipe(tmp_path, "M2")
    batch = tmp_path / "batch.json"
    write_json(batch, {"schema_version": "0.2", "cases": [{"case_id": "A", "recipe_path": a.name}, {"case_id": "B", "recipe_path": b.name}]})
    class NoModel:
        mode = "mock"
        def call(self, *args): raise AssertionError("Material stage must not call an API")
    root = Path(__file__).resolve().parents[1]
    result = run_batch(batch, config(), NoModel(), tmp_path / "batch-out", root, "materials")
    assert len(result["cases"]) == 2 and not result["errors"]
    assert (tmp_path / "batch-out/A/private/material.json").exists()
    assert (tmp_path / "batch-out/B/private/material.json").exists()
    recipe = json.loads(b.read_text()); recipe["split"] = "test"; write_json(b, recipe)
    with pytest.raises(DataError): run_batch(batch, config(), NoModel(), tmp_path / "other", root, "materials")


def test_full_pipeline_fixture_and_resume_without_calls(tmp_path):
    path = make_recipe(tmp_path)
    recipe = json.loads(path.read_text())
    recipe["interpretations"] = [{"interpretation_id": "C1", "statement": "Median exceeds 1.",
        "fact_ids": ["F1"], "expected_verdict": "supported", "basis_type": "analytic_fixture", "rationale": "3 > 1"}]
    recipe["task_slots"] = [{"slot_id": f"S{i}", "focus": "OFFLINE structural fixture",
        "measurement_ids": ["F1"], "interpretation_ids": ["C1"]} for i in range(3)]
    write_json(path, recipe)
    batch = tmp_path / "batch.json"
    write_json(batch, {"schema_version": "0.2", "cases": [{"case_id": "A", "recipe_path": path.name}]})

    class Fixture:
        mode = "mock"
        def __init__(self): self.calls = 0
        def call(self, role, payload, kind):
            self.calls += 1
            if role == "material_generator":
                return {"material_id": "M1", "tasks": [{"task_id": f"T{i}", "slot_id": f"S{i}",
                    "title": "OFFLINE fixture", "prompt": "Measure and assess this fixture.",
                    "measurement_ids": ["F1"], "interpretation_ids": ["C1"], "required_record_ids": ["R1"],
                    "why_data_are_needed": "fixture", "distinctness": "fixture only"} for i in range(3)]}
            if role == "material_critic":
                return {"reviews": [{"task_id": f"T{i}", "decision": "accept", "leakage": False, "issues": [], "rationale": "fixture"} for i in range(3)]}
            if role == "material_solver":
                if not payload["observations"]:
                    return {"action": "query", "queries": [query()]}
                obs = payload["observations"][0]
                return {"action": "submit", "answer": {"measurements": [{"measurement_id": "F1", "value": 3, "observation_id": obs["observation_id"]}],
                    "interpretations": [{"interpretation_id": "C1", "verdict": "supported", "explanation": "3 exceeds 1.", "observation_ids": [obs["observation_id"]]}],
                    "limitations": ["fixture only"]}}
            return {"task_id": payload["task"]["task_id"], "decision": "pass", "criteria": [{"interpretation_id": "C1", "pass": True, "reason": "fixture"}], "issues": []}
    model = Fixture()
    root = Path(__file__).resolve().parents[1]
    result = run_batch(batch, config(), model, tmp_path / "out", root)
    assert not result["errors"]
    assert result["cases"][0]["status"] == "fixture_only"
    assert result["cases"][0]["trajectories"] == 3
    assert result["cases"][0]["pilot_passed"] == 0  # mocks can never become real passed cases
    assert model.calls == 11
    run_batch(batch, config(), model, tmp_path / "out", root)
    assert model.calls == 11


def test_api_free_audit_labels_reference_replay_correctly(tmp_path):
    from hangtian.material_pipeline import audit_drafts
    path = make_recipe(tmp_path)
    recipe = json.loads(path.read_text())
    recipe["interpretations"] = [{"interpretation_id": "C1", "statement": "Median exceeds 1.",
        "fact_ids": ["F1"], "expected_verdict": "supported", "basis_type": "analytic_fixture", "rationale": "3 > 1"}]
    recipe["task_slots"] = [{"slot_id": f"S{i}", "focus": "OFFLINE fixture", "measurement_ids": ["F1"], "interpretation_ids": ["C1"]} for i in range(3)]
    write_json(path, recipe)
    proposal = {"material_id": "M1", "tasks": [{"task_id": f"T{i}", "slot_id": f"S{i}", "title": "Fixture", "prompt": "Assess this measurement.",
        "measurement_ids": ["F1"], "interpretation_ids": ["C1"], "required_record_ids": ["R1"],
        "why_data_are_needed": "fixture", "distinctness": "fixture"} for i in range(3)]}
    write_json(tmp_path / "draft.json", proposal)
    write_json(tmp_path / "index.json", {"schema_version": "0.2", "cases": [{"case_id": "A", "proposal_path": "draft.json", "authorship": "analytic test fixture"}]})
    write_json(tmp_path / "batch.json", {"schema_version": "0.2", "cases": [{"case_id": "A", "recipe_path": path.name}]})
    result = audit_drafts(tmp_path / "batch.json", tmp_path / "index.json", config(), tmp_path / "out", Path(__file__).resolve().parents[1])
    assert not result["errors"]
    case = result["cases"][0]
    assert case["reference_replays"] == 3 and case["trajectories"] == 0 and case["pilot_passed"] == 0
    assert case["api_calls_in_this_run"] == 0
    validation = json.loads((tmp_path / "out/A/validation_results.json").read_text())
    assert all(n["rejected"] for r in validation["results"] for n in r["validator_negative_controls"])


def test_zero_run_is_acquisition_rows_with_earliest_tie(records):
    r = records['R1']
    r['channels']['P_SA'] = [0, 0, 9, 0, 0, 9]
    r['channels']['I_Load1'] = [0, 0, 9, 0, 0, 9]
    q = {'record_id': 'R1', 'op': 'longest_zero_run', 'region': 'low_irr', 'slice': 'all', 'channels': ['P_SA', 'I_Load1']}
    result = execute(records, q)
    assert result['value'] == 2 and result['run_source_rows'] == [10, 12]
    assert result['run_start_offset_s'] == 0
    q['channels'].append('Irradiation')
    assert execute(records, q)['value'] == 0
    q['channels'].append('PRIVATE')
    with pytest.raises(DataError): execute(records, q)


def test_quality_conflict_channel_and_below_direction(records):
    r = records['R1']
    assert execute(records, onset(threshold=8, direction='below'))['value'] == 0
    assert execute(records, onset(threshold=6, direction='below'))['value'] is None
    r['time_s'][2] = 1
    q = {'record_id':'R1', 'op':'quality', 'region':'low_irr', 'slice':'all', 'metric':'conflict_channel_count'}
    result = execute(records, q)
    assert result['value'] == 1 and result['quality']['conflict_channels'] == ['P_SA']
    with pytest.raises(DataError): execute(records, {**q, 'region': 'undeclared'})
    with pytest.raises(DataError): execute(records, onset(direction='below'))


def test_explicit_regions_cannot_escape_source_window(tmp_path):
    path = make_recipe(tmp_path)
    recipe = json.loads(path.read_text()); recipe['records'][0]['regions'] = {'low_irr':[0,2]}
    write_json(path, recipe)
    _, records = build_material(path, tmp_path/'good')
    assert records['R1']['regions']['full_record'] == [0,2]
    recipe['records'][0]['regions']['low_irr'] = [0,3]; write_json(path, recipe)
    with pytest.raises(DataError): build_material(path, tmp_path/'bad')


def test_assistant_review_generation_calls_only_generator(records, tmp_path):
    from hangtian.material_pipeline import generate
    from hangtian.material_review import review_gate
    task, material, _ = reference(records)
    material['require_model_written_interpretations'] = True
    material['task_slots'] = [{'slot_id': f'S{i}', 'target_task_id': f'T{i}', 'measurement_ids':['F1'], 'interpretation_ids':['C1']} for i in range(3)]
    proposal = {'material_id':'M1', 'tasks':[{**task, 'slot_id':f'S{i}', 'task_id':f'T{i}',
        'why_data_are_needed':'Analytic test fixture', 'distinctness':'Test fixture',
        'interpretation_statements':[{'interpretation_id':'C1', 'statement':'The median exceeds one.'}]} for i in range(3)]}
    class GeneratorOnly:
        mode = 'mock'
        def __init__(self): self.calls = []
        def call(self, role, payload, kind):
            self.calls.append(role)
            assert role == 'material_generator'
            view = payload['material']
            assert 'expected_verdict' not in json.dumps(view) and 'rationale' not in json.dumps(view)
            assert 'result' not in view['task_slots'][0]['measurements'][0]
            assert view['task_slots'][0]['measurements'][0]['query'] == query()
            return proposal
    model = GeneratorOnly(); cfg = config(); cfg['review_mode'] = 'assistant'
    generated = generate(material, model, cfg, tmp_path)
    assert model.calls == ['material_generator'] and generated['review'] is None
    assert generated['public_tasks'][0]['interpretations'][0]['statement'] == 'The median exceeds one.'
    bad = copy.deepcopy(proposal); bad['tasks'][0]['interpretation_statements'] = []
    with pytest.raises(DataError): verify_proposal(bad, material)
    bad = copy.deepcopy(proposal); bad['tasks'][0]['task_id'] = 'T8'
    with pytest.raises(DataError): verify_proposal(bad, material)
    review = {'reviewer':'current_assistant', 'proposal_sha256':digest(proposal),
        'material_sha256':digest(material), 'public_tasks_sha256':digest(generated['public_tasks']),
        'reviews':[{'task_id':f'T{i}', 'decision':'accept', 'leakage':False, 'issues':[], 'rationale':'Analytic test only.'} for i in range(3)]}
    review_gate(review, proposal, material, generated['public_tasks'])
    bad = copy.deepcopy(proposal); bad['tasks'][0]['prompt'] = 'Changed question'
    with pytest.raises(DataError): review_gate(review, bad, material, generated['public_tasks'])
    review['reviews'][0]['decision'] = 'revise'
    with pytest.raises(DataError): review_gate(review, proposal, material, generated['public_tasks'])


def test_flash_thinking_request_and_secret_free_logs(tmp_path, monkeypatch):
    from hangtian.models import DeepSeekModel
    import hangtian.models as models
    cfg=config();cfg['models']['material_generator'].update(model='deepseek-flash',thinking='enabled',reasoning_effort='high')
    monkeypatch.setenv('UNUSED','TEST_PRIVATE_KEY_DO_NOT_LOG')
    captured=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,size):
            return json.dumps({'model':'deepseek-flash','choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}','reasoning_content':'DO_NOT_SAVE_REASONING'}}]}).encode()
    class Opener:
        def open(self,request,timeout):captured.append(json.loads(request.data));return Response()
    monkeypatch.setattr(models.urllib.request,'build_opener',lambda *args:Opener())
    model=DeepSeekModel(cfg,Path(__file__).resolve().parents[1],tmp_path,True,True)
    assert model.call('material_generator',{},'material_tasks') == {'ok':True}
    assert captured[0]['model']=='deepseek-flash' and captured[0]['thinking']=={'type':'enabled'}
    assert captured[0]['reasoning_effort']=='high' and 'temperature' not in captured[0]
    log=(tmp_path/'private/calls/00001.json').read_text()
    assert 'TEST_PRIVATE_KEY_DO_NOT_LOG' not in log and 'DO_NOT_SAVE_REASONING' not in log


def test_generation_view_keeps_sparse_scope_and_arbitrary_source_groups(records):
    from hangtian.materials import generation_view
    _, material, _ = reference(records)
    material['record_catalog']=[{'record_id':'Sample_X','series_id':'Origin_P','quality':{'rows':999}},
                                {'record_id':'Sample_Y','series_id':'Origin_Q','quality':{'rows':998}}]
    material['facts']=[{'fact_id':'Metric_P','query':{'record_id':'Sample_X','op':'stat','region':'window_left','slice':'all','channel':'Sensor_Alpha','stat':'mean'},'unit':'unit_A','result':{'value':777}},
                       {'fact_id':'Metric_Q','query':{'record_id':'Sample_Y','op':'stat','region':'window_right','slice':'all','channel':'Sensor_Beta','stat':'max'},'unit':'unit_B','result':{'value':888}}]
    material['task_slots']=[{'slot_id':'Goal_Z','focus':'PRIVATE OBSERVED OUTCOME','measurement_ids':['Metric_P','Metric_Q'],'interpretation_ids':['C1']}]
    view=generation_view(material)
    assert view['source_groups']=={'Origin_P':['Sample_X'],'Origin_Q':['Sample_Y']}
    measurements=view['task_slots'][0]['measurements']
    assert len(measurements)==2
    assert [(m['query']['record_id'],m['query']['region'],m['query']['channel']) for m in measurements]==[
        ('Sample_X','window_left','Sensor_Alpha'),('Sample_Y','window_right','Sensor_Beta')]
    text=json.dumps(view)
    assert 'PRIVATE OBSERVED OUTCOME' not in text and '777' not in text and '888' not in text and 'quality' not in text


def test_api_version_assembly_rejects_unlogged_text_edits(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    from assemble_api_versions import assemble
    path=make_recipe(tmp_path);recipe=json.loads(path.read_text())
    recipe['interpretations']=[{'interpretation_id':'C1','statement':'Median exceeds one.','fact_ids':['F1'],
        'expected_verdict':'supported','basis_type':'analytic_fixture','rationale':'Fixture only.'}]
    recipe['task_slots']=[{'slot_id':f'S{i}','measurement_ids':['F1'],'interpretation_ids':['C1']} for i in range(3)]
    write_json(path,recipe)
    proposal={'material_id':'M1','tasks':[{'task_id':f'T{i}','slot_id':f'S{i}','title':'Analytic fixture',
        'prompt':'Assess the attached fixture.','measurement_ids':['F1'],'interpretation_ids':['C1'],
        'required_record_ids':['R1'],'why_data_are_needed':'fixture','distinctness':'fixture'} for i in range(3)]}
    source=tmp_path/'prior/A'
    write_json(source/'private/generated_candidate.json',{'authorship':'remote_api','proposal':proposal})
    write_json(source.parent/'private/calls/00001.json',{'metadata':{'status':'completed','requested_model':'offline_test_fixture',
        'prompt_sha256':'test','input_sha256':'test'},'output':proposal})
    manifest=tmp_path/'selection.json'
    write_json(manifest,{'cases':[{'case_id':'A','recipe_path':str(path),'selections':[{'task_id':f'T{i}','source_case_dir':str(source)} for i in range(3)]}]})
    assemble(manifest,tmp_path/'good')
    generated=json.loads((tmp_path/'good/A/private/generated_candidate.json').read_text())
    assert generated['proposal']==proposal and len(generated['task_origins'])==3
    assert not (tmp_path/'good/A/public/tasks.json').exists()
    proposal['tasks'][0]['prompt']='Unlogged substituted question'
    write_json(source/'private/generated_candidate.json',{'authorship':'remote_api','proposal':proposal})
    with pytest.raises(DataError):assemble(manifest,tmp_path/'bad')
