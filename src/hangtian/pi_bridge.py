"""Trusted JSONL tool service for Pi. Never evaluates model code or paths."""
import argparse
import json
import sys
from pathlib import Path

from .autonomous import InvestigationTools, review_gate, verify_evidence
from .contracts import schema, validate
from .data import DataError, digest, file_hash, write_json
from .materials import read_json


def approved_task(batch: Path, task_id: str):
    manifest = read_json(batch / 'private/manifest.json')
    matches = [c for c in manifest['cases'] if task_id in c['targets'].values()]
    if len(matches) != 1:
        raise DataError('Task not uniquely present in approved batch')
    case = matches[0]
    directory, source = batch / case['case_id'], Path(case['source_case_dir'])
    public = read_json(directory / 'public/tasks.json')
    material = read_json(source / 'private/material.json')
    saved = read_json(directory / 'private/candidate.json')
    review_gate(read_json(directory / 'private/autonomy_review.json'), saved['proposal'],
                public, material, read_json(directory / 'private/outcome_rubric.json'))
    records_hash = file_hash(source / 'private/records.json')
    if saved['identity']['records_file_sha256'] != records_hash:
        raise DataError('Audited record arrays changed')
    task = next(t for t in public if t['task_id'] == task_id)
    aggregate = read_json(batch / 'tasks.json')['tasks']
    if [t for t in aggregate if t['task_id'] == task_id] != [task]:
        raise DataError('Public export differs from reviewed task')
    records = read_json(source / 'private/records.json')
    permitted = {r['record_id'] for r in task['environment']['records']}
    return task, {k: v for k, v in records.items() if k in permitted}, records_hash


class Bridge:
    def __init__(self, task, records, out, *, mode='tools', max_calls=64):
        self.task, self.out, self.mode, self.max_calls = task, out, mode, max_calls
        self.tool = InvestigationTools(records)
        self.state = {'task_id': task['task_id'], 'mode': mode, 'status': 'running',
                      'answer': None, 'observations': self.tool.observations, 'errors': [],
                      'tool_attempts': 0}

    def seed_reporting_probe(self, prior):
        """Replay only evidence already selected in an unfinished baseline run."""
        if self.mode != 'report_only' or prior.get('task_id') != self.task['task_id']:
            raise DataError('Reporting probe task or mode mismatch')
        if prior.get('mode') != 'tools' or prior.get('answer') is not None:
            raise DataError('Reporting probe requires an unsubmitted tools baseline')
        replay = InvestigationTools(self.tool.records)
        for obs in prior['observations']:
            if digest(replay.call(obs['query'])) != digest(obs):
                raise DataError('Prior observation failed independent replay')
        self.tool = replay
        self.state['observations'] = replay.observations
        self.state['diagnostic_condition'] = 'prompted reporting from previously selected evidence; not autonomous completion'
        self.state['prior_trajectory_sha256'] = digest(prior)

    def save(self):
        write_json(self.out / 'trajectory.json', self.state)

    def handle(self, message):
        try:
            op = message.get('op')
            if op == 'init':
                result = {'task': self.task, 'query_schema': schema('autonomous_query'),
                          'answer_schema': schema('autonomous_answer')}
                if self.mode == 'report_only':
                    result['prior_observations'] = self.tool.observations
                return result
            if op == 'query':
                if self.mode != 'tools' or self.state['answer'] is not None:
                    raise DataError('Data tools unavailable in this condition')
                self.state['tool_attempts'] += 1
                if self.state['tool_attempts'] > self.max_calls:
                    raise DataError('Tool budget exhausted')
                return self.tool.call(message['query'])
            if op == 'submit':
                if self.mode not in ('tools', 'report_only') or self.state['answer'] is not None:
                    raise DataError('Submission unavailable')
                validate('autonomous_answer', message['answer'])
                probe = {'observations': self.tool.observations, 'answer': message['answer']}
                report = verify_evidence(probe, self.tool.records)
                if not report['evidence_integrity_pass']:
                    raise DataError('Submission contains invalid evidence citations')
                self.state.update(answer=message['answer'], status='submitted')
                return {'receipt': 'submitted', 'correctness': 'not_evaluated'}
            if op == 'finish':
                if self.state['answer'] is None:
                    self.state['status'] = 'no_structured_submission'
                report = verify_evidence(self.state, self.tool.records) if self.mode in ('tools', 'report_only') else {
                    'condition': 'no_data_probe', 'task_pass': None,
                    'note': 'Review content guessing separately; no-data citation failure is not evidence of difficulty.'}
                write_json(self.out / 'evidence_verification.json', report)
                return {'status': self.state['status'], 'observations': len(self.tool.observations)}
            raise DataError('Unknown service operation')
        except (DataError, KeyError, TypeError, ValueError) as error:
            text = str(error) if isinstance(error, DataError) else 'Invalid tool input'
            self.state['errors'].append({'operation': message.get('op'), 'error': text})
            return {'error': text}
        finally:
            self.save()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--batch', type=Path, required=True)
    p.add_argument('--task', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--mode', choices=['tools', 'no_data', 'report_only'], required=True)
    p.add_argument('--prior-trajectory', type=Path)
    p.add_argument('--max-calls', type=int, default=64)
    a = p.parse_args()
    task, records, records_hash = approved_task(a.batch, a.task)
    a.out.mkdir(parents=True, exist_ok=True)
    write_json(a.out / 'source_identity.private.json', {
        'task_sha256': digest(task), 'records_file_sha256': records_hash})
    bridge = Bridge(task, records, a.out, mode=a.mode, max_calls=a.max_calls)
    if a.mode == 'report_only':
        if a.prior_trajectory is None:
            raise DataError('A reporting probe requires a baseline trajectory')
        bridge.seed_reporting_probe(read_json(a.prior_trajectory))
    elif a.prior_trajectory is not None:
        raise DataError('Prior evidence is forbidden in baseline conditions')
    for line in sys.stdin:
        try:
            message = json.loads(line)
            result = bridge.handle(message)
        except (ValueError, TypeError):
            result = {'error': 'Invalid JSONL input'}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
