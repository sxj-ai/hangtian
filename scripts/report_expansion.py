"""Assemble reviewed cases and render API-written questions without reference answers."""
import argparse
import html
import json
from pathlib import Path
from hangtian.data import digest, write_json
from hangtian.materials import read_json


def render(run_dir, previous_runs):
    cases = []
    for d in sorted(run_dir.iterdir()):
        if (d / 'summary.json').exists():
            summary = read_json(d/'summary.json')
            if summary['status'] != 'api_generated_reviewed_reference_checked_pending_agent':
                raise ValueError('Unreviewed case: ' + d.name)
            cases.append((d, summary, read_json(d/'public/tasks.json')))
    tasks = sorted([t for _,_,ts in cases for t in ts], key=lambda t:t['task_id'])
    if not tasks or len({t['task_id'] for t in tasks}) != len(tasks):
        raise ValueError('Empty batch or duplicate task IDs')
    validations = [v for d,_,_ in cases for v in read_json(d/'validation_results.json')['results']]
    calls = []; api_tasks=set()
    for r in [*previous_runs, run_dir]:
        for p in sorted((r/'private/calls').glob('*.json')):
            record=read_json(p)
            proposal=record.get('output',{})
            for task in proposal.get('tasks',[]):
                api_tasks.add((proposal['material_id'],task['task_id'],digest(task)))
            calls.append({'run':r.name, **record['metadata'],
                'output_sha256':digest(record['output']) if 'output' in record else None,
                'task_versions_returned':len(record.get('output',{}).get('tasks',[]))})
    private_materials = [read_json(d/'private/material.json') for d,_,_ in cases]
    for d,_,_ in cases:
        proposal=read_json(d/'private/generated_candidate.json')['proposal']
        if any((proposal['material_id'],t['task_id'],digest(t)) not in api_tasks for t in proposal['tasks']):
            raise ValueError('Final task does not match a recorded API output')
    summary = {'status':'api_generated_reviewed_reference_checked_pending_agent',
        'materials':len(cases), 'tasks_generated':len(tasks), 'assistant_reviewed':len(tasks),
        'material_facts':sum(len(m['facts']) for m in private_materials),
        'selected_records_across_materials':sum(len(m['provenance']) for m in private_materials),
        'unique_raw_sources':len({p['source_hashes']['telemetry'] for m in private_materials for p in m['provenance']}),
        'hard_checks':sum(len(v['reference_tool_consistency']['checks']) for v in validations),
        'negative_controls':sum(len(v['validator_negative_controls']) for v in validations),
        'api_calls_including_revisions':len(calls),
        'api_models':sorted({c['requested_model'] for c in calls}),
        'api_roles':sorted({c['role'] for c in calls}),
        'api_candidate_task_versions':sum(c['task_versions_returned'] for c in calls),
        'final_tasks_match_recorded_api_outputs':True,
        'independent_raw_checks':sum(len(read_json(d/'independent_material_validation.json')['checks']) for d,_,_ in cases),
        'usage':{k:sum(c.get('usage',{}).get(k,0) for c in calls) for k in ['prompt_tokens','completion_tokens','total_tokens']},
        'independent_agent_trajectories':0, 'agent_pass_rate':None,
        'cases':[s for _,s,_ in cases],
        'limitations':['Guided evidence-analysis tasks with curator-defined measurements and propositions.',
            'No independent agent solve or physical root-cause validation.',
            'Cases share source experiments; do not split tasks randomly into train/test.',
            'New material families still require evidence curation and review.']}
    write_json(run_dir/'tasks.json',{'schema_version':'0.3','tasks':tasks})
    write_json(run_dir/'validation_results.private.json',{'results':validations})
    write_json(run_dir/'generation_provenance.json',{'calls':calls,'task_authorship':'deepseek-flash API','reviewer':'current_assistant'})
    write_json(run_dir/'final_summary.json',summary)
    e = lambda x:html.escape(str(x),quote=True)
    cards = []
    for t in tasks:
        statements=''.join('<li><code>'+e(i['interpretation_id'])+'</code> '+e(i['statement'])+'</li>' for i in t['interpretations'])
        measures=''.join('<tr><td><code>'+e(m['measurement_id'])+'</code></td><td><code>'+e(json.dumps(m['query'],ensure_ascii=False))+'</code></td><td>'+e(m['unit'])+'</td></tr>' for m in t['measurements'])
        cards.append('<article id="'+e(t['task_id'])+'"><div class="tag">'+e(t['task_id'])+' · '+e(t['material_id'])+'</div><h2>'+e(t['title'])+'</h2><p class="prompt">'+e(t['prompt'])+'</p><h3>需要判断的陈述</h3><p class="muted">以下是待判断命题，不是已经给出的事实。逐条选择 supported / refuted / insufficient，并引用工具观测。</p><ol>'+statements+'</ol><details><summary>查看 '+str(len(t['measurements']))+' 项测量定义和公共背景</summary><table><thead><tr><th>测量 ID</th><th>工具查询</th><th>单位</th></tr></thead><tbody>'+measures+'</tbody></table><ul>'+''.join('<li>'+e(b)+'</li>' for b in t['background'])+'</ul></details></article>')
    nav=''.join('<a href="#'+e(t['task_id'])+'">'+e(t['task_id'])+'</a>' for t in tasks)
    doc='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>12道 API 生成任务 · 航天数据材料</title><style>
