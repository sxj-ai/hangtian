"""Evidence-backed expansion recipes. This program authors NO public questions."""
import argparse
from pathlib import Path
from prepare_expansion_materials import Curator, Recipe
from hangtian.data import write_json, file_hash
from hangtian.materials import build_material, read_json


def plans(source):
    """Private assessment goals; reusable generator must not expose the route."""
    if source.startswith(('Load', 'PDM')):
        n = source[4] if source.startswith('Load') else source[3]
        own = [f'U_Load{n}', f'I_Load{n}', f'P_Load{n}']
        other = [f'I_Load{i}' for i in '123' if i != n]
        return [
            (f'Assess whether Load{n} in A3 and A4 can be represented by the same observed operating-state description. Later-cycle repeatability, not initial fault diagnosis.', own),
            (f'Determine the dependence of Load{n} observed voltage/current behavior on operating phase in A4. Distinguish inactive phases from measured availability, without granting any observed pattern.', own + ['U_Bus']),
            (f'Assess operating availability of the OTHER two load branches in A3/A4. A data-dependent service scope, not a claim of universal health.', other + ['U_Bus']),
            (f'Characterize how solar/BCR output in A4 responds across the documented operating conditions; evaluate what this says about the upstream measured response.', ['P_SA','P_BCR','U_Bus','I_BAT2']),
            (f'Assess whether reference series R is an appropriate quantitative baseline for Load{n} in A1, and identify the scope of a defensible comparison.', own + ['U_Bus','Irradiation','Temperature']),
        ]
    if source.startswith('BAT'):
        return [
            ('Assess whether the observed battery-current sharing in A3 is reproduced in A4; report degree of consistency without treating cycles as independent experiments.', ['I_BAT2','I_BAT3','I_BAT4']),
            ('Characterize how the measured battery groups participate across operating phases in A4. Positive current follows the documented discharge convention; do not infer complete energy accounting.', ['I_BAT2','I_BAT3','I_BAT4','U_Bus']),
            ('Assess whether the observed battery-voltage behavior distinguishes the three measured groups in A3/A4. Do not infer capacity or remaining life.', ['U_BAT2','U_BAT3','U_BAT4']),
            ('Evaluate suitability of series R as a quantitative reference for battery operation in A1. Require actual condition and response evidence, not generic methodological caution.', ['I_BAT2','I_BAT3','I_BAT4','I_Load2','U_Bus','Irradiation']),
            ('Assess load service across A1 through A4, including whether any measured load availability changes through this experiment.', ['I_Load1','I_Load2','I_Load3','U_Bus']),
        ]
    if source == 'BCR_short circuit':
        return [
            ('Assess what changes in measured supply behavior between A1 and A2, limiting this investigation to the first two cycles.', ['P_SA','P_BCR','U_Bus','I_Bus']),
            ('Assess the usability of A2 for comparing measured load operation with reference series R. This is a data fitness question about the second cycle, not whole-source deduplication.', ['I_Load1','I_Load2','I_Load3','U_Bus']),
            ('Assess the substantive information A3 and A4 contain for judging electrical operating state. Base information value on measurements rather than catalog identity; do not equate recorded zeros with physical shutdown.', ['P_SA','P_BCR','U_Bus','I_Load1','I_BAT2']),
            ('Characterize battery participation during A1 and A2 and how much of the observed load service it can explain.', ['I_BAT2','I_BAT3','I_BAT4','I_Load1','I_Load2','I_Load3']),
            ('Assess whether a single representative cycle can summarize all four A cycles for an operational status report. Base representativeness on measured intercycle variation, not a data cleaning procedure.', ['P_SA','P_BCR','U_Bus','I_Load1','I_Load2','I_Load3']),
        ]
    if source.startswith('BCR'):
        return [
            ('Characterize how the joint measured solar/BCR power behavior evolves through A1 to A4. Describe measured relations; no unverified efficiency/loss topology.', ['P_SA','P_BCR','U_Bus']),
            ('Assess the dependence of BCR-related measured supply behavior on operating phase in A4.', ['P_BCR','U_BCR','I_BCR','U_Bus']),
            ('Determine load service scope in A3/A4 compared with the earlier A records. Distinguish measured branch availability from physical component causes.', ['I_Load1','I_Load2','I_Load3','U_Bus']),
            ('Assess how the measured battery groups participate in sustaining operation in A4.', ['I_BAT2','I_BAT3','I_BAT4','I_Load1','I_Load2','I_Load3']),
            ('Evaluate whether series R provides a suitable quantitative baseline for BCR output in A4. Require actual comparable conditions and measured discrepancies.', ['P_BCR','P_SA','U_Bus','Irradiation','I_Load1']),
        ]
    if source.startswith('Bus'):
        return [
            ('Assess repeatability of observed bus and load behavior between A3 and A4, without assuming a shared physical failure mechanism.', ['U_Bus','I_Bus','I_Load1','I_Load2','I_Load3']),
            ('Characterize solar/BCR measured output across operating phases in A4, and what range of upstream behavior is actually observed.', ['P_SA','P_BCR','U_BCR','Irradiation']),
            ('Assess the observed battery-group state in A4. Distinguish measured battery participation from bus/load service.', ['I_BAT2','I_BAT3','I_BAT4','U_BAT2','U_Bus']),
            ('Determine how the relationship of bus and load measurements varies with operating phase in A3. Do not infer wiring or unmeasured leakage pathways.', ['U_Bus','I_Bus','U_Load1','I_Load1','I_Load2','I_Load3']),
            ('Determine whether one cycle can represent bus operational behavior throughout A1 to A4. Describe time evolution over recorded cycles, not an exact physical onset.', ['U_Bus','I_Bus','P_Bus','I_Load1']),
        ]
    return [
        ('Assess whether solar output behavior in A3 is reproduced in A4, accounting for actual documented operating context.', ['P_SA','U_SA','I_SA','Irradiation','I_Load1']),
        ('Characterize solar output dependence on operating phase in A4. Do not grant that a low-output episode is abnormal.', ['P_SA','U_SA','I_SA','Irradiation','Incidence_Angle']),
        ('Assess the association of solar output and measured battery participation in A4, with bounded observed load context; do not infer complete power balance.', ['P_SA','I_BAT2','I_BAT3','I_BAT4','I_Load1','I_Load2']),
        ('Evaluate whether reference series R is quantitatively comparable to A4 for interpreting solar output. Require numerical evidence of conditions and response; do not prescribe the decisive comparison.', ['P_SA','I_Load1','Irradiation','Temperature','U_Bus']),
        ('Determine whether load service changes through A1 to A4, despite any variation in source-side output. The public question must not assert that such variation exists.', ['I_Load1','I_Load2','I_Load3','P_SA','U_Bus']),
    ]


