"""Load all 100 published tasks through the real Pi gate; no model calls."""
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from hangtian.data import file_hash, write_json
from hangtian.materials import read_json
from hangtian.pi_bridge import approved_task, Bridge


class CardCount(HTMLParser):
    def __init__(self):super().__init__();self.count=0
    def handle_starttag(self,tag,attrs):
        if tag=='article':self.count+=1


def verify(batch):
    tasks=read_json(batch/'tasks.json')['tasks']
    if [t['task_id'] for t in tasks]!=[f'T{i:02d}' for i in range(1,101)]:
        raise ValueError('Expected ordered 100 tasks')
    origins=read_json(batch/'generation_provenance.json')
    if Counter(o['task_id'] for o in origins)!=Counter(t['task_id'] for t in tasks):
        raise ValueError('Incomplete or repeated provenance')
    checks=[]
    for task in tasks:
        tid=task['task_id'];approved,records,records_hash=approved_task(batch,tid)
        if approved!=task:raise ValueError('Public mismatch')
        if set(task)!={'task_id','title','prompt','schema_version','environment','response_requirements'}:
            raise ValueError('Unexpected public top-level field')
        # Init is the same public payload supplied to Pi. Its temporary state is
        # discarded; no model, data query, or answer submission is performed.
        with TemporaryDirectory(prefix='hangtian_gate_') as temporary:
            bridge=Bridge(task,records,Path(temporary))
            init=bridge.handle({'op':'init'})
        if init.get('task')!=task:
            raise ValueError('Pi initialization differs from public task')
        rendered=json.dumps(init,ensure_ascii=False)
        if any(secret in rendered for secret in ['private_rubric','reference_fact_ids','source_call_logs','/home/xjshang']):
            raise ValueError('Private information in Pi initialization')
        checks.append({'task_id':tid,'pi_review_gate':'passed','record_hash':records_hash,
            'record_count':len(records),'model_called':False})
    for name,expected in [('questions.html',100),('review_report.html',85)]:
        parser=CardCount();parser.feed((batch/name).read_text(encoding='utf-8'))
        if parser.count!=expected:raise ValueError('Wrong HTML card count')
    result={'passed':True,'task_count':100,'model_calls':0,'new_solver_trajectories':0,
        'checks':checks,'file_sha256':{n:file_hash(batch/n) for n in ['tasks.json','questions.html','review_report.html','generation_provenance.json']}}
    write_json(batch/'publication_verification.json',result)
    print({k:v for k,v in result.items() if k not in ['checks','file_sha256']})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True)
    verify(p.parse_args().batch)
