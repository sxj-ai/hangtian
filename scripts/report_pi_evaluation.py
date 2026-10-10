"""Render executed runs and separately authored semantic reviews; no auto-grading."""
import argparse
from collections import Counter
import html
import json
from pathlib import Path


def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def lines(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s] if path.exists() else []


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--reporting-probe',type=Path)
    a=p.parse_args();root=a.run
    config=read(root/'model_config.json',{})
    budget_audit=read(root/'budget_boundary_audit.json',{})
    oracle=read(root/'independent_observation_verification.json',{})
    review=read(root/'semantic_review.private.json',{'tasks':[]})
    reviews={r['task_id']:r for r in review['tasks']}
    items=[];cards=[];diagnostics=[]
    esc=lambda s:html.escape(str(s))
    for index in range(1,16):
        tid=f'T{index:02d}';d=root/(tid+'_tools')
        meta=read(d/'run_metadata.json',{})
        trajectory=read(d/'trajectory.json',{'observations':[],'errors':[],'answer':None})
        task=read(d/'public_input.json',{})
        integrity=read(d/'evidence_verification.json',{})
        verdict=reviews.get(tid,{'decision':'pending','summary':'尚未完成语义审核'})
        wire=lines(d/'response_audit.jsonl');requests=lines(d/'request_audit.jsonl')
        input_tokens=sum((x.get('usage') or {}).get('prompt_tokens',0) for x in wire)
        output_tokens=sum((x.get('usage') or {}).get('completion_tokens',0) for x in wire)
        observations=trajectory['observations']
        numerical=[c for c in oracle.get('checks',[]) if c['task_id']==tid]
        models=sorted({m for r in wire for m in r.get('models',[])})
        emitted={c['id'] for m in lines(d/'assistant_messages.jsonl') for c in m.get('content',[]) if c.get('type')=='toolCall'}
        executed={c['tool_call_id'] for c in lines(d/'tool_calls.jsonl')}
        item={'task_id':tid,'run_status':meta.get('status','not_run'),
            'requests':meta.get('api_requests',0),'observations':len(observations),
            'tool_errors':len(trajectory['errors']),'evidence_integrity_pass':integrity.get('evidence_integrity_pass'),
            'observation_values_pass':all(c['passed'] for c in numerical) if len(numerical)==len(observations) and numerical else None,
            'tool_calls_without_backend_log':sorted(emitted-executed),
            'semantic_decision':verdict['decision'],'response_models':models,
            'thinking_disabled_on_all_requests':bool(requests) and all(
                r.get('thinking',{}).get('type') == 'disabled' if config.get('model') == 'deepseek-flash'
                else r.get('chat_template_kwargs',{}).get('enable_thinking') is False for r in requests),
            'reasoning_content_seen':any(r.get('reasoning_content_seen') for r in wire),
            'input_tokens':input_tokens,'output_tokens':output_tokens}
        item['budget_state']=meta.get('budget_state')
        items.append(item)
        answer=trajectory['answer']
        findings='' if not answer else ''.join('<li>'+esc(f['claim'])+'<br><small>'+esc(', '.join(f['observation_ids']))+'</small></li>' for f in answer['findings'])
        fallback=read(d/'final_text.json',{}).get('text','')
        explanation=('<p>未收到结构化答案。以下是保存的最后一段模型文本，不自动视为合规提交。</p><pre>'+esc(fallback)+'</pre>') if not answer else '<ol>'+findings+'</ol><p><b>结论：</b>'+esc(answer['conclusion'])+'</p><p><b>限制：</b>'+esc('；'.join(answer['limitations']))+'</p>'
        calls=''.join('<details><summary>'+esc(o['observation_id']+' · '+o['query']['op']+' · '+o['query']['record_id'])+'</summary><pre>'+esc(json.dumps(o,ensure_ascii=False,indent=2))+'</pre></details>' for o in observations)
        probe_html=''
        if a.reporting_probe:
            pd=a.reporting_probe/(tid+'_report_only')
            pm=read(pd/'run_metadata.json',{})
            pt=read(pd/'trajectory.json',{})
            if pm:
                pi=read(pd/'evidence_verification.json',{})
                attempts=[c['arguments'] for m in lines(pd/'assistant_messages.jsonl') for c in m.get('content',[]) if c.get('type')=='toolCall' and c.get('name')=='submit_report']
                diagnostics.append({'task_id':tid,'status':pm['status'],'requests':pm['api_requests'],
                    'evidence_integrity_pass':pi.get('evidence_integrity_pass'),
                    'answer':pt.get('answer'),'unaccepted_submission_attempts':attempts if not pt.get('answer') else [],
                    'semantic_review':verdict.get('reporting_diagnostic')})
                display=pt.get('answer') or {'status':'未被接口接受的提交尝试，不算有效报告','attempts':attempts,'tool_feedback':lines(pd/'pi_tool_results.jsonl')}
                probe_html='<details><summary>补充收束诊断：仅用已有证据，不计入自主完成率</summary><pre>'+esc(json.dumps(display,ensure_ascii=False,indent=2))+'</pre></details>'
        audit_calls=lines(d/'tool_calls.jsonl')
        errors=[c for c in audit_calls if c.get('result',{}).get('error')]
        trace_html='<details><summary>查询错误与模型中间输出</summary><pre>'+esc(json.dumps({'backend_errors':errors,'calls_without_backend_log':item['tool_calls_without_backend_log'],'assistant_messages':lines(d/'assistant_messages.jsonl')},ensure_ascii=False,indent=2))+'</pre></details>'
        cards.append('<article id="'+tid+'"><div class="eyebrow">'+tid+' · '+esc(item['run_status'])+' · 审核 '+esc(verdict['decision'])+'</div><h2>'+esc(task.get('title',tid))+'</h2><p>'+esc(task.get('prompt',''))+'</p><div class="review">'+esc(verdict['summary'])+'</div><p class="meta">模型请求 '+str(item['requests'])+' · 有效观测 '+str(item['observations'])+' · 后台工具错误 '+str(item['tool_errors'])+' · 数据数值复算 '+esc(item['observation_values_pass'])+'</p><details><summary>原始自主运行的答案</summary>'+explanation+'</details>'+probe_html+'<details><summary>逐项审核依据</summary><pre>'+esc(json.dumps(verdict,ensure_ascii=False,indent=2))+'</pre></details><details><summary>完整数据查询与证据</summary>'+calls+'</details>'+trace_html+'</article>')
    summary={'model':config.get('model','unknown'),'thinking':config.get('thinking','unknown'),'agent':'Pi SDK '+config.get('pi_package_version','unknown'),
        'task_count':15,'attempted':sum(x['requests']>0 for x in items),
        'submitted':sum(x['run_status']=='submitted' for x in items),
        'semantic_decisions':dict(Counter(x['semantic_decision'] for x in items)),
        'model_requests':sum(x['requests'] for x in items),'observations':sum(x['observations'] for x in items),
        'input_tokens':sum(x['input_tokens'] for x in items),'output_tokens':sum(x['output_tokens'] for x in items),
        'tasks':items,'limitations':['Single model, one run per task; not a general difficulty or discrimination estimate.',
            'Integrity and numerical checks do not automatically establish semantic correctness.']}
    summary['execution_config']=config
    summary['budget_boundary_audit']={k:v for k,v in budget_audit.items() if k!='tasks'}
    summary['review_status']=review.get('stage','pending')
    summary['overall_review']=review.get('overall')
    summary['execution_protocol_consistency']=read(root/'budget_turn_consistency.private.json')
    summary['reporting_diagnostic']={'condition':'Prompted report from unchanged previously selected evidence; excluded from autonomous completion.',
        'attempted':len(diagnostics),'submitted':sum(d['status']=='submitted' for d in diagnostics),'tasks':diagnostics}
    (root/'evaluation_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    controls=''
    for tid in ['T01','T05','T12']:
        d=root/(tid+'_no_data')
        if not d.exists(): continue
        text=read(d/'final_text.json',{}).get('text','未完成')
        controls+='<details><summary>'+tid+' 无数据对照</summary><pre>'+esc(text)+'</pre></details>'
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>15题 Pi Agent 实测审核</title><style>
body{margin:0;background:#f3f5f7;color:#163047;font:16px/1.85 system-ui,sans-serif}main{max-width:1060px;margin:auto;padding:32px 20px}h1{font-size:30px;line-height:1.4}h2{font-size:21px}article,.overview{background:white;border:1px solid #d9e2e9;border-radius:12px;padding:24px;margin:20px 0}.eyebrow,.meta,small{font-size:13px;color:#557086}.review{padding:14px 18px;background:#edf3f8;border-left:4px solid #477499}details{margin:14px 0}summary{cursor:pointer;font-weight:600}pre{font:13px/1.7 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:650px;overflow:auto;background:#f4f6f8;padding:16px}nav a{display:inline-block;padding:5px 10px;color:#326181}li{margin:12px 0}</style><main>
<h1>15 道自主分析任务 · Pi Agent 实测与审核</h1>'''
    page+='<p>'+esc(config.get('model','未知模型'))+' · '+esc(config.get('protocol_version','历史执行协议'))+' · 非思考模式 · 每题独立会话 · 公开任务与后台答案隔离</p>'
    labels={'incomplete':'未提交','fail':'关键错误','partial':'部分达到','pass_with_notes':'核心达到，有细节问题','pass':'通过','pending':'待审核'}
    table='<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;text-align:left"><tr><th>任务</th><th>自主提交</th><th>成功查询</th><th>审核结论</th></tr>'+''.join('<tr><td><a href="#'+x['task_id']+'">'+x['task_id']+'</a></td><td>'+('已提交' if x['run_status']=='submitted' else '未提交')+'</td><td>'+str(x['observations'])+'</td><td>'+esc(labels.get(x['semantic_decision'],x['semantic_decision']))+'</td></tr>' for x in items)+'</table></div>'
    findings='<article><h2>整批问题与后续改进</h2><ul>'+''.join('<li>'+esc(s)+'</li>' for s in review.get('framework_findings',[]))+'</ul><p>'+esc(review.get('diagnostic_conclusion',''))+'</p><p>'+esc(review.get('next_step',''))+'</p></article>'
    diagnostic_summary=('<p>补充收束诊断：提交 '+str(summary['reporting_diagnostic']['submitted'])+'/'+str(len(diagnostics))+'，不计入上面的自主完成数。</p>') if a.reporting_probe else ''
    settings='<p>每题模型请求上限 '+esc(config.get('max_api_calls_per_task','?'))+' · 查询上限 '+esc(config.get('max_tool_calls_per_task','?'))+' · 上下文 '+esc(config.get('context_window','?'))+' token'+(' · 随机种子 '+esc(config['seed']) if 'seed' in config else '')+'</p>'
    if config.get('reserved_report_requests'):
        settings+='<p>预留 '+esc(config['reserved_report_requests'])+' 次同会话提交／修正机会；每次请求显示剩余预算。</p>'
    controls_html=('<article><h2>无数据对照（单独计数）</h2><p>观察是否能从题面推测关键数据结论，不以无法引用数据作为题目质量证明。</p><pre>'+esc(json.dumps(review.get('controls_review',{}),ensure_ascii=False,indent=2))+'</pre>'+controls+'</article>') if controls else ''
    page+='<div class="overview"><p>自主运行：尝试 '+str(summary['attempted'])+'/15 · 提交 '+str(summary['submitted'])+'/15</p>'+settings+diagnostic_summary+'<p>'+esc(review.get('overall','语义审核尚未完成。运行完成不等于答案正确，也不等于任务质量已得到全面证明。'))+'</p>'+table+'</div>'+findings+''.join(cards)+controls_html+'</main></html>'
    (root/'report.html').write_text(page,encoding='utf-8')
    print({k:v for k,v in summary.items() if k not in ['tasks','limitations','reporting_diagnostic']})


if __name__=='__main__': main()