def prepare(root, out, audit):
    channels = read_json(root/'private/inputs/solar_recipe.private.json')['channels']
    curator = Curator(Path('/home/xjshang/llm_datasets/XJTU-SPS'),
                      Path('/home/xjshang/xjtu_material_analysis_20261008_run01/catalog.json'), channels)
    previous = read_json(root/'runs/autonomous_tasks_final_001/private/manifest.json')
    context = previous['cases'][1]['public_context'] + [
        'A1至A4属于同一实验序列的连续四个周期。R1和R4属于另一实验序列的第1和第4周期；这些ID不表示健康类别。',
        'time_s相对于各记录首条时间戳；source行号用于定位，不能当作经过秒数。跨记录时间不是统一的绝对时钟。']
    cases = []
    checks = []
    for index, evidence in enumerate(read_json(audit)):
        name = evidence['source']; cid = f'pack_{index+1:02d}'
        destination = out/'materials'/cid
        records = [curator.record(name, c, f'A{c}', f'S{index+1:02d}') for c in range(1,5)]
        records += [curator.record('2024.9.18_normal', c, f'R{c}', 'REF09') for c in [1,4]]
        recipe = Recipe('M100_'+cid, '周期行为与参考适用性材料', records, channels, [name,'2024.9.18_normal'])
        recipe.r['limitations'].append(evidence['allowed_use_and_limit'])
        targets = {}
        for j, (focus, cols) in enumerate(plans(name)):
            sid, tid = f'G{j+1}', f'T{16+index*5+j:02d}'
            ids = []
            for region in ['load3_phase','load1_phase','load2_phase']:
                ids += recipe.stats(['A1','A2','A3','A4','R1','R4'], cols, region=region)
            for rid in ['A1','A2','A3','A4','R1','R4']:
                ids += [recipe.fact(rid, region='full_record', sl='all', op='quality', metric=m)
                        for m in ['duplicate_extra_rows','gaps_gt_1s']]
            # Phase summaries are anchors, never an exclusive answer path or proof of all samples.
            recipe.slot(sid, tid, focus, ids, [])
            targets[sid] = tid
        path = destination/'private/recipe.json'
        write_json(path, recipe.r)
        material, arrays = build_material(path, destination)
        # Independently reread raw CSV using pandas (engine uses csv+statistics).
        import pandas as pd
        import math
        for fact in material['facts']:
            if fact['query']['op'] != 'stat':
                continue
            q = fact['query']; spec = next(r for r in records if r['record_id']==q['record_id'])
            key = spec['telemetry_path']
            if key not in curator.cache_raw_verify:
                frame = pd.read_csv(key)
                aux = pd.read_csv(spec['context_path'])
                if not frame.Time.equals(aux.Time): raise ValueError('Raw time alignment changed')
                curator.cache_raw_verify[key] = pd.concat([frame,aux.drop(columns='Time')],axis=1)
            frame = curator.cache_raw_verify[key]
            a,b = fact['result']['source_rows']
            value = float(frame[q['channel']].iloc[a:b].median())
            ok = math.isclose(value, fact['result']['value'], rel_tol=1e-9, abs_tol=1e-9)
            checks.append({'case_id':cid,'fact_id':fact['fact_id'],'pass':ok})
            if not ok: raise ValueError('Independent raw median mismatch')
        cases.append({'case_id':cid,'source_case_dir':str(destination),'targets':targets,
                      'public_context':context,'private_source':name,
                      'lineage_group':records[0]['lineage_group'],
                      'records_file_sha256':file_hash(destination/'private/records.json')})
        write_json(out/'private/manifest.json', {'schema_version':'autonomous-0.1','cases':cases})
        print({'material':cid,'facts':len(material['facts']),'tasks':5},flush=True)
    write_json(out/'independent_raw_verification.private.json',
               {'passed':all(x['pass'] for x in checks),'check_count':len(checks),'checks':checks,
                'scope':'Fresh pandas reads versus csv/statistics reference medians; not agent solvability.'})


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--audit',type=Path,required=True)
    a=p.parse_args();Curator.cache_raw_verify={};prepare(a.root,a.out,a.audit)
