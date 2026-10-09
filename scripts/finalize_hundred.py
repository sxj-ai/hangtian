"""Assemble 15 historical tasks + 85 reviewed, exact local-model API outputs."""
import argparse
import html
from collections import Counter
from pathlib import Path
from hangtian.autonomous import review_gate, export_tasks, public_environment
from hangtian.data import DataError, digest, file_hash, write_json
from hangtian.materials import read_json


def finalize(old, expansion, selection, out):
    if (out/'tasks.json').exists():raise DataError('Use a fresh publication directory')
    chosen=read_json(selection)
    manifest=read_json(expansion/'private/manifest.json')
    oracle=read_json(expansion/'window_verification.private.json')
    raw=read_json(expansion/'independent_raw_verification.private.json')
    policy=read_json(expansion/'final_grading_policy.private.json')
    if policy.get('author')!='current_assistant' or not policy.get('policy'):
        raise DataError('Missing final grading policy')
    if not oracle['passed'] or not raw['passed']:raise DataError('Reference verification failed')
    if len(manifest['cases'])!=17 or set(chosen)!=set(c['case_id'] for c in manifest['cases']):
        raise DataError('Incomplete material selection')
    tasks=read_json(old/'tasks.json')['tasks'];cases=read_json(old/'private/manifest.json')['cases']
    origins=read_json(old/'generation_provenance.json')
    staged=[];reviews=[]
    # Old public tasks are immutable; retain their original approvals and actual evaluation status.
    for case in cases:
        directory=old/case['case_id'];source=Path(case['source_case_dir'])
        material=read_json(source/'private/material.json');saved=read_json(directory/'private/candidate.json')
        public=read_json(directory/'public/tasks.json');review=read_json(directory/'private/autonomy_review.json')
        rubric=read_json(directory/'private/outcome_rubric.json')
        review_gate(review,saved['proposal'],public,material,rubric)
        if saved['identity']['records_file_sha256']!=file_hash(source/'private/records.json'):raise DataError('Old data changed')
        if [t for t in tasks if t['task_id'] in case['targets'].values()]!=public:raise DataError('Old aggregate mismatch')
        staged.append((case['case_id'],saved,public,review,rubric))
    for case in manifest['cases']:
        cid=case['case_id'];directory=Path(chosen[cid]);source=Path(case['source_case_dir'])
        material=read_json(source/'private/material.json');records=read_json(source/'private/records.json')
        saved=read_json(directory/'private/candidate.json');proposal=saved['proposal']
        identity=saved['identity']
        if saved['authorship']!='local_model_api' or saved['model']!='Qwen3.5-27B':raise DataError('Wrong author identity')
        if identity['material_sha256']!=digest(material) or identity['records_file_sha256']!=file_hash(source/'private/records.json'):
            raise DataError('Material identity changed')
        if oracle['record_hashes'][cid]!=identity['records_file_sha256']:raise DataError('Unverified arrays')
        public=export_tasks(proposal,material,public_environment(material,records,case['public_context']),case['targets'])
        review=read_json(directory/'private/autonomy_review.json');rubric=read_json(directory/'private/outcome_rubric.json')
        if rubric.get('policy')!=policy['policy'] or rubric.get('version')!=policy['version']:
            raise DataError('New-task grading policy mismatch')
        review_gate(review,proposal,public,material,rubric)
        logs=[read_json(Path(p)) for p in saved['source_call_logs']]
        for task in proposal['tasks']:
            matches=[l for l in logs if l['status']=='returned' and
                task in __import__('json').loads(l['response']['choices'][0]['message']['content'])['tasks']]
            if len(matches)!=1:raise DataError('Task is not an exact logged model output')
            log=matches[0]
            if log['request']['model']!='Qwen3.5-27B' or log['response']['model']!='Qwen3.5-27B' or log['request']['chat_template_kwargs']['enable_thinking'] is not False:
                raise DataError('Wrong model/mode')
            origins.append({'task_id':task['task_id'],'authored_object_sha256':digest(task),
                'request_id':log['response']['id'],'requested_model':log['request']['model'],
                'response_model':log['response']['model'],'prompt_sha256':digest(log['request']['messages'][0]['content']),
                'source_call_logs':saved['source_call_logs'],'thinking':False})
        tasks.extend(public);cases.append(case);reviews.extend(review['reviews'])
        staged.append((cid,saved,public,review,rubric))
    if len(tasks)!=100 or {t['task_id'] for t in tasks}!={f'T{i:02d}' for i in range(1,101)}:
        raise DataError('Expected exactly T01 through T100')
    tasks.sort(key=lambda t:int(t['task_id'][1:]))
    for cid,saved,public,review,rubric in staged:
        for path,obj in [('private/candidate.json',saved),('public/tasks.json',public),
                         ('private/autonomy_review.json',review),('private/outcome_rubric.json',rubric)]:
            write_json(out/cid/path,obj)
    write_json(out/'private/manifest.json',{'schema_version':'autonomous-0.1','cases':cases})
    write_json(out/'tasks.json',{'schema_version':'autonomous-0.1','tasks':tasks})
    write_json(out/'generation_provenance.json',origins)
    write_json(out/'selection_manifest.private.json',chosen)
    write_json(out/'final_grading_policy.private.json',policy)
    for name,obj in [('window_verification.private.json',oracle),('independent_raw_verification.private.json',raw)]:write_json(out/name,obj)
    prompts=Counter(t['prompt'] for t in tasks)
    exact=[{'prompt':p,'count':n} for p,n in prompts.items() if n>1]
    summary={'status':'generation_and_assistant_review_complete_pending_new_agent_solves',
        'tasks':100,'retained_tasks':15,'new_tasks':85,'new_material_packs':17,
        'source_experiments_in_new_tasks':17,'shared_reference_source_experiments':1,
        'final_new_task_grading_policy_sha256':digest(policy),
        'new_agent_trajectories':0,'independent_task_types':None,
        'author_model_new':'Qwen3.5-27B','thinking_new':False,
        'new_raw_checks':raw['check_count'],'new_saved_window_checks':oracle['check_count'],
        'identical_prompt_groups':exact,
        'limits':['Tasks are related development instances, not 100 independent experiments or unique reasoning types.',
            'New tasks have not been solved by an independent Agent. Prior 15 have mixed/incomplete execution outcomes.',
            'Source experiments and shared reference records overlap. Do not randomly split by task.']}
    write_json(out/'summary.json',summary)
    cards=[]
    case_for={tid:c['case_id'] for c in cases for tid in c['targets'].values()}
    for t in tasks:
        cid=case_for[t['task_id']]
        state='保留旧题；已有一轮 Agent 运行记录' if int(t['task_id'][1:])<=15 else '新增；Qwen 生成、助手审题，尚未 Agent 实跑'
        catalog='；'.join(f'{r["record_id"]}（序列{r["series_id"]}，周期{r["sequence_index"]}，原始行[{r["start_row"]}, {r["stop_row"]})）' for r in t['environment']['records'])
        cards.append(f'<article data-search="{html.escape(t["task_id"]+cid+t["title"]+t["prompt"],quote=True)}"><small>{t["task_id"]} · 材料组 {cid} · {state}</small><h2>{html.escape(t["title"])}</h2><p>{html.escape(t["prompt"])}</p><details><summary>公开数据说明</summary><p>'+html.escape(catalog)+'</p><ul>'+''.join('<li>'+html.escape(s)+'</li>' for s in t['environment']['context'])+'</ul></details></article>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>100道遥测自主分析任务</title>
<style>body{font:17px/1.8 system-ui,sans-serif;background:#f3f5f8;color:#173049;margin:0}main{max-width:1000px;margin:auto;padding:32px 22px}h1{font-size:30px}h2{font-size:21px}article{padding:22px 26px;background:white;border:1px solid #d9e1e8;border-radius:10px;margin:20px 0}small{color:#4b6379}input{box-sizing:border-box;width:100%;padding:14px;font:inherit;border:1px solid #a9b8c8;border-radius:8px}summary{cursor:pointer}aside{padding:20px;background:#e5edf3;border-radius:8px}li{margin:8px 0}</style><main><h1>遥测自主分析任务 · 100题</h1>
<aside>保留原15题，新增85题。新增题由服务器本地Qwen3.5-27B通过API生成，非思考模式。材料覆盖17份来源记录和共享参考实验，包含同类能力在不同数据上的实例，不是100类独立问题。题面、附件和评分依据经过本助手审核；新增题尚未独立Agent实跑。旧题的历史运行也并非全部答对。</aside>
<p>公开任务只给调查目标和数据说明；参考数值、标签与评分标准保存在私有目录。记录ID以各材料组为作用域：不同材料组的A4并不是同一份数据，R参考记录则可能共享。</p><input id="filter" placeholder="搜索题号、材料组、标题或问题内容" aria-label="搜索任务"><p id="count">显示100题</p>'''+''.join(cards)+'''</main><script>document.querySelector('#filter').addEventListener('input',e=>{const q=e.target.value.toLowerCase();let n=0;document.querySelectorAll('article').forEach(a=>{const hit=a.dataset.search.toLowerCase().includes(q);a.hidden=!hit;if(hit)n++});document.querySelector('#count').textContent='显示'+n+'题'});</script></html>'''
    (out/'questions.html').write_text(page,encoding='utf-8');print(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ['old','expansion','selection','out']:p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();finalize(a.old,a.expansion,a.selection,a.out)
