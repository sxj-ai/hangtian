"""Readable authoring audit, kept separate from the solver-visible task file."""
import argparse
import html
from pathlib import Path
from hangtian.data import write_json
from hangtian.materials import read_json


def report(expansion, final):
    summary=read_json(final/'summary.json')
    if summary['tasks']!=100:raise ValueError('Only report an assembled bank')
    review_paths=sorted(expansion.glob('review_subagent_*.private.json'))
    notes=[(read_json(p),p) for p in review_paths]
    tasks={t['task_id']:t for t in read_json(final/'tasks.json')['tasks']}
    rows=[];decisions=[]
    for document,path in notes:
        for review in document['tasks']:
            tid=review['task_id'];task=tasks[tid]
            if review['public_decision']!='accept':raise ValueError('Unaccepted task in final report')
            if task['prompt']!=review.get('reviewed_prompt',review.get('prompt')):
                raise ValueError('Report review is stale')
            issues=review.get('rubric_issues',review.get('rubric_findings',review.get('rubric_rationale',[])))
            if isinstance(issues,str):issues=[issues]
            rationale=review.get('public_rationale',review.get('rationale'))
            item={'task_id':tid,'subagent':document['reviewer'],'public_decision':'accept',
                'model_rubric_decision':review['rubric_decision'],'rationale':rationale,
                'model_rubric_issues':issues,'accepted_outcome_criteria':review['proposed_outcome_criteria']}
            decisions.append(item)
            rows.append((int(tid[1:]),'<article><h2>'+html.escape(tid+' · '+task['title'])+'</h2><p>'+html.escape(task['prompt'])+
                '</p><p><b>题面审查：</b>'+html.escape(rationale)+'</p><p><b>原模型评分：</b>'+html.escape(review['rubric_decision'])+
                '</p><ul>'+''.join('<li>'+html.escape(x)+'</li>' for x in issues)+'</ul><details><summary>采纳的后台评分标准</summary><ul>'+
                ''.join('<li>'+html.escape(x)+'</li>' for x in review['proposed_outcome_criteria'])+'</ul></details></article>'))
    if len(decisions)!=85:raise ValueError('Incomplete review report')
    calls=[]
    for run in sorted((expansion/'generation_jobs').iterdir()):
        if not run.is_dir():continue
        status_path=run/'status.json'
        if not status_path.exists():continue
        status=read_json(status_path)
        requests=[read_json(p) for p in run.glob('pack_*_attempt*.json')]
        returned=[r for r in requests if r.get('response')]
        calls.append({'job_id':run.name,'status':status['status'],
            'attempt_files':len(requests),'responses':len(returned),
            'response_tokens':sum(r['response'].get('usage',{}).get('completion_tokens',0) for r in returned),
            'prompt_tokens':sum(r['response'].get('usage',{}).get('prompt_tokens',0) for r in returned),
            'model_service_stopped':status.get('model_service_stopped'),
            'backend':status.get('runtime',{}).get('backend','vllm')})
    audit={'scope':'85 newly generated tasks; retained 15 keep historical reviews and outcomes',
        'public_accepted':85,'model_rubrics_revised':sum(d['model_rubric_decision']=='revise' for d in decisions),
        'independent_agent_solves_new':0,'reviewers_are_ai_assistants':True,
        'source_overlap_requires_grouped_design':True,'decisions':decisions,'generation_jobs':calls}
    write_json(final/'quality_review.private.json',audit)
    table=''.join('<tr>'+''.join('<td>'+html.escape(str(r[k]))+'</td>' for k in ['job_id','status','responses','backend'])+'</tr>' for r in calls)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>100题生成与审查记录</title>
<style>body{font:17px/1.8 system-ui;background:#f4f6f8;color:#20384c;margin:0}main{max-width:1080px;margin:auto;padding:30px 24px}article,aside{background:white;border:1px solid #d7e0e8;border-radius:10px;padding:22px;margin:20px 0}h2{font-size:21px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #ccd6df;padding:8px;text-align:left}summary{cursor:pointer}</style><main><h1>100题生成与详细审查记录</h1>
<aside><b>这是出题方内部审查材料，不提供给解题 Agent。</b><p>保留15道旧题，新增85道；新增题由服务器本地Qwen3.5-27B非思考模式生成。三个subagent分组审查，本助手复核并确定最终评分规则。这是AI静态审核，不能充当独立Agent解题验证或航天专家结论。</p><p>17包新增材料覆盖17份目标来源和1份共享参考，70个独特记录窗口、389,360行不重复原始记录。3,708项原始中位数复算和3,912项保存窗口/工具核对通过。相同来源和参考反复使用，题数不代表独立实验或独立推理类型。</p></aside>
<h2>实际发现与处理</h2><ul><li>第一批85题含分析步骤、通道清单或未核实术语，全部退回；修改通用提示词后整批重新生成。</li><li>重生成批次的T38可仅凭目录回答，因此只重生成该题。程序强制新输出来自成功模型响应，不允许回退到旧版本。</li><li>评分规则改为核查结果、证据覆盖和推论范围；允许不同合理路径，不要求固定末60秒、指定通道清单或隐藏阈值。</li><li>局部零值不能证明全周期为零；有电压不能直接证明负载工作；同源周期相似不能证明跨实验复现或相同根因。</li><li>保留各次请求、响应、退回版本和逐题审查。最终题面须逐项等于模型原始输出；审查哈希绑定完整公开附件、材料及最终评分标准。</li></ul>
<h2>尚未完成的验证</h2><p>新增85题尚未独立Agent实跑，不能给出解题通过率、可靠难度或区分度。原15题已有历史运行，其中有未完成和推论错误，均未改写为通过。本轮扩展形成开发题库，不直接形成可训练的正确轨迹。</p>
<h2>生成作业记录</h2><p>表中状态是各作业结束时保留的生成阶段记录，最终采纳以逐题审核为准。返回次数包括被退回的真实模型响应。启动失败不计为模型返回；被取消且未启动的165723无模型调用。</p><table><tr><th>作业</th><th>状态</th><th>模型响应数</th><th>引擎</th></tr>'''+table+'''</table><h2>新增85题逐题记录</h2>'''+''.join(x for _,x in sorted(rows))+'''</main></html>'''
    (final/'review_report.html').write_text(page,encoding='utf-8')
    print({k:v for k,v in audit.items() if k not in ['decisions','generation_jobs']})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--expansion',type=Path,required=True);p.add_argument('--final',type=Path,required=True)
    a=p.parse_args();report(a.expansion,a.final)
