"""Publish immutable API outputs only after actual hash-bound assistant review."""
import argparse
import html
from pathlib import Path

from hangtian.autonomous import public_environment, export_tasks, review_gate
from hangtian.data import DataError, digest, file_hash, write_json
from hangtian.materials import read_json


def finalize(run_dir):
    manifest=read_json(run_dir/'private/manifest.json')
    oracle=read_json(run_dir/'window_verification.private.json')
    if not oracle.get('passed'):raise DataError('Missing window verification')
    tasks=[];origins=[];approved=[]
    # Validate the complete batch before writing any accepted public exports.
    for case in manifest['cases']:
        directory=run_dir/case['case_id'];source=Path(case['source_case_dir'])
        material=read_json(source/'private/material.json');records=read_json(source/'private/records.json')
        saved=read_json(directory/'private/candidate.json');proposal=saved['proposal']
        if (saved['authorship']!='remote_api' or saved['identity']['material_sha256']!=digest(material)
            or saved['identity']['records_file_sha256']!=file_hash(source/'private/records.json')
            or oracle['record_hashes'][case['case_id']]!=saved['identity']['records_file_sha256']):
            raise DataError('Changed source identity')
        public=export_tasks(proposal,material,public_environment(material,records,case['public_context']),case['targets'])
        review=read_json(directory/'private/autonomy_review.json')
        rubric=read_json(directory/'private/outcome_rubric.json')
        review_gate(review,proposal,public,material,rubric)
        log_paths=[Path(p) for p in saved.get('source_call_logs',[])] or list((run_dir/'private/calls').glob('*.json'))
        logs=[read_json(p) for p in log_paths]
        for task in proposal['tasks']:
            matches=[log['metadata'] for log in logs if log.get('metadata',{}).get('status')=='completed'
                     and log.get('output',{}).get('material_id')==proposal['material_id']
                     and task in log.get('output',{}).get('tasks',[])]
            if not matches:raise DataError('Task text does not match an API output')
            origin=matches[-1]
            if origin['requested_model']!='deepseek-flash' or origin.get('response_model')!='deepseek-flash':
                raise DataError('Unexpected model identity')
            origins.append({'task_id':task['task_id'],'authored_object_sha256':digest(task),
                'request_id':origin['request_id'],'requested_model':origin['requested_model'],
                'response_model':origin['response_model'],'prompt_sha256':origin['prompt_sha256']})
        tasks.extend(public);approved.append((directory,public))
    if len({t['task_id'] for t in tasks})!=len(tasks):raise DataError('Duplicate batch task identity')
    for directory,public in approved:write_json(directory/'public/tasks.json',public)
    tasks.sort(key=lambda t:t['task_id'])
    write_json(run_dir/'tasks.json',{'schema_version':'autonomous-0.1','tasks':tasks})
    write_json(run_dir/'generation_provenance.json',origins)
    summary={'status':'autonomy_reviewed_pending_independent_agent','tasks':len(tasks),
             'materials':len(approved),'agent_trajectories':0,'agent_pass_rate':None,
             'reference_query_lists_exposed':False,'reference_query_matching_required':False,
             'window_tool_checks':oracle['check_count'], 'semantic_scoring':'requires_outcome_review',
             'limitation':'Curated material subsets and bounded tools; agent difficulty/solvability not empirically measured.'}
    write_json(run_dir/'summary.json',summary)
    cards=[]
    for task in tasks:
        cards.append('<article><small>'+html.escape(task['task_id'])+'</small><h2>'+html.escape(task['title'])+
                     '</h2><p>'+html.escape(task['prompt'])+'</p><details><summary>可见的数据说明与通用交付要求</summary><ul>'+
                     ''.join('<li>'+html.escape(s)+'</li>' for s in task['environment']['context']+task['response_requirements'])+
                     '</ul></details></article>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>自主分析任务修订版</title><style>body{font:17px/1.85 system-ui,sans-serif;background:#f3f5f8;color:#182c3d;margin:0}main{max-width:940px;margin:auto;padding:28px 20px}article{background:white;padding:24px;margin:22px 0;border:1px solid #dce3ea;border-radius:12px}h1{font-size:28px}h2{font-size:21px;line-height:1.6;margin:6px 0 14px}small{color:#315f88}summary{cursor:pointer;color:#426481}li{margin:9px 0}.status{background:#e6eef6;padding:18px;border-radius:10px}</style><main>
<h1>自主分析任务修订版 · __COUNT__题</h1><p class="status">DeepSeek-flash 通过 API 生成，逐题人工（当前助手）审核。原题保留为旧版。此版不向解题模型提供参考查询、事件定位答案或评分依据。独立 Agent 尚未运行，不能据此报告解题成功率。</p>'''+''.join(cards)+'</main></html>'
    page=page.replace('__COUNT__',str(len(tasks)))
    (run_dir/'questions.html').write_text(page,encoding='utf-8')
    print(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True)
    finalize(p.parse_args().run_dir)
