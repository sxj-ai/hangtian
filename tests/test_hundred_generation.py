import importlib.util
from pathlib import Path
import pytest


def module(name='generate_hundred_qwen'):
    path=Path(__file__).resolve().parents[1]/'scripts'/(name+'.py')
    spec=importlib.util.spec_from_file_location('hundred_generator',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_local_authoring_rejects_external_destinations():
    m=module();m.validate_loopback('http://127.0.0.1:34567/v1')
    for url in ['https://api.deepseek.com/v1','http://localhost:80','http://127.0.0.1.evil/v1',
                'http://user:secret@127.0.0.1:8080/v1','https://127.0.0.1:8080/v1']:
        with pytest.raises(ValueError):m.validate_loopback(url)


def test_authoring_payload_keeps_schema_and_only_requested_targets():
    m=module()
    material={'material_id':'M1','limitations':['Evidence limited'],
              'task_slots':[{'slot_id':'G1','focus':'private purpose','measurement_ids':['F1']}],
              'facts':[{'fact_id':'F1','query':{'record_id':'A1'},'unit':'V',
                        'result':{'value':0.0,'source_rows':[0,10]}}]}
    p=m.payload_for(material,{'context':['public']},{'G1':'T16'})
    assert p['private_slots'][0]['target_task_id']=='T16'
    assert p['private_verified_anchors'][0]['value']==0
    assert 'private_verified_anchors' not in p['public_environment']
    assert p['required_output_schema']['required']==['material_id','tasks']
    material['task_slots'].append({'slot_id':'G2','focus':'other','measurement_ids':['F2']})
    material['facts'].append({'fact_id':'F2','query':{},'unit':'V','result':{'value':2,'source_rows':[10,20]}})
    selected=m.payload_for(material,{}, {'G1':'T16'})
    assert len(selected['private_slots'])==1
    assert [f['id'] for f in selected['private_verified_anchors']]==['F1']


def test_style_screen_catches_solution_checklists_but_does_not_approve_semantics():
    m=module()
    assert m.public_style_errors([{'task_id':'T1','title':'参考适用性','prompt':'评估R是否适合作为A4的定量参考。'}])==[]
    for bad in ['比较I_BAT2、I_BAT3并说明其贡献。','评估A4。再分析A3。',
                '评估电池充电电阻的表现。','比较对应负载阶段的测量。']:
        assert m.public_style_errors([{'task_id':'T1','title':'调查','prompt':bad}])


def test_offline_transformers_adapter_enforces_model_mode_and_budget():
    m=module('local_transformers_api')
    body={'model':'Qwen3.5-27B','chat_template_kwargs':{'enable_thinking':False},
          'messages':[{'role':'user','content':'test'}],'max_tokens':200}
    m.validate_request(body,'Qwen3.5-27B')
    for bad in [{'model':'other'},{'chat_template_kwargs':{}},{'max_tokens':10001},
                {'stream':True},{'tools':[{}]},{'messages':[{'role':'system','content':{}}]}]:
        with pytest.raises(ValueError):m.validate_request(body|bad,'Qwen3.5-27B')


def test_review_binding_rejects_missing_hashes_changed_attachments_and_wrong_origin():
    from hangtian.data import DataError,digest
    m=module('bind_hundred_reviews');task={'task_id':'T16','prompt':'same','environment':{'records':['A1']}}
    material={'facts':['verified']}
    review={'public_project_digest':digest(task),'material_project_digest':digest(material),
            'reviewed_generation_job':'100'}
    m.verify_review_identity(review,task,material,'generation_jobs/100/pack_01')
    for changed in [{},review|{'material_project_digest':'wrong'},review|{'reviewed_generation_job':'99'}]:
        with pytest.raises(DataError):m.verify_review_identity(changed,task,material,'generation_jobs/100/pack_01')
    with pytest.raises(DataError):m.verify_review_identity(review,task|{'environment':{'records':['A2']}},material,'generation_jobs/100/pack_01')


def test_overlay_refuses_unlogged_question_edits_and_changed_material(tmp_path):
    import json
    from hangtian.data import write_json,DataError
    m=module('overlay_local_tasks')
    manifest=tmp_path/'manifest.json';write_json(manifest,{'cases':[{'case_id':'p1'}]})
    def candidate(folder,title,material='M'):
        task={'task_id':'T1','title':title}
        call=tmp_path/(folder+'.json')
        write_json(call,{'status':'returned','response':{'choices':[{'message':{
            'content':json.dumps({'tasks':[task]})}}]}})
        saved={'identity':{'material_sha256':material,'records_file_sha256':'R'},
               'proposal':{'tasks':[task]},'source_call_logs':[str(call)]}
        write_json(tmp_path/folder/'p1/private/candidate.json',saved)
        return saved
    candidate('base','old');alternate=candidate('replacement','new')
    m.overlay(manifest,tmp_path/'base',tmp_path/'replacement',tmp_path/'valid')
    assembled=json.loads((tmp_path/'valid/p1/private/candidate.json').read_text())
    assert assembled['proposal']['tasks'][0]['title']=='new'
    alternate['proposal']['tasks'][0]['title']='edited by human'
    write_json(tmp_path/'replacement/p1/private/candidate.json',alternate)
    with pytest.raises(DataError,match='Unlogged'):m.overlay(manifest,tmp_path/'base',tmp_path/'replacement',tmp_path/'tampered')
    candidate('replacement','new',material='different')
    with pytest.raises(DataError,match='Material changed'):m.overlay(manifest,tmp_path/'base',tmp_path/'replacement',tmp_path/'mismatch')
    with pytest.raises(DataError,match='Replacement set'):m.overlay(manifest,tmp_path/'base',tmp_path/'absent',tmp_path/'missing',required_tasks=['T1'])
    assert not (tmp_path/'missing').exists()
    candidate('replacement','new')
    with pytest.raises(DataError,match='Replacement set'):m.overlay(manifest,tmp_path/'base',tmp_path/'replacement',tmp_path/'wrong',required_tasks=['T2'])
