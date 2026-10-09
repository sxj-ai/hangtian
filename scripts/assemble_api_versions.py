"""Select immutable API task versions; never edit public prose or auto-approve."""
import argparse
from pathlib import Path
from hangtian.data import DataError, digest, write_json
from hangtian.materials import build_material, public_task, read_json, verify_proposal


def assemble(manifest_path, out):
    if out.exists():raise DataError('Use a fresh assembly directory')
    manifest=read_json(manifest_path)
    if len({c['case_id'] for c in manifest['cases']}) != len(manifest['cases']):
        raise DataError('Duplicate case ID')
    summaries=[]
    for case in manifest['cases']:
        case_dir=out/case['case_id']
        material,records=build_material(Path(case['recipe_path']),case_dir)
        tasks=[];origins=[]
        for choice in case['selections']:
            source=Path(choice['source_case_dir'])
            candidate=read_json(source/'private/generated_candidate.json')
            if candidate.get('authorship')!='remote_api':raise DataError('Non-API candidate')
            proposal=candidate['proposal']
            if proposal['material_id']!=material['material_id']:raise DataError('Material identity mismatch')
            matches=[t for t in proposal['tasks'] if t['task_id']==choice['task_id']]
            if len(matches)!=1:raise DataError('Selected task is missing/duplicated')
            task=matches[0];call=None
            for log in sorted((source.parent/'private/calls').glob('*.json')):
                record=read_json(log)
                if record.get('metadata',{}).get('status')=='completed' and record.get('output')==proposal:
                    call=(log,record['metadata']);break
            if call is None:raise DataError('Candidate does not match recorded API output')
            tasks.append(task)
            origins.append({'task_id':task['task_id'],'task_sha256':digest(task),
                'source_case_dir':str(source),'call_log':str(call[0]),
                'request_id':call[1].get('request_id'),'requested_model':call[1]['requested_model'],
                'prompt_sha256':call[1]['prompt_sha256'],'input_sha256':call[1]['input_sha256']})
        proposal={'material_id':material['material_id'],'tasks':tasks}
        verify_proposal(proposal,material)
        public=[public_task(t,material) for t in tasks]
        generated={'proposal':proposal,'public_tasks':public,'review':None,'authorship':'remote_api',
            'status':'pending_assistant_review','assembly':'Unmodified API task objects selected across recorded calls.',
            'task_origins':origins}
        write_json(case_dir/'private/generated_candidate.json',generated)
        write_json(case_dir/'private/task_origins.json',origins)
        write_json(case_dir/'candidate_tasks.json',public)
        summary={'material_id':material['material_id'],'status':'api_generated_pending_assistant_review',
            'records':len(records),'source_lineages':len({p['series_id'] for p in material['provenance']}),
            'fact_count':len(material['facts']),'tasks_generated':len(tasks),'trajectories':0,'pilot_passed':0,
            'mode':'remote','data_origin':material['data_origin'],'generator':origins[0]['requested_model'],'review_mode':'assistant'}
        write_json(case_dir/'summary.json',summary);summaries.append(summary)
    write_json(out/'private/selection_manifest.json',manifest)
    write_json(out/'assembly_summary.json',{'cases':summaries,'public_text_edits':0,'acceptance':'Requires explicit new hash-bound reviews.'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();assemble(a.manifest,a.out)
