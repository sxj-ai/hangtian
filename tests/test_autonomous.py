"""Independent analysis paths, environment isolation and evidence integrity."""
import copy
import pytest

from hangtian.autonomous import (run_query, InvestigationTools, verify_evidence,
                                export_tasks, public_environment, review_gate)
from hangtian.data import DataError, digest


@pytest.fixture
def records():
    return {'SampleX': {'record_id': 'SampleX', 'row_origin': 10,
        'time_s': [0., 1., 3., 4., 5., 7.], 'channels': {'SensorAlpha': [0., 5., 6., 7., 8., 0.]},
        'regions': {'answer_location': [12, 15]}}}


def query(**overrides):
    return dict({'record_id': 'SampleX', 'op': 'stat', 'start_row': 10, 'stop_row': 16,
                 'channel': 'SensorAlpha', 'stat': 'mean'}, **overrides)


def test_free_window_not_limited_to_reference_region(records):
    assert run_query(records, query(start_row=11, stop_row=13))['value'] == 5.5
    assert run_query(records, query(stat='max'))['value'] == 8


@pytest.mark.parametrize('changes', [dict(record_id='Hidden'), dict(start_row=9), dict(stop_row=17),
                                    dict(channel='HiddenSensor'), dict(stop_row=10)])
def test_invalid_access_rejected(records, changes):
    with pytest.raises(DataError):
        run_query(records, query(**changes))


def test_read_pagination_is_explicit_and_preserves_duplicates(records):
    r = records['SampleX']; r['time_s'] = [2.] * 600; r['channels']['SensorAlpha'] = list(range(600))
    q = {'record_id':'SampleX','op':'read','start_row':10,'stop_row':610,'channels':['SensorAlpha']}
    first = run_query(records, q)
    assert len(first['time_s']) == 512 and first['next_start_row'] == 522
    last = run_query(records, q | {'start_row':first['next_start_row']})
    assert last['next_start_row'] is None and last['channels']['SensorAlpha'] == list(range(512,600))


def test_profile_has_complete_nonoverlapping_coverage(records):
    result = run_query(records, {'record_id':'SampleX','op':'profile','start_row':10,'stop_row':16,
                                'channels':['SensorAlpha'],'bins':4})
    assert [b['source_rows'] for b in result['bins']] == [[10,11],[11,13],[13,14],[14,16]]
    assert sum(b['count'] for b in result['bins']) == 6


def test_bidirectional_event_actual_seconds_and_extra_fields(records):
    q = {'record_id':'SampleX','op':'first_sustained','start_row':10,'stop_row':16,
         'channel':'SensorAlpha','threshold':5,'min_records':3,'direction':'above'}
    assert run_query(records,q)['value'] == 3
    assert run_query(records,q | {'direction':'below','min_records':1})['value'] == 0
    with pytest.raises(DataError): run_query(records,q | {'stat':'median'})


def test_different_valid_methods_pass_integrity_but_never_auto_grade(records):
    for stat in ('mean','median','max'):
        tool = InvestigationTools(records); obs = tool.call(query(stat=stat))
        trajectory = {'observations':tool.observations, 'answer':{'findings':[
            {'claim':'Test claim, not semantically graded.','observation_ids':[obs['observation_id']]}],
            'conclusion':'Test fixture','limitations':[]}}
        report = verify_evidence(trajectory, records)
        assert report['evidence_integrity_pass'] and report['task_pass'] is None
        assert report['semantic_status'] == 'pending_outcome_review'
        bad = copy.deepcopy(trajectory); bad['observations'][0]['result']['value'] += 1
        assert not verify_evidence(bad, records)['evidence_integrity_pass']
        bad = copy.deepcopy(trajectory);bad['answer']['findings'][0]['observation_ids'] = ['O_forged']
        assert not verify_evidence(bad, records)['evidence_integrity_pass']


def test_public_whitelist_removes_entire_reference_plan(records):
    material = {'material_id':'MaterialX','channels':{'SensorAlpha':{'unit':'arbitrary'}},
                'forbidden_public_strings':[], 'record_catalog':[{'record_id':'SampleX','series_id':'OriginX',
                    'sequence_index':1,'regions':{'answer_location':[12,15]},'quality':{'answer':99}}],
                'facts':[{'fact_id':'FactX'}]}
    env = public_environment(material,records,['Neutral data documentation.'])
    task = {'task_id':'TaskX','slot_id':'SlotX','title':'Investigation', 'prompt':'Assess the supplied phenomenon.',
            'private_rubric':[{'criterion':'SECRET','reference_fact_ids':['FactX'],'acceptable_alternatives':'Other valid methods.'}]*2,
            'private_decisions_left_to_agent':['Choose evidence','Choose comparison'], 'private_distinctness':'PRIVATE'}
    proposal = {'material_id':'MaterialX','tasks':[task]}
    public = export_tasks(proposal,material,env,{'SlotX':'TaskX'})
    text = str(public)
    for token in ('SECRET','FactX','answer_location','private_rubric','measurements','interpretations','SlotX'):
        assert token not in text
    assert all('quality' not in r for r in public[0]['environment']['records'])
    rubric = {'tasks':[{'task_id':'TaskX','criterion':'PRIVATE_OUTCOME'}]}
    review = {'outcome_rubric_sha256':digest(rubric),'reviewer':'current_assistant','purpose':'autonomous_investigation',
              'proposal_sha256':digest(proposal),'public_sha256':digest(public),'material_sha256':digest(material),
              'reviews':[{'task_id':'TaskX','decision':'accept','blocking_issues':[],'rationale':'Fixture only',
                          'no_solution_plan':True,'data_dependent':True,'fair_outcome_rubric':True}]}
    review_gate(review,proposal,public,material,rubric)
    from hangtian.autonomous import solve
    class SolverFixture:
        def __init__(self): self.calls = 0
        def call(self, role, payload, kind):
            assert role == 'autonomous_solver'
            assert 'SECRET' not in str(payload) and 'FactX' not in str(payload)
            self.calls += 1
            if self.calls == 1:
                return {'action':'query','queries':[query(stat='max')]}
            return {'action':'submit','answer':{'findings':[{'claim':'Fixture claim',
                'observation_ids':[payload['observations'][0]['observation_id']]}],
                'conclusion':'Fixture conclusion','limitations':[]}}
    import tempfile
    from pathlib import Path
    model = SolverFixture()
    with tempfile.TemporaryDirectory() as directory:
        trajectory = solve(public,'TaskX',records,model,Path(directory),review=review,
                           proposal=proposal,material=material,outcome_rubric=rubric)
        assert trajectory['status'] == 'submitted' and model.calls == 2
        assert verify_evidence(trajectory,records)['evidence_integrity_pass']
    public[0]['prompt'] = 'Tampered'
    with pytest.raises(DataError): review_gate(review,proposal,public,material,rubric)
    with pytest.raises(DataError):
        solve(public,'TaskX',records,model,Path('.'),review=review,proposal=proposal,material=material,outcome_rubric=rubric)
    assert model.calls == 2
