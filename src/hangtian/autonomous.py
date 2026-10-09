"""Bounded autonomous investigations; reference paths are never solver inputs."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import statistics

from .contracts import validate
from .data import DataError, digest, write_json
from .materials import execute, leak_scan


def public_environment(material: dict, records: dict, context: list[str]) -> dict:
    """Explicit neutral context is curated, never copied from instructional background."""
    catalog = []
    for record in material['record_catalog']:
        rid = record['record_id']
        data = records[rid]
        catalog.append({k: record[k] for k in ('record_id', 'series_id', 'sequence_index')}
            | {'start_row': data['row_origin'],
               'stop_row': data['row_origin'] + len(data['time_s'])})
    result = {'schema_version': 'autonomous-0.1', 'records': catalog,
              'channels': deepcopy(material['channels']), 'context': context,
              'tool_ops': ['read', 'profile', 'stat', 'quality', 'first_sustained', 'longest_zero_run']}
    leak_scan(result, material)
    return result


def generator_input(material: dict, environment: dict, targets: dict) -> dict:
    facts = {f['fact_id']: f for f in material['facts']}
    rules = {r['interpretation_id']: r for r in material['interpretations']}
    slots = []
    for s in material['task_slots']:
        if s['slot_id'] not in targets:
            continue
        slots.append({'slot_id': s['slot_id'], 'target_task_id': targets[s['slot_id']],
                      'private_research_focus': s['focus'],
                      'private_reference_facts': [facts[i] for i in s['measurement_ids']],
                      'private_reference_interpretations': [rules[i] for i in s['interpretation_ids']]})
    # References go to the already-authorized generator only, not the solver.
    return {'material_id': material['material_id'], 'public_environment': environment,
            'task_slots': slots, 'private_limitations': material['limitations']}


def export_tasks(proposal: dict, material: dict, environment: dict, targets: dict) -> list[dict]:
    validate('autonomous_tasks', proposal)
    if proposal['material_id'] != material['material_id']:
        raise DataError('Material mismatch')
    if len(proposal['tasks']) != len(targets) or {t['slot_id'] for t in proposal['tasks']} != set(targets):
        raise DataError('Slot coverage mismatch')
    fact_ids = {f['fact_id'] for f in material['facts']}
    if len({t['task_id'] for t in proposal['tasks']}) != len(targets):
        raise DataError('Duplicate task ID')
    public = []
    for t in proposal['tasks']:
        if t['task_id'] != targets[t['slot_id']]:
            raise DataError('Task identity mismatch')
        for criterion in t['private_rubric']:
            if not set(criterion['reference_fact_ids']).issubset(fact_ids):
                raise DataError('Invented rubric evidence')
        item = {k: t[k] for k in ('task_id', 'title', 'prompt')}
        item.update({'schema_version': 'autonomous-0.1', 'environment': deepcopy(environment),
                     'response_requirements': [
                         '提交针对调查目标的发现、结论和必要限定。',
                         '数据判断须引用实际工具观测；使用的判据或分析假设需交代清楚。']})
        leak_scan(item, material)
        public.append(item)
    return public


def review_gate(review: dict, proposal: dict, public: list[dict], material: dict,
                outcome_rubric: dict) -> None:
    if (review.get('reviewer') != 'current_assistant'
        or review.get('purpose') != 'autonomous_investigation'
        or review.get('proposal_sha256') != digest(proposal)
        or review.get('public_sha256') != digest(public)
        or review.get('outcome_rubric_sha256') != digest(outcome_rubric)
        or review.get('material_sha256') != digest(material)):
        raise DataError('Missing or stale autonomous review')
    checks = review.get('reviews', [])
    ids = [r['task_id'] for r in checks]
    if len(ids) != len(set(ids)) or set(ids) != {t['task_id'] for t in public}:
        raise DataError('Incomplete task review')
    criteria = outcome_rubric.get('tasks', [])
    if len(criteria) != len(public) or {t['task_id'] for t in criteria} != set(ids):
        raise DataError('Incomplete outcome rubric')
    for r in checks:
        if r.get('decision') != 'accept' or r.get('blocking_issues') or not r.get('rationale'):
            raise DataError('Autonomous task needs revision')
        if not all(r.get(k) is True for k in ('no_solution_plan', 'data_dependent', 'fair_outcome_rubric')):
            raise DataError('Autonomy review criteria unmet')


def run_query(records: dict, query: dict) -> dict:
    validate('autonomous_query', query)
    if query['record_id'] not in records:
        raise DataError('Record outside environment')
    record = records[query['record_id']]
    origin = record['row_origin']
    a, b = query['start_row'] - origin, query['stop_row'] - origin
    if not 0 <= a < b <= len(record['time_s']):
        raise DataError('Window outside permitted record')
    op = query['op']
    fields = {'read': {'channels'}, 'profile': {'channels', 'bins'},
              'stat': {'channel', 'stat'}, 'quality': {'metric'},
              'first_sustained': {'channel', 'threshold', 'min_records', 'direction'},
              'longest_zero_run': {'channels'}}
    if set(query) != {'record_id', 'op', 'start_row', 'stop_row'} | fields[op]:
        raise DataError('Unexpected or missing operation fields')
    channels = query.get('channels', [query['channel']] if 'channel' in query else [])
    if len(channels) != len(set(channels)) or not set(channels).issubset(record['channels']):
        raise DataError('Undeclared or repeated channel')
    if op == 'read':
        end = min(b, a + 512)
        return {'source_rows': [origin+a, origin+end], 'time_s': record['time_s'][a:end],
                'channels': {c: record['channels'][c][a:end] for c in channels},
                'next_start_row': origin+end if end < b else None,
                'requested_stop_row': origin+b}
    if op == 'profile':
        count = min(query['bins'], b-a)
        bins = []
        for i in range(count):
            lo, hi = a+(b-a)*i//count, a+(b-a)*(i+1)//count
            bins.append({'source_rows': [origin+lo, origin+hi],
                'first_time_s': record['time_s'][lo], 'last_time_s': record['time_s'][hi-1],
                'count': hi-lo, 'channels': {c: {
                    'min': min(record['channels'][c][lo:hi]),
                    'max': max(record['channels'][c][lo:hi]),
                    'mean': statistics.fmean(record['channels'][c][lo:hi])} for c in channels}})
        return {'bins': bins, 'definition': 'Contiguous acquisition-row bins; no sorting or resampling.'}
    # Reuse the checked numerical primitives with a solver-selected window, never
    # an answer-bearing region name or reference query supplied by the task.
    scoped = dict(record)
    scoped['regions'] = {'selected': [origin+a, origin+b]}
    numerical = {k: v for k, v in query.items() if k not in {'start_row', 'stop_row'}}
    numerical.update(region='selected', slice='all')
    return execute({query['record_id']: scoped}, numerical)


class InvestigationTools:
    def __init__(self, records: dict):
        self.records = records
        self.observations = []

    def call(self, query: dict) -> dict:
        result = run_query(self.records, query)
        value = {'query': deepcopy(query), 'result': result}
        observation = value | {'observation_id': 'O_' + digest(value)[:20]}
        self.observations.append(observation)
        return observation


def verify_evidence(trajectory: dict, records: dict) -> dict:
    """Integrity only: semantic correctness always needs separate outcome review."""
    issues = []
    observed = {}
    for observation in trajectory.get('observations', []):
        oid = observation.get('observation_id')
        try:
            recomputed = run_query(records, observation['query'])
            expected_id = 'O_' + digest({'query': observation['query'], 'result': recomputed})[:20]
            if oid != expected_id or observation.get('result') != recomputed:
                issues.append('Observation replay mismatch')
            observed[oid] = observation
        except (DataError, KeyError, TypeError):
            issues.append('Invalid observation')
    answer = trajectory.get('answer')
    try:
        validate('autonomous_answer', answer)
        for finding in answer['findings']:
            if not set(finding['observation_ids']).issubset(observed):
                issues.append('Unknown evidence citation')
    except DataError:
        issues.append('Missing or invalid final answer')
    return {'evidence_integrity_pass': not issues, 'issues': issues,
            'semantic_status': 'pending_outcome_review', 'task_pass': None,
            'reference_query_matching_required': False}


def solve(public_tasks: list[dict], task_id: str, records: dict, model, out: Path,
          *, review: dict, proposal: dict, material: dict, outcome_rubric: dict,
          max_steps: int = 16) -> dict:
    """An independently approved public export is mandatory; only it goes to the model."""
    review_gate(review, proposal, public_tasks, material, outcome_rubric)
    matches = [t for t in public_tasks if t['task_id'] == task_id]
    if len(matches) != 1:
        raise DataError('Unknown task')
    public_task = matches[0]
    permitted = {r['record_id'] for r in public_task['environment']['records']}
    tool = InvestigationTools({k: v for k, v in records.items() if k in permitted})
    result = {'task_id': public_task['task_id'], 'steps': [], 'observations': tool.observations,
              'errors': [], 'answer': None, 'status': 'step_budget_exhausted'}
    for index in range(max_steps):
        payload = {'task': public_task, 'observations': tool.observations,
                   'tool_errors': result['errors'], 'steps_remaining': max_steps-index}
        step = model.call('autonomous_solver', payload, 'autonomous_step')
        result['steps'].append(step)
        try:
            validate('autonomous_step', step)
            if step['action'] == 'submit':
                result.update(answer=step['answer'], status='submitted')
            else:
                for query in step['queries']:
                    try:
                        tool.call(query)
                    except DataError as error:
                        result['errors'].append({'query': query, 'error': str(error)})
        except DataError as error:
            result['errors'].append({'error': str(error)})
        write_json(out / ('trajectory_' + public_task['task_id'] + '.json'), result)
        if result['answer'] is not None:
            break
    return result
