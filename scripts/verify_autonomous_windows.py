"""Pandas oracle for free-window tools on saved, previously raw-verified records."""
import argparse
import math
from pathlib import Path
import pandas as pd

from hangtian.autonomous import run_query
from hangtian.data import DataError, file_hash, write_json
from hangtian.materials import read_json


def check(manifest_path, out):
    report = {'verification_scope':'Saved material records; not a fresh independent acquisition or agent solve.',
              'checks':[], 'record_hashes':{}}
    for case in read_json(manifest_path)['cases']:
        source = Path(case['source_case_dir']); material = read_json(source/'private/material.json')
        records = read_json(source/'private/records.json')
        report['record_hashes'][case['case_id']] = file_hash(source/'private/records.json')
        for fact in material['facts']:
            original = fact['query']; record = records[original['record_id']]
            start,stop = fact['result']['source_rows']; a,b=start-record['row_origin'],stop-record['row_origin']
            q = {k:v for k,v in original.items() if k not in ('region','slice')}
            q.update(start_row=start,stop_row=stop)
            if q['op']=='first_sustained':q.setdefault('direction','above')
            if q['op']=='quality':q.setdefault('metric','duplicate_extra_rows')
            actual = run_query(records,q)['value']
            frame = pd.DataFrame({k:v[a:b] for k,v in record['channels'].items()})
            times = pd.Series(record['time_s'][a:b])
            if q['op']=='stat':
                s=frame[q['channel']];expected=getattr(s,q['stat'])()
            elif q['op']=='first_sustained':
                hit = (frame[q['channel']] > q['threshold'] if q['direction']=='above'
                       else frame[q['channel']] < q['threshold'])
                ends=hit.rolling(q['min_records']).sum().eq(q['min_records'])
                locations=ends[ends].index
                expected=None if len(locations)==0 else float(times.iloc[locations[0]-q['min_records']+1]-times.iloc[0])
            elif q['op']=='longest_zero_run':
                zeros=frame[q['channels']].eq(0).all(axis=1)
                sizes=zeros.groupby(zeros.ne(zeros.shift()).cumsum()).sum()
                expected=int(sizes.max()) if len(sizes) else 0
            else:
                frame['_time']=times
                conflicts=frame.groupby('_time',sort=False).nunique(dropna=False).gt(1)
                values={'rows':len(times),'duplicate_extra_rows':int(times.duplicated().sum()),
                    'conflicting_timestamp_groups':int(conflicts.any(axis=1).sum()),
                    'conflict_channel_count':int(conflicts.any(axis=0).sum()),
                    'time_reversals':int(times.diff().lt(0).sum()),'gaps_gt_1s':int(times.diff().gt(1).sum()),
                    'max_gap_s':float(times.diff().max()) if len(times)>1 else 0.,
                    'elapsed_span_s':float(times.iloc[-1]-times.iloc[0])}
                expected=values[q['metric']]
            passed=(actual is None and expected is None) or (actual is not None and expected is not None and
                      math.isclose(float(actual),float(expected),abs_tol=1e-9,rel_tol=1e-9))
            report['checks'].append({'case_id':case['case_id'],'fact_id':fact['fact_id'],'pass':bool(passed)})
    report['passed']=all(c['pass'] for c in report['checks']);report['check_count']=len(report['checks'])
    write_json(out,report)
    print({'passed':report['passed'],'check_count':report['check_count']},flush=True)
    if not report['passed']:raise DataError('Free-window oracle mismatch')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();check(a.manifest,a.out)
