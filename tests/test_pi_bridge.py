import pytest
from hangtian.pi_bridge import Bridge


@pytest.fixture
def bridge(tmp_path):
    return Bridge({'task_id':'SyntheticTask'}, {'Visible': {
        'record_id':'Visible','row_origin':0,'time_s':[0.,1.,2.],
        'channels':{'Current':[0.,2.,3.]},'regions':{}}}, tmp_path)


def test_bridge_rejects_paths_code_and_hidden_records(bridge):
    for query in [
        {'record_id':'Hidden','op':'stat','start_row':0,'stop_row':3,'channel':'Current','stat':'mean'},
        {'record_id':'Visible','op':'read','start_row':0,'stop_row':3,'channels':['Current'],'path':'private/material.json'},
        {'record_id':'Visible','op':'execute','start_row':0,'stop_row':3,'code':'print(1)'},
    ]:
        assert 'error' in bridge.handle({'op':'query','query':query})
    assert bridge.state['observations']==[]


def test_submission_receipt_is_not_grade_and_forged_citations_rejected(bridge):
    q={'record_id':'Visible','op':'stat','start_row':0,'stop_row':3,'channel':'Current','stat':'max'}
    obs=bridge.handle({'op':'query','query':q})
    answer={'findings':[{'claim':'Maximum is 3.','observation_ids':['O_fake']}],
            'conclusion':'A synthetic observation.','limitations':[]}
    assert 'error' in bridge.handle({'op':'submit','answer':answer})
    answer['findings'][0]['observation_ids']=[obs['observation_id']]
    result=bridge.handle({'op':'submit','answer':answer})
    assert result=={'receipt':'submitted','correctness':'not_evaluated'}
    assert 'error' in bridge.handle({'op':'query','query':q})


def test_no_data_condition_cannot_read_even_if_requested(bridge):
    bridge.mode='no_data'
    assert 'error' in bridge.handle({'op':'query','query':{
        'record_id':'Visible','op':'stat','start_row':0,'stop_row':3,'channel':'Current','stat':'max'}})
    assert bridge.state['observations']==[]


def test_reporting_probe_can_only_submit_previously_verified_evidence(bridge, tmp_path):
    import copy
    from hangtian.data import DataError
    q={'record_id':'Visible','op':'stat','start_row':0,'stop_row':3,'channel':'Current','stat':'max'}
    obs=bridge.handle({'op':'query','query':q})
    prior=copy.deepcopy(bridge.state)
    probe=Bridge(bridge.task, bridge.tool.records, tmp_path/'probe', mode='report_only')
    forged=copy.deepcopy(prior); forged['observations'][0]['result']['value']=99
    with pytest.raises(DataError): probe.seed_reporting_probe(forged)
    assert probe.state['observations']==[]
    probe.seed_reporting_probe(prior)
    assert probe.handle({'op':'init'})['prior_observations']==[obs]
    assert 'error' in probe.handle({'op':'query','query':q})
    assert len(probe.state['observations'])==1
    answer={'findings':[{'claim':'Maximum is 3.','observation_ids':[obs['observation_id']]}],
            'conclusion':'A synthetic observation.','limitations':[]}
    assert probe.handle({'op':'submit','answer':answer})['receipt']=='submitted'
    assert prior['answer'] is None
    assert 'not autonomous completion' in probe.state['diagnostic_condition']
