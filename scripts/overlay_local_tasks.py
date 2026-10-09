"""Select exact logged local-model objects; never edit public question text."""
import argparse
import json
from pathlib import Path
from hangtian.data import DataError,digest,write_json
from hangtian.materials import read_json


def overlay(manifest,base,replacement,out,required_tasks=None):
    if out.exists():raise DataError('Use a fresh assembly directory')
    staged=[];replaced=set()
    for case in read_json(manifest)['cases']:
        cid=case['case_id'];saved=read_json(base/cid/'private/candidate.json')
        tasks={t['task_id']:t for t in saved['proposal']['tasks']}
        logs=list(saved['source_call_logs']);sources={tid:str(base/cid) for tid in tasks}
        alternate=replacement/cid/'private/candidate.json'
        if alternate.exists():
            other=read_json(alternate)
            for key in ['material_sha256','records_file_sha256']:
                if other['identity'][key]!=saved['identity'][key]:raise DataError('Material changed between versions')
            for t in other['proposal']['tasks']:
                if t['task_id'] not in tasks:raise DataError('Replacement added unknown task')
                tasks[t['task_id']]=t;sources[t['task_id']]=str(replacement/cid)
                replaced.add(t['task_id'])
            logs.extend(other['source_call_logs'])
        calls=[read_json(Path(p)) for p in dict.fromkeys(logs)]
        for t in tasks.values():
            if not any(l['status']=='returned' and t in json.loads(l['response']['choices'][0]['message']['content'])['tasks'] for l in calls):
                raise DataError('Unlogged model object')
        saved['proposal']['tasks']=list(tasks.values())
        saved['source_call_logs']=list(dict.fromkeys(logs))
        saved['identity']['input_sha256']=digest(sources)
        saved.update(assembly='Exact API object selection; fresh review required',selected_sources=sources)
        staged.append((cid,saved))
    if required_tasks is not None and replaced!=set(required_tasks):
        raise DataError('Replacement set does not match required tasks')
    for cid,saved in staged:write_json(out/cid/'private/candidate.json',saved)
    write_json(out/'selection_sources.private.json',{'base':str(base),'replacement':str(replacement),
        'replaced_tasks':sorted(replaced),'required_tasks':required_tasks,'public_text_edits':0})


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ['manifest','base','replacement','out']:p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--required-tasks',nargs='+')
    a=p.parse_args();overlay(a.manifest,a.base,a.replacement,a.out,a.required_tasks)
