"""Independent pandas recomputation from CSVs, without the material query engine."""
import argparse
import json
import math
from pathlib import Path
import pandas as pd
from hangtian.data import digest, file_hash, write_json


def predicate(rule, values):
    if 'all' in rule:
        return all(predicate(r, values) for r in rule['all'])
    a = values[rule['fact_id']]
    b = values[rule['other_fact_id']] if 'other_fact_id' in rule else rule['value']
    return {'gt': lambda: a > b, 'lt': lambda: a < b, 'eq': lambda: a == b, 'ne': lambda: a != b}[rule['relation']]()


def check(case_dir):
    material = json.loads((case_dir / 'private/material.json').read_text(encoding='utf-8'))
    records = json.loads((case_dir / 'private/records.json').read_text(encoding='utf-8'))
    frames, clocks, sources, checks = {}, {}, {}, []
    for source in material['provenance']:
        rid = source['record_id']; sources[rid] = source
        frames_raw = []
        for kind in ['telemetry', 'context']:
            path = Path(source[kind + '_path'])
            if file_hash(path) != source['source_hashes'][kind]:
                raise ValueError('Raw hash mismatch')
            frames_raw.append(pd.read_csv(path))
        tele, ctx = frames_raw
        if not tele.Time.equals(ctx.Time):
            raise ValueError('Raw context alignment mismatch')
        merged = pd.concat([tele, ctx.drop(columns='Time')], axis=1)
        merged = merged[list(material['channels'])].astype(float)
        frames[rid] = merged
        times = pd.to_datetime(tele.Time)
        a, b = source['source_rows']
        clocks[rid] = (times - times.iloc[a]).dt.total_seconds()
        expected = merged.iloc[a:b]
        ok = records[rid]['time_s'] == clocks[rid].iloc[a:b].tolist() and all(
            records[rid]['channels'][c] == expected[c].tolist() for c in material['channels'])
        checks.append({'kind': 'entire_record_copy', 'record_id': rid, 'pass': ok, 'rows': b-a})
    values = {}
    quality_cache = {}
    for f in material['facts']:
        q = f['query']; rid = q['record_id']
        bounds = {'full_record': sources[rid]['source_rows'], **sources[rid]['regions']}
        a, b = bounds[q['region']]; base_a = a
        if q['slice'] == 'last60s':
            a = int(clocks[rid].iloc[a:b][clocks[rid].iloc[a:b] >= clocks[rid].iloc[b-1]-59].index[0])
        elif q['slice'] != 'all':
            raise ValueError('Unsupported independent slice')
        frame = frames[rid].iloc[a:b]; times = clocks[rid].iloc[a:b]
        cache_key = (rid, a, b)
        if cache_key not in quality_cache:
            grouped = frame.groupby(times, sort=False).nunique(dropna=False)
            changes = grouped.gt(1)
            conflict_channels = changes.columns[changes.any()].tolist()
            delta = times.diff().dropna()
            quality_cache[cache_key] = {'rows': b-a, 'duplicate_extra_rows': int(times.duplicated().sum()),
                'conflicting_timestamp_groups': int(changes.any(axis=1).sum()),
                'conflict_channel_count': len(conflict_channels), 'conflict_channels': sorted(conflict_channels),
                'time_reversals': int((delta < 0).sum()), 'gaps_gt_1s': int((delta > 1).sum()),
                'max_gap_s': float(delta.max()) if len(delta) else 0,
                'elapsed_span_s': float(times.iloc[-1]-times.iloc[0])}
        qual = quality_cache[cache_key]
        extra = {}
        if q['op'] == 'stat':
            value = float(getattr(frame[q['channel']], q['stat'])())
        elif q['op'] == 'quality':
            value = qual[q.get('metric', 'duplicate_extra_rows')]
        elif q['op'] == 'first_sustained':
            if not (times.diff().dropna() > 0).all():
                raise ValueError('Onset on non-increasing timestamps')
            mask = frame[q['channel']] < q['threshold'] if q.get('direction') == 'below' else frame[q['channel']] > q['threshold']
            ends = mask.rolling(q['min_records']).sum().eq(q['min_records'])
            start = int(ends[ends].index[0])-q['min_records']+1 if ends.any() else None
            value = None if start is None else float(clocks[rid].iloc[start]-clocks[rid].iloc[base_a])
            extra = {'onset_source_row': start}
        elif q['op'] == 'longest_zero_run':
            mask = frame[q['channels']].eq(0).all(axis=1)
            groups = (mask != mask.shift()).cumsum()
            runs = mask[mask].groupby(groups[mask], sort=False).agg(['size'])
            if runs.empty:
                value = 0; extra = {'run_source_rows': None, 'run_start_offset_s': None}
            else:
                selected = groups[groups.eq(runs['size'].idxmax())].index
                lo, hi = int(selected[0]), int(selected[-1])+1
                value = hi-lo
                extra = {'run_source_rows': [lo, hi], 'run_start_offset_s': float(clocks[rid].iloc[lo]-clocks[rid].iloc[base_a])}
        else:
            raise ValueError('Unsupported independent operation')
        expected = f['result']; values[f['fact_id']] = value
        same = (value is None and expected['value'] is None) or (
            value is not None and expected['value'] is not None and math.isclose(value, expected['value'], rel_tol=0, abs_tol=1e-6))
        ok = same and qual == expected['quality'] and expected['source_rows'] == [a,b] and all(expected[k] == v for k,v in extra.items())
        checks.append({'kind': 'raw_fact', 'fact_id': f['fact_id'], 'pass': ok, 'independent_value': value})
    for r in material['interpretations']:
        if 'predicate' in r:
            result = 'supported' if predicate(r['predicate'], values) else 'refuted'
            checks.append({'kind': 'computable_interpretation', 'interpretation_id': r['interpretation_id'], 'pass': result == r['expected_verdict']})
    report = {'material_sha256': digest(material), 'records_sha256': digest(records), 'all_passed': all(c['pass'] for c in checks),
        'implementation': 'Independent pandas CSV read/aggregation; does not call material execute/build functions.',
        'checks': checks, 'epistemic_references': 'Require assistant review; numerical checks do not establish physical causes.'}
    write_json(case_dir / 'independent_material_validation.json', report)
    return {'case': case_dir.name, 'checks': len(checks), 'all_passed': report['all_passed'], 'failed': [c for c in checks if not c['pass']]}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run-dir', type=Path, required=True)
    a = p.parse_args()
    results = [check(d) for d in sorted(a.run_dir.iterdir()) if (d / 'private/material.json').exists()]
    print(json.dumps(results, ensure_ascii=False)); raise SystemExit(0 if results and all(r['all_passed'] for r in results) else 2)