body{margin:0;background:#f4f6f8;color:#182a3a;font:16px/1.8 "Microsoft YaHei",sans-serif}main{max-width:1080px;margin:auto;padding:40px 24px}header{background:#112c43;color:white;border-radius:16px;padding:32px}h1{font-size:30px;line-height:1.4;margin:0 0 16px}h2{font-size:22px;line-height:1.5}h3{font-size:17px}.stats{display:flex;gap:16px;flex-wrap:wrap}.stats span{background:#26455e;padding:10px 18px;border-radius:8px}nav{display:flex;flex-wrap:wrap;gap:10px;padding:22px 0}nav a{color:#126771;padding:4px 10px;background:white;border-radius:5px}article{background:white;border:1px solid #dce3e9;border-radius:12px;padding:28px;margin-bottom:24px;scroll-margin-top:20px}.tag{font-size:14px;color:#1a7478;font-weight:bold}.prompt{white-space:pre-wrap}.muted{color:#586b79;font-size:14px}li{margin:8px 0}code{font-size:13px;overflow-wrap:anywhere}details{margin-top:20px;border-top:1px solid #dce3e9;padding-top:16px}summary{cursor:pointer;color:#126771}table{border-collapse:collapse;width:100%;font-size:13px;margin-top:16px;table-layout:fixed}th,td{border:1px solid #dce3e9;text-align:left;padding:8px;overflow-wrap:anywhere}th:first-child{width:30%}th:last-child{width:9%}a{color:#126771}@media print{body{background:white}main{padding:0}header{color:black;background:white;border-bottom:2px solid #222}nav{display:none}article{break-inside:avoid;border-radius:0}details{display:none}.stats span{background:#eee}}
</style><main><header><h1>新增任务 T04–T15</h1><p>四组材料 → deepseek-flash API 出题 → 当前助手逐题审查 → 程序复核。</p><div class="stats"><span>4 组材料</span><span>12 道新增题</span><span>审题已完成</span><span>独立 Agent 解题待开展</span></div></header>'''
    doc+='<nav>'+nav+'</nav><p>本页展示 API 最终生成的完整题面，不含参考答案。测量定义来自经过核查的材料。题目属于有引导的证据分析任务，尚不能据此报告 Agent 通过率。</p><p><a href="tasks.json">任务 JSON</a> · <a href="final_summary.json">运行汇总</a> · <a href="generation_provenance.json">API 调用记录摘要</a></p>'+''.join(cards)+'</main></html>'
    doc=doc.replace('12道 API 生成任务',str(len(tasks))+'道 API 生成任务')
    doc=doc.replace('新增任务 T04–T15','任务 '+e(tasks[0]['task_id'])+'–'+e(tasks[-1]['task_id']))
    doc=doc.replace('四组材料 →',str(len(cases))+'组材料 →').replace('4 组材料</span>',str(len(cases))+' 组材料</span>')
    doc=doc.replace('12 道新增题</span>',str(len(tasks))+' 道题</span>')
    (run_dir/'questions.html').write_text(doc,encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--previous-run',type=Path,action='append',default=[])
    a=p.parse_args();render(a.run_dir,a.previous_run)
