"""Prepare four audited material recipes, never author their public task text.

Run on HPC. Source hashes come from the two completed raw-data audits. Task slots
are evidence/assessment specifications. DeepSeek writes all titles, prompts and
public interpretation propositions through the batch API runner.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from hangtian.data import file_hash, write_json
from hangtian.materials import build_material


class Curator:
    def __init__(self, data_root, catalog_path, channels):
        self.root = data_root
        self.catalog = {x['source']: x for x in json.loads(catalog_path.read_text())}
        self.channels = channels
        self.cache = {}

    def source(self, name):
        if name not in self.cache:
            meta = self.catalog[name]
            tele = self.root / meta['raw_relative_path']
            ctx = tele.with_name(tele.stem + '_Work_Condition.csv')
            if file_hash(tele) != meta['sha256']:
                raise ValueError('Telemetry differs from previously audited source: ' + name)
            t, c = pd.read_csv(tele), pd.read_csv(ctx)
            if not t.Time.equals(c.Time):
                raise ValueError('Context alignment failed')
            elapsed = (pd.to_datetime(t.Time)-pd.to_datetime(t.Time).iloc[0]).dt.total_seconds()
            self.cache[name] = (meta, tele, ctx, t, elapsed)
        return self.cache[name]

    def record(self, name, cycle, rid, series, whole=False):
        meta, tele, ctx, frame, elapsed = self.source(name)
        a, b = (0,len(frame)) if whole else tuple(meta['cycle_anchor_rows'][cycle-1:cycle+1])
        clock = elapsed.iloc[a:b]-elapsed.iloc[a]
        def region(lo,hi):
            idx = clock[(clock>=lo)&(clock<hi)].index.tolist()
            if not idx or idx != list(range(idx[0],idx[-1]+1)):
                raise ValueError('Region is empty or not contiguous in acquisition order')
            return [idx[0],idx[-1]+1]
        bounds = {'early_segment':region(0,11400), 'late_segment':region(11400,float(clock.iloc[-1])+1)} if whole else {
            'boundary':region(0,40), 'load3_phase':region(600,1500),
            'idle_phase':region(1500,2100), 'load1_phase':region(2100,3000),
            'load2_phase':region(4200,5100)}
        lineage = 'G2' if name == '2024.9.18_normal' else 'L_'+meta['sha256'][:20]
        return {'record_id':rid,'series_id':series,'sequence_index':cycle,
            'lineage_group':lineage,'telemetry_path':str(tele),'context_path':str(ctx),
            'source_hashes':{'telemetry':meta['sha256'],'context':file_hash(ctx)},
            'source_rows':[a,b],'regions':bounds}


COMMON = [
    '记录按原始采集顺序保留，所有行范围均为从0开始、左闭右开。记录 ID 不编码健康类别或故障名称。',
    '同一 series_id 的周期来自同一次连续实验。不同周期不是独立重复实验。比较记录是目的性选择，不能代表总体分布。',
    'cycle内的名义阶段：load3_phase为600至1500秒，idle_phase为1500至2100秒，load1_phase为2100至3000秒，load2_phase为4200至5100秒。阶段名称描述名义计划，实际是否工作需用测量判断。',
    '提供的 Load_Signal 不能等同于独立指令发送日志；其生成方式存在未解决问题。传感器细节、控制器日志与完整接线拓扑未提供。',
    '电池正向电流按作者模型约定解释为放电；只提供BAT2、BAT3、BAT4三组测量，不能当作所有电池支路。',
    'last60s是窗口最后时间戳往前59秒（含端点）的全部记录。持续越阈以连续记录数定义，以真实时间戳给出经过秒数。',
    '中位数描述选中窗口，不证明窗口内每一个样本都相同。名义1 Hz数据不能排除未被采样捕捉的更快瞬态。'
]


class Recipe:
    def __init__(self, ident, title, records, channels, sources):
        self.r = {'schema_version':'0.2','material_id':ident,'title':title,'data_origin':'real','split':'development',
            'records':records,'channels':channels,'facts':[],'interpretations':[],'task_slots':[],
            'public_background':COMMON.copy(),'limitations':[
                '来源标签不是可以由这些测量唯一确定的物理根因。',
                '比较记录不是随机样本；不能从少数同源周期报告跨实验泛化能力。',
                '缺少独立指令日志、传感器校准和完整物理拓扑。'],
            'forbidden_public_strings':sources+['AnomalyLabel','/home/','original data/'],
            'selection_rationale':'Audited source/cycle comparisons; nominal phase names separated from observed response; complete selected cycles retained.',
            'evidence_sources':['Raw audit catalog with pinned telemetry hashes','Second-round targeted interpretation and 17-source evidence review'],
            'require_model_written_interpretations':True}
        self.ids = set()

    def fact(self,rid,channel=None,region='load1_phase',sl='last60s',op='stat',stat='median',metric=None,threshold=None,direction=None,channels=None):
        suffix = channel or metric or 'all_channels'
        fid = '_'.join([rid,region,sl,suffix,stat if op=='stat' else op])
        if fid in self.ids:
            return fid
        self.ids.add(fid)
        q={'record_id':rid,'op':op,'region':region,'slice':sl}
        if op=='stat':
            q.update(channel=channel,stat=stat);unit=self.r['channels'][channel]['unit']
        elif op=='quality':
            q['metric']=metric
            unit={'elapsed_span_s':'s','max_gap_s':'s','conflicting_timestamp_groups':'timestamp_groups',
                  'conflict_channel_count':'channels','gaps_gt_1s':'intervals','time_reversals':'intervals'}.get(metric,'records')
        elif op=='first_sustained':
            q.update(channel=channel,threshold=threshold,min_records=20,direction=direction);unit='s'
        else:
            q['channels']=channels;unit='records'
        self.r['facts'].append({'fact_id':fid,'definition':json.dumps(q,ensure_ascii=False,separators=(',',':')),
                               'query':q,'unit':unit})
        return fid

    def stats(self, rids, columns, region='load1_phase', sl='last60s'):
        return [self.fact(r,c,region,sl) for r in rids for c in columns]

    def claim(self,iid,statement,verdict,ids,rationale,predicate=None):
        entry={'interpretation_id':iid,'statement':statement,'expected_verdict':verdict,'fact_ids':list(dict.fromkeys(ids)),
               'rationale':rationale,'basis_type':'computable_reference' if predicate else 'audited_evidence_boundary'}
        if predicate:entry['predicate']=predicate
        self.r['interpretations'].append(entry)
        return iid

    def slot(self,sid,tid,focus,ids,claims):
        self.r['task_slots'].append({'slot_id':sid,'target_task_id':tid,'focus':focus,
                                   'measurement_ids':list(dict.fromkeys(ids)),'interpretation_ids':claims})


def atom(fid, relation, value=None, other=None):
    return {'fact_id':fid,'relation':relation,**({'other_fact_id':other} if other else {'value':value})}


def all_of(*items):return {'all':list(items)}


def predicate_value(rule, values):
    if 'all' in rule:return all(predicate_value(x,values) for x in rule['all'])
    a=values[rule['fact_id']];b=values[rule['other_fact_id']] if 'other_fact_id' in rule else rule['value']
    return {'gt':lambda:a>b,'lt':lambda:a<b,'eq':lambda:a==b,'ne':lambda:a!=b}[rule['relation']]()


def build_all(curator):
    c=curator;ch=c.channels;normal='2024.9.18_normal'
    source_a,source_b='Load1_open circuit','PDM1_open circuit or short circuit'
    rec=[c.record(source_a,1,'A1','A'),c.record(source_a,2,'A2','A'),c.record(source_b,1,'B1','B'),c.record(source_b,2,'B2','B'),c.record(normal,1,'R1','R')]
    branch=Recipe('M_branch_002','局部负载与供电支路的观测差异',rec,ch,[source_a,source_b,normal])
    x=branch
    # Slot 1: distinguish inactive control phase from changed response under the same named stage.
    f=x.stats(['R1','A1','A2'],['I_Load1','U_Load1'])+x.stats(['R1','A2'],['I_Load1'],region='idle_phase')
    r1=x.claim('L_response','A2在load1_phase末段的I_Load1中位数低于0.01 A，而A1和R1均大于1 A。','supported',f,
        'Compare matching named-stage measurements and an inactive-phase control; nominal schedule alone is not measured activation.',
        all_of(atom(f[4],'lt',.01),atom(f[2],'gt',1),atom(f[0],'gt',1)))
    r2=x.claim('L_command','这些电流差异足以证明某条指令已发送且执行失败。','insufficient',f,
        'No independent dispatch/acknowledgement log; supplied context provenance is unresolved.')
    x.slot('L_phase','T04','用正常停用阶段与名义启用阶段作对照，判断现象是否只由取错阶段解释；约束指令结论。',f,[r1,r2])
    f=x.stats(['A2','B2','R1'],['U_Load1','I_Load1','U_Bus'])
    r1=x.claim('L_voltage','A2与B2的I_Load1末段中位数均低于0.01 A，但A2的U_Load1中位数大于1 V，B2则低于1 V。','supported',f,
        'Similar current absence has different measured voltage signatures. This does not by itself fix a physical device topology.',
        all_of(atom(f[1],'lt',.01),atom(f[4],'lt',.01),atom(f[0],'gt',1),atom(f[3],'lt',1)))
    r2=x.claim('L_unique','仅凭这些窗口的电压和电流，就能唯一确定两个记录各自的具体元器件故障机理。','insufficient',f,
        'Allow observable localization, but exact wiring, sensor placement and intervention evidence are missing.')
    x.slot('L_localize','T05','比较相似低电流现象背后的电压证据；判断能定位到什么观测范围，以及什么仍不能唯一确定。',f,[r1,r2])
    f=x.stats(['A2','B2','R1'],['I_Load1','U_Bus'])+x.stats(['A2','B2','R1'],['I_Load2'],region='load2_phase')+x.stats(['A2','B2','R1'],['I_Load3'],region='load3_phase')
    r1=x.claim('L_scope','A2和B2在load2_phase末段的I_Load2中位数及load3_phase末段的I_Load3中位数均大于1 A。','supported',f,
        'Compare each branch in its own planned activity phase; simultaneous current comparisons across different load schedules are misleading.',
        all_of(atom(f[6],'gt',1),atom(f[7],'gt',1),atom(f[9],'gt',1),atom(f[10],'gt',1)))
    r2=x.claim('L_global','因为A2和B2的Load1电流较低，就可以推断整套系统的所有负载均失去供电。','refuted',f,
        'Other measured load branches remain active in their corresponding phases; the evidence contradicts an all-load loss.')
    x.slot('L_extent','T06','通过其他支路各自的工作阶段核查影响范围，避免把局部观测扩大成全系统结论。',f,[r1,r2])

    source_a,source_b='BAT_open circuit','BAT_degradation'
    rec=[c.record(source_a,1,'A1','A'),c.record(source_a,2,'A2','A'),c.record(source_b,1,'B1','B'),c.record(normal,1,'R1','R')]
    battery=Recipe('M_battery_003','电池电流分担与参考条件',rec,ch,[source_a,source_b,normal]);x=battery
    cols=['I_BAT2','I_BAT3','I_BAT4','I_Load2','U_Bus']
    f=x.stats(['A1','A2'],cols,region='load2_phase')
    r1=x.claim('B_redistribution','从A1到A2，load2_phase末段I_BAT2中位数降低，I_BAT3和I_BAT4中位数均提高。','supported',f,
        'Describe redistribution among three observed currents under the documented discharge sign convention.',
        all_of(atom(f[5],'lt',other=f[0]),atom(f[6],'gt',other=f[1]),atom(f[7],'gt',other=f[2])))
    r2=x.claim('B_all_energy','这三路电池电流和这些末段窗口足以计算整套系统的完整电池能量收支。','insufficient',f,
        'Only three of the storage groups are observed; instantaneous/median current is not total energy over an interval.')
    x.slot('B_share','T07','联合负载与母线测量比较同源周期的电流分担变化，明确当前测量可以支持的供电解释。',f,[r1,r2])
    f=x.stats(['A2','B1','R1'],cols,region='load2_phase')
    r1=x.claim('B_similarity','A2和B1在load2_phase末段的I_BAT2中位数均低于0.01 A，R1则大于0.1 A。','supported',f,
        'Identify a shared measured phenotype, not an identical physical cause.',
        all_of(atom(f[0],'lt',.01),atom(f[5],'lt',.01),atom(f[10],'gt',.1)))
    r2=x.claim('B_cause','两段记录出现相似的低I_BAT2测量，就足以证明它们具有完全相同的物理根因。','insufficient',f,
        'Different unobserved device/measurement/connection conditions can share this steady-state signature.')
    x.slot('B_ambiguity','T08','比较两个来源中的相似表型与参考记录，判断相似性对根因推断究竟有多大约束。',f,[r1,r2])
    f=x.stats(['B1','R1'],['I_BAT2','I_BAT3','I_BAT4','I_Load2'],region='load2_phase')
    r1=x.claim('B_working','B1在load2_phase末段I_Load2中位数大于1 A，I_BAT3和I_BAT4中位数均为正。','supported',f,
        'A persistently small measured current in one battery group need not mean the measured load is inactive.',
        all_of(atom(f[3],'gt',1),atom(f[1],'gt',0),atom(f[2],'gt',0)))
    r2=x.claim('B_degradation','只有B1的这个周期及跨来源参考R1，也足以恢复B所属实验在此之前的连续退化速度。','insufficient',f,
        'No earlier within-source baseline or longitudinal ageing trajectory is included. Cross-source difference does not create a within-source history.')
    x.slot('B_history','T09','在缺少同源前序记录时评估可以确认的状态和无法重建的历史；检查参考条件与推断边界。',f,[r1,r2])

    source='BCR_short circuit'
    rec=[c.record(source,1,'Q1','Q',whole=True),c.record(normal,1,'R1','R',whole=True)]
    quality=Recipe('M_quality_004','时间冲突、全零段与分析有效性',rec,ch,[source,normal]);x=quality
    x.r['public_background']=[p for p in COMMON if not p.startswith('cycle内')]+[
        '本组每个record保留完整源记录。early_segment取本记录起点起[0,11400)秒，late_segment取[11400,记录结束]；这只是固定分段，不预先解释其原因。',
        'quality的duplicate_extra_rows数的是超过唯一时间戳数量的记录数；conflicting_timestamp_groups数的是同时间戳下存在不同通道值的组数。',
        'longest_zero_run只检查声明的33个遥测通道，排除4个工况字段；返回最长连续记录段的条数、原始行范围及起始经过秒数。']
    f=[x.fact(r,region='early_segment',sl='all',op='quality',metric=m) for r in ['Q1','R1'] for m in ['duplicate_extra_rows','conflicting_timestamp_groups','conflict_channel_count']]
    r1=x.claim('Q_conflict','Q1的early_segment存在同一时间戳下通道值不同的记录组，R1的early_segment没有这类冲突组。','supported',f,
        'Timestamp repetition and conflicting observations are separate counts.',all_of(atom(f[1],'gt',0),atom(f[4],'eq',0)))
    r2=x.claim('Q_dedup','在确认这些冲突记录代表什么之前，任意删除同时间戳记录中的一条都不会影响信息。','refuted',f,
        'Conflicting values mean arbitrary deduplication can discard different measurements; no adjudicating source-order rule is supplied.')
    x.slot('Q_duplicates','T10','区分重复时间戳与冲突数值，识别受影响通道，并解释为什么不能默默去重。',f,[r1,r2])
    tele=[k for k in ch if k not in ['Irradiation','Temperature','Incidence_Angle','Load_Signal']]
    f=[x.fact(r,region='full_record',sl='all',op='longest_zero_run',channels=tele) for r in ['Q1','R1']]
    f += [x.fact('Q1',region=rg,sl='all',op='quality',metric=m) for rg in ['early_segment','late_segment'] for m in ['duplicate_extra_rows','gaps_gt_1s','rows']]
    r1=x.claim('Q_zero','Q1的最长33通道全零连续记录段比R1更长。','supported',f,
        'Exact-zero run scope includes temperatures and all observed electrical channels but excludes supplied condition fields.',atom(f[0],'gt',other=f[1]))
    r2=x.claim('Q_shutdown','全零遥测段本身足以证明实际设备在对应时段已全部物理断电。','insufficient',f,
        'Record-level zeros alone do not distinguish physical state, recording failure, merge/fill logic or missing measurements.')
    x.slot('Q_zero_tail','T11','定位并量化全零记录段，结合采样节奏变化评估其分析含义；严守记录现象与物理停机的边界。',f,[r1,r2])
    f=[x.fact('Q1',region=rg,sl='all',op='quality',metric=m) for rg in ['early_segment','late_segment'] for m in ['duplicate_extra_rows','conflicting_timestamp_groups','gaps_gt_1s','max_gap_s']]
    f += [x.fact('Q1',region='late_segment',sl='all',op='longest_zero_run',channels=tele)]
    r1=x.claim('Q_time_axis','Q1的late_segment没有重复时间戳，也没有大于1秒的相邻时间间隔。','supported',f,
        'This describes a regular recorded clock, not valid physical measurements.',all_of(atom(f[4],'eq',0),atom(f[6],'eq',0)))
    r2=x.claim('Q_validity','由于late_segment的时间轴规则，就可以直接把其中的全零序列当作可靠的物理故障响应轨迹。','insufficient',f,
        'A valid recorded time axis is necessary for temporal calculations but does not establish sensor/recording validity.')
    x.slot('Q_usable','T12','分别评估前后分段适合哪些分析，识别时间轴规则与测量可信度是不同条件。',f,[r1,r2])

    source_a,source_b='Bus_open circuit','Bus_short circuit'
    rec=[c.record(source_a,1,'A1','A'),c.record(source_a,2,'A2','A'),c.record(source_b,1,'B1','B'),c.record(source_b,2,'B2','B'),c.record(normal,1,'R1','R')]
    bus=Recipe('M_bus_005','母线响应范围、时间定位与根因边界',rec,ch,[source_a,source_b,normal]);x=bus
    x.r['public_background'].append('boundary为所选周期前40秒。对A2、B2，把该周期第一条记录的时间定义为比较标记t=0；该标记不是已核实的物理故障发生时刻或指令时刻。')
    f=x.stats(['A1','A2','R1'],['U_Bus','U_Load1','I_Load1','P_SA','P_BCR'],region='load1_phase')
    r1=x.claim('U_scope','A2在load1_phase末段的U_Bus和U_Load1中位数均小于0.01 V，I_Load1中位数小于0.01 A，而P_SA和P_BCR中位数均大于0 W。','supported',f,
        'Electrical channels use their individually documented units. Distinguish simultaneous downstream low signals from all-channel-zero records.',
        all_of(atom(f[5],'lt',.01),atom(f[6],'lt',.01),atom(f[7],'lt',.01),atom(f[8],'gt',0),atom(f[9],'gt',0)))
    r2=x.claim('U_entire','这些母线及负载的低测量值证明整个观测系统的所有通道都已经变成零。','refuted',f,
        'Other observed output channels remain nonzero; scope of measured loss must not be overextended.')
    x.slot('U_extent','T13','结合前序周期和参考记录确定测量变化范围，检查是否属于所有通道同时消失。',f,[r1,r2])
    f=x.stats(['A2','B2','R1'],['U_Bus','U_Load1','I_Load1','P_SA','P_BCR'],region='load1_phase')
    r1=x.claim('U_similarity','A2和B2在load1_phase末段的U_Bus和U_Load1中位数均小于0.01 V，I_Load1中位数均小于0.01 A。','supported',f,
        'Shared downstream signature is observable; upstream values may differ without forming a universal diagnostic rule.',
        all_of(*[atom(f[i],'lt',.01) for i in [0,1,2,5,6,7]]))
    r2=x.claim('U_root','仅凭这两段稳态窗口，能够形成可泛化到其他实验的唯一具体故障机理判别规则。','insufficient',f,
        'Only one source experiment for each measured pattern; unobserved transients, topology and interventions are not available.')
    x.slot('U_distinguish','T14','比较相似的母线及负载表现与其他通道差异，评估现有证据能否形成唯一且可泛化的原因判别。',f,[r1,r2])
    f=[]
    for rid in ['A2','B2']:
        f.append(x.fact(rid,'U_Bus',region='boundary',sl='all',op='first_sustained',threshold=1,direction='below'))
        f.append(x.fact(rid,'I_Bus',region='boundary',sl='all',stat='max'))
        f.append(x.fact(rid,region='boundary',sl='all',op='quality',metric='duplicate_extra_rows'))
    r1=x.claim('U_timing','在所定义的boundary窗口中，A2的首次持续U_Bus低于1 V时刻比B2更晚。','supported',f,
        'Report elapsed measured time relative to each record marker, not unsampled physical failure time.',atom(f[0],'gt',other=f[3]))
    r2=x.claim('U_transient','如果boundary内I_Bus的已采样最大值没有超过3 A，就能排除期间曾发生任何更快的大电流瞬态。','insufficient',f,
        'A roughly 1 Hz recorded maximum cannot exclude an event between samples; no high-speed protection log is supplied.')
    x.slot('U_onset','T15','定位可观测的电压变化时刻，区分记录标记和物理起点，并评估采样分辨率对瞬态排除的限制。',f,[r1,r2])
    return {'branch':branch.r,'battery':battery.r,'quality':quality.r,'bus':bus.r}


def main(data_root,catalog,channel_recipe,out):
    ch=json.loads(channel_recipe.read_text())['channels']
    recipes=build_all(Curator(data_root,catalog,ch));cases=[];checks=[]
    for name,recipe in recipes.items():
        path=out/(name+'.private.json');write_json(path,recipe)
        material,_=build_material(path,out/'prepared'/name)
        values={f['fact_id']:f['result']['value'] for f in material['facts']}
        for rule in material['interpretations']:
            if 'predicate' in rule:
                verdict='supported' if predicate_value(rule['predicate'],values) else 'refuted'
                if verdict != rule['expected_verdict']:
                    raise ValueError('Audited claim does not match current raw facts: '+rule['interpretation_id'])
        checks.append({'case_id':name,'records':len(recipe['records']),'facts':len(recipe['facts']),'slots':len(recipe['task_slots'])})
        cases.append({'case_id':name,'recipe_path':path.name})
    write_json(out/'batch.private.json',{'schema_version':'0.2','cases':cases})
    write_json(out/'preparation_summary.json',{'cases':checks,'public_questions_authored_by_this_script':0})
    print(json.dumps(checks,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--catalog',type=Path,required=True)
    p.add_argument('--channel-recipe',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();main(a.data_root,a.catalog,a.channel_recipe,a.out)
