"""Overlay selected regenerated API objects without editing their text."""
import argparse
from pathlib import Path
from hangtian.data import DataError, write_json
from hangtian.materials import read_json
from hangtian.autonomous import public_environment, export_tasks


def assemble(base, replacements, out):
    if out.exists():raise DataError('Assembly needs a fresh output directory')
    manifest=read_json(base/'private/manifest.json')
    for case in manifest['cases']:
        original=read_json(base/case['case_id']/'private/candidate.json')
        candidates={t['task_id']:t for t in original['proposal']['tasks']}
        logs=list((base/'private/calls').glob('*.json'))
        for replacement in replacements:
            path=replacement/case['case_id']/'private/candidate.json'
            if not path.exists():continue
            other=read_json(path)
            for key in ('material_sha256','records_file_sha256'):
                if other['identity'][key]!=original['identity'][key]:raise DataError('Changed source in replacement')
            for task in other['proposal']['tasks']:
                if task['task_id'] not in candidates:raise DataError('Unknown replacement')
                candidates[task['task_id']]=task
            logs.extend((replacement/'private/calls').glob('*.json'))
        proposal={'material_id':original['proposal']['material_id'],'tasks':list(candidates.values())}
        source=Path(case['source_case_dir']);material=read_json(source/'private/material.json')
        records=read_json(source/'private/records.json')
        public=export_tasks(proposal,material,public_environment(material,records,case['public_context']),case['targets'])
        logs_content=[read_json(p) for p in logs]
        if any(not any(log.get('metadata',{}).get('status')=='completed' and
                       t in log.get('output',{}).get('tasks',[]) for log in logs_content) for t in proposal['tasks']):
            raise DataError('Unlogged task object')
        saved=original|{'proposal':proposal,'source_call_logs':[str(p.resolve()) for p in logs],
                        'status':'pending_autonomous_review','assembly':'Immutable API object selection'}
        write_json(out/case['case_id']/'private/candidate.json',saved)
        write_json(out/case['case_id']/'candidate_tasks.json',public)
    write_json(out/'private/manifest.json',manifest)
    write_json(out/'selection_manifest.private.json',{'base_run':str(base),'replacement_runs':[str(p) for p in replacements],
               'public_text_edits':0,'status':'pending_autonomous_review'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--replacement',type=Path,action='append',default=[])
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();assemble(a.base,a.replacement,a.out)
