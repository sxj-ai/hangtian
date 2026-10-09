"""Independently check executed observations with pandas; never grade prose."""
import argparse
import math
from pathlib import Path
import pandas as pd
from hangtian.data import write_json
from hangtian.materials import read_json
from hangtian.pi_bridge import approved_task


def close(a, b):
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), abs_tol=1e-9, rel_tol=1e-9)


def verify(record, obs):
    q, result = obs['query'], obs['result']
    origin = record['row_origin']
    start, stop = q['start_row'], q['stop_row']
    a, b = start-origin, stop-origin
    frame = pd.DataFrame({k: v[a:b] for k, v in record['channels'].items()})
    times = pd.Series(record['time_s'][a:b])
    checks = []
    if q['op'] == 'read':
        n = min(512, b-a)
        checks += [result['time_s'] == times.iloc[:n].tolist(), result['source_rows'] == [start, start+n],
                   result['next_start_row'] == (start+n if n < b-a else None), result['requested_stop_row'] == stop]
        checks += [result['channels'][c] == frame[c].iloc[:n].tolist() for c in q['channels']]
    elif q['op'] == 'profile':
        bins = result['bins']; count = min(q['bins'], len(frame))
        checks.append(len(bins) == count)
        for i, item in enumerate(bins):
            lo, hi = len(frame)*i//count, len(frame)*(i+1)//count
            checks += [item['source_rows'] == [start+lo, start+hi], item['count'] == hi-lo,
                       item['first_time_s'] == times.iloc[lo], item['last_time_s'] == times.iloc[hi-1]]
            for c in q['channels']:
                for name in ('min','max','mean'):
                    checks.append(close(item['channels'][c][name], getattr(frame[c].iloc[lo:hi], name)()))
    else:
        groups = frame.assign(_time=times).groupby('_time', sort=False).nunique(dropna=False).gt(1)
        quality = {'rows': len(times), 'duplicate_extra_rows': int(times.duplicated().sum()),
            'conflicting_timestamp_groups': int(groups.any(axis=1).sum()),
            'conflict_channel_count': int(groups.any(axis=0).sum()),
            'conflict_channels': sorted(groups.columns[groups.any(axis=0)].tolist()),
            'time_reversals': int(times.diff().lt(0).sum()), 'gaps_gt_1s': int(times.diff().gt(1).sum()),
            'max_gap_s': float(times.diff().max()) if len(times)>1 else 0.,
            'elapsed_span_s': float(times.iloc[-1]-times.iloc[0])}
        checks += [result['source_rows'] == [start, stop], result['quality'] == quality]
        if q['op'] == 'quality':
            expected = quality[q['metric']]
        elif q['op'] == 'stat':
            expected = getattr(frame[q['channel']], q['stat'])()
        elif q['op'] == 'first_sustained':
            hits = frame[q['channel']].gt(q['threshold']) if q['direction']=='above' else frame[q['channel']].lt(q['threshold'])
            ends = hits.rolling(q['min_records']).sum().eq(q['min_records'])
            candidates = ends[ends].index
            onset = None if len(candidates)==0 else int(candidates[0])-q['min_records']+1
            expected = None if onset is None else float(times.iloc[onset]-times.iloc[0])
            checks.append(result['onset_source_row'] == (None if onset is None else start+onset))
        else:
            hits = frame[q['channels']].eq(0).all(axis=1)
            group_ids = hits.ne(hits.shift()).cumsum()
            sizes = hits.groupby(group_ids).sum()
            expected = int(sizes.max())
            if expected:
                best = sizes.idxmax(); indices = hits.index[group_ids.eq(best)]
                checks += [result['run_source_rows'] == [start+int(indices[0]),start+int(indices[-1])+1],
                    close(result['run_start_offset_s'], times.iloc[indices[0]]-times.iloc[0])]
            else:
                checks += [result['run_source_rows'] is None, result['run_start_offset_s'] is None]
        checks.append(close(result['value'], expected))
    return {'observation_id': obs['observation_id'], 'op': q['op'],
            'passed': bool(all(checks)), 'field_checks': len(checks)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--batch', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    a = p.parse_args()
    checks = []
    for directory in sorted(a.run.glob('T*_tools')):
        path = directory / 'trajectory.json'
        if not path.exists(): continue
        trajectory = read_json(path)
        _, records, _ = approved_task(a.batch, trajectory['task_id'])
        for observation in trajectory['observations']:
            item = verify(records[observation['query']['record_id']], observation)
            checks.append({'task_id': trajectory['task_id'], **item})
    report = {'scope': 'Pandas recomputation of actual Agent-selected windows on audited saved record arrays; not independent physical acquisition or semantic grading.',
        'observations': len(checks), 'field_checks': sum(c['field_checks'] for c in checks),
        'passed': bool(checks) and all(c['passed'] for c in checks), 'checks': checks}
    write_json(a.run / 'independent_observation_verification.json', report)
    print({k:v for k,v in report.items() if k!='checks'})
    if not report['passed']: raise SystemExit(1)


if __name__ == '__main__': main()
