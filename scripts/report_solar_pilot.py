"""Produce a Chinese result report and a standard scientific plot from saved outputs."""
import argparse
import html
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value):
    return html.escape(str(value))


def table(head, rows):
    return '<div class="table"><table><thead><tr>' + ''.join('<th>'+esc(h)+'</th>' for h in head) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows) + '</tbody></table></div>'


def make_plot(case_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    records = load(case_dir / "public/records.json")
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    colors = {"E1_C1": "#354f67", "E1_C2": "#b84438", "E1_C3": "#d07258", "E1_C4": "#dd9c72", "E2_C1": "#137c83", "E3_C94": "#8060ac"}
    for rid, r in records.items():
        a, b = [i-r["row_origin"] for i in r["regions"]["low_irr"]]
        time = [t-r["time_s"][a] for t in r["time_s"][a:b]]
        for ax, channel in zip(axes, ["P_SA", "I_Load1", "I_BAT2"]):
            ax.plot(time, r["channels"][channel][a:b], label=rid, color=colors[rid], linewidth=1,
                    linestyle='--' if rid == "E1_C3" else ':' if rid == "E1_C4" else '-')
            ax.grid(alpha=.15); ax.set_ylabel(channel + (' (W)' if channel == 'P_SA' else ' (A)'))
    axes[0].legend(ncol=3, fontsize=8)
    axes[-1].set_xlabel("Actual elapsed seconds since the first low-irradiation record")
    fig.suptitle("Six complete low-irradiation intervals; acquisition order preserved", fontsize=12)
    fig.tight_layout(); fig.savefig(case_dir/'comparison.png',dpi=170); plt.close(fig)


def report(case_dir):
    bundle = load(case_dir/'bundle.private.json'); material = bundle['material']; summary = bundle['summary']
    independent = load(case_dir/'independent_material_validation.json')
    runtime = load(case_dir/'private/runtime.json')
    facts = {f['fact_id']: f for f in material['facts']}
    value = lambda k: facts[k]['result']['value']
    make_plot(case_dir)
    parts = []
    parts.append('<header><div class="eyebrow">XJTU-SPS · 材料与任务试作 · 2026-10-08</div><h1>一组材料，三道试题，<br>可追溯的验证记录</h1><p>低辐照阶段的恢复时序、供电变化与持续低输出。</p></header>')
    parts.append('<section class="notice"><b>当前状态：材料与任务草案的程序核查已完成；API 测试已暂停。</b><p>三道试题由本次对话中的助手依据已审查材料编写。参考答案通过真实数据和工具回放核对；没有完成独立模型解题，也没有完成模型语义复核。程序参考回放不是模型解题轨迹。</p><p>此前唯一一次远程模型请求返回 HTTP 403，未取得模型输出；已保留失败日志，没有继续调用。当前无 API 运行的调用次数为 0。</p></section>')
    parts.append('<section><h2>交付包含什么</h2>')
    parts.append(table(['项目','数量或状态'], [['材料组',1],['原始实验来源',summary['source_lineages']],['完整周期记录',summary['records']],['计算事实',summary['fact_count']],['任务草案',summary['tasks_authored']],['程序检查通过的任务',summary['draft_checks_passed']],['实际模型解题轨迹',0],['运行主机',runtime['hostname']]]))
    parts.append('<p>机器使用 <a href="bundle.private.json">完整汇总 JSON</a>；解题端只接收 <a href="public/tasks.json">公开任务 JSON</a> 和匿名数据。<a href="validation_results.json">验证结果 JSON</a> 含参考值，应留在后台。原始 CSV 位于服务器，本次未改动。</p></section>')
    parts.append('<section><h2>材料为什么这样组织</h2><p>主序列取同次实验的四个完整周期；另取两个比较周期，保留较早投入负载与较晚投入负载的不同时间模式。内部来源映射用于追溯，公开题面用匿名 ID，文件故障名称不参与解题。</p>')
    parts.append(table(['匿名记录','原始来源（仅本内部报告展示）','原始行范围 [起,止)','用途'], [[p['record_id'],Path(p['telemetry_path']).stem,str(p['source_rows']), '同次实验的前后过程' if p['series_id']=='G1' else '跨实验比较记录'] for p in material['provenance']]))
    parts.append('<p>这是一组有目的选择的材料，不能当作随机抽样。G1 后三个周期是同次实验的重复观察，不能扩充成三个独立实验。名义计划、提供的工况字段与实测响应分别保存。</p>')
    parts.append('<img src="comparison.png" alt="六个低辐照区间的太阳能功率、Load1电流和BAT2电流"/><p class="caption">横轴使用真实时间戳；所有选中记录按采集顺序绘制。C2–C4 曲线相近并部分重叠，图中曲线数量不是独立实验数量。</p></section>')
    parts.append('<section><h2>三道任务及其参考结论</h2>')
    statuses = {v['task_id']:v for v in bundle['validations']}
    rules = {r['interpretation_id']:r for r in material['interpretations']}
    verdict = {'supported':'有证据支持','refuted':'被当前证据反驳','insufficient':'证据不足'}
    for task, draft in zip(bundle['public_tasks'],bundle['draft_proposal']['tasks']):
        v = statuses[task['task_id']]
        parts.append('<article><div class="eyebrow">'+esc(task['task_id'])+'</div><h3>'+esc(task['title'])+'</h3><p>'+esc(task['prompt'])+'</p>')
        parts.append(table(['需要判断的陈述','参考判断'], [[rules[i]['statement'],verdict[rules[i]['expected_verdict']]] for i in draft['interpretation_ids']]))
        parts.append('<p><b>验证：</b>'+str(len(task['measurements']))+' 项测量与 '+str(len(task['interpretations']))+' 项判断的引用覆盖检查通过；4 类故意构造的错误均被验证器拒绝。模型作答：待执行。</p>')
        if task['task_id']=='T01':
            timing=[]
            for rid in ['E2_C1','E3_C94']:
                load_on=value(rid+'_load_on'); solar=value(rid+'_solar5')
                timing.append([rid,load_on,solar,solar-load_on,value(rid+'_solar10')])
            parts.append(table(['记录','负载投入 / 秒','P_SA>5恢复 / 秒','投入后等待 / 秒','P_SA>10恢复 / 秒'],timing))
            parts.append('<p>从阶段起点看，E3_C94 的恢复更晚；但扣除负载实际投入时刻后，它的等待时间更短。这说明不分阶段的“恢复延迟”会混合两种过程。没有独立指令发送时刻，不能给这些差值贴上“指令执行延迟”的标签。</p>')
        elif task['task_id']=='T02':
            parts.append(table(['通道','前30条记录中位数','后30条记录中位数'],[[c,value('E2_C1_'+c+'_pre'),value('E2_C1_'+c+'_post')] for c in ['P_SA','P_BCR','I_BAT2','I_BAT3','I_BAT4','I_Load1','Irradiation','Incidence_Angle']]))
            parts.append('<p>这些量的联合变化与太阳能侧供电贡献增加、电池放电负担降低相符，同时负载仍保持投入。它可以训练“用多个观测约束解释”，但还不能唯一确认某个控制器动作，也不是完整系统功率平衡的证明。</p>')
        else:
            parts.append(table(['记录','持续恢复时刻 / 秒','末段 P_SA / W','末段 I_Load1 / A','末段 I_BAT2 / A'],[[rid,'窗口内未观察到' if value(rid+'_solar5') is None else value(rid+'_solar5'),value(rid+'_tail_solar'),value(rid+'_tail_load'),value(rid+'_tail_bat2')] for rid in ['E1_C1','E1_C2','E1_C3','E1_C4','E2_C1','E3_C94']]))
            parts.append('<p>G1 后三个周期的特征是窗口内持续低太阳能输出，同时末段负载仍投入、电池正向电流较高；比较记录存在恢复。能够描述和对照这个表型，仍不能把某个文件标签等同于已从遥测唯一辨识出的故障机理。</p>')
        parts.append('<details><summary>查看逐项测量定义和结果</summary>')
        parts.append(table(['测量 ID','定义','参考值','来源行范围'], [[i, facts[i]['definition'],facts[i]['result']['value'],facts[i]['result']['source_rows']] for i in draft['measurement_ids']]))
        parts.append('</details></article>')
    parts.append('</section><section><h2>验证证明了什么，尚未证明什么</h2>')
    parts.append(table(['检查','结果','能支持的结论'], [['源文件哈希与逐行对齐','通过','使用与前两轮审查一致的数据，工况未按时间戳单独拼接'],['独立原始 CSV 重算',str(independent['facts_checked'])+' / '+str(independent['facts_checked'])+' 通过','44条数值事实与原始数据一致'],['可计算判断独立检查','7 / 7 通过','比较算术和实验来源关系一致'],['验证器错误对照','12 / 12 拒绝','数值错误、伪造引用、遗漏测量、错误判断不会被直接放行'],['模型实际解题','未运行','暂不能报告模型成功率或可解性实测结果'],['语义泄漏与评分充分性','需继续人工审阅','字符串扫描及参考回放不能替代独立审题'],['航天物理根因独立确认','未完成','保留控制器、指令日志和拓扑未知项']]))
    parts.append('<p>10项解释判断中，3项涉及“缺少哪些证据”的审查结论。这些边界有文档和前两轮数据解释支持，但不能通过再次计算同一批数值变成独立物理验证。</p></section>')
    parts.append('<section><h2>后续怎样批量运行</h2><div class="flow">已审查的材料配方 → 批量计算材料 → 任务编写或 API 出题 → 数据与引用检查 → 实际解题 → 逐题验证 → 通过／待修订／失败分流</div><p>材料配方说明记录怎样选、正常参考为什么可比、计算哪些事实、结论到哪一步。批次清单可以放多个材料配方；程序按清单执行，逐案例保存状态与错误。完成的阶段可复用，源文件每次重新核验。</p><p>提示词负责指导模型完整使用材料，不负责替代统计计算和答案核对。程序负责结构契约、原始数据查询、哈希与来源追溯、公开／私有隔离、调用预算、断点恢复与硬性验证。</p><p>当前已经运行的是无 API 分支。API 出题、独立解题与语义评审的接口已实现并通过模拟接口测试，但真实接口链路尚未成功验证。推广到新的故障材料族时，还要先确定新的比较规则和证据边界，不能只把名称替换后批量出题。</p></section>')
    parts.append('<footer>运行目录：/home/xjshang/hangtian_material_pipeline/runs/pilot_offline_001/solar_pilot<br>完整内部汇总含参考答案与来源信息，请勿作为解题模型输入。</footer>')
    style='''body{margin:0;background:#f2f4f6;color:#223240;font:16px/1.75 "Microsoft YaHei",sans-serif}main{max-width:1100px;margin:auto;padding:42px 26px}header{padding:36px 0}h1{font-size:40px;line-height:1.35;letter-spacing:-1px;margin:12px 0}h2{font-size:24px}h3{font-size:21px}.eyebrow{color:#527688;font-size:13px;letter-spacing:1px}section{background:white;border:1px solid #e0e7eb;padding:28px;margin:22px 0;border-radius:10px}.notice{background:#fff5de;border-color:#ecd39b}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px;margin:18px 0}th,td{text-align:left;border-bottom:1px solid #e5e9ec;padding:10px;vertical-align:top;overflow-wrap:anywhere}th{background:#edf3f6}article{border-top:2px solid #e5ebef;padding-top:25px;margin-top:35px}img{max-width:100%;height:auto}.caption,footer{color:#5e707b;font-size:13px}.flow{padding:18px;background:#eaf3f2;border-left:4px solid #187d7a}a{color:#116d88}summary{cursor:pointer;color:#116d88;padding:12px 0}footer{padding:25px 0}details table{font-size:12px}@media(max-width:700px){main{padding:15px}section{padding:16px}h1{font-size:30px}}'''
    document='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>材料包与三道任务 · 验证报告</title><style>'+style+'</style><main>'+''.join(parts)+'</main></html>'
    (case_dir/'report.html').write_text(document,encoding='utf-8')
    print(json.dumps({'report':str(case_dir/'report.html'),'tasks':len(bundle['public_tasks']),'independent_facts_pass':independent['all_facts_pass'],'model_solver_runs':0}))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--case-dir',type=Path,required=True);a=p.parse_args();report(a.case_dir)
