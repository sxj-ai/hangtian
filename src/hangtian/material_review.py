"""Finalize API candidates only after hash-bound assistant review and raw-data checks."""
from copy import deepcopy
from pathlib import Path

from .data import DataError, digest, file_hash, write_json
from .materials import MaterialTools, public_task, read_json, verify_proposal
from .material_pipeline import task_review_gate, validate_answer


def review_gate(review, proposal, material, public):
    if review.get('reviewer') != 'current_assistant':
        raise DataError('An explicit current-assistant review is required')
    for key, value in [('proposal_sha256', proposal), ('material_sha256', material), ('public_tasks_sha256', public)]:
        if review.get(key) != digest(value):
            raise DataError('Assistant review is stale: ' + key)
    task_review_gate({'reviews': review['reviews']}, proposal)
    for item in review['reviews']:
        if not item['rationale'].strip():
            raise DataError('Each task needs an actual review rationale')


def reference_audit(task, material, records):
    facts = {f['fact_id']: f for f in material['facts']}
    rules = {r['interpretation_id']: r for r in material['interpretations']}
    tool = MaterialTools(records, task['required_record_ids'])
    obs = {i: tool.call(facts[i]['query']) for i in task['measurement_ids']}
    answer = {'measurements': [{'measurement_id': i, 'value': obs[i]['result']['value'],
        'observation_id': obs[i]['observation_id']} for i in task['measurement_ids']],
        'interpretations': [{'interpretation_id': i, 'verdict': rules[i]['expected_verdict'],
            'explanation': rules[i]['rationale'], 'observation_ids': [obs[f]['observation_id'] for f in rules[i]['fact_ids']]}
            for i in task['interpretation_ids']], 'limitations': material['limitations']}
    replay = {'task_id': task['task_id'], 'answer': answer, 'observations': tool.observations,
              'provenance': 'Deterministic reference replay; NOT an independent agent solution.'}
    hard = validate_answer(task, material, records, replay)
    if not hard['hard_pass']:
        raise DataError('Reference replay failed')
    negatives = []
    for defect in ('wrong_number', 'fake_citation', 'missing_measurement', 'wrong_interpretation'):
        bad = deepcopy(replay)
        if defect == 'wrong_number':
            next(m for m in bad['answer']['measurements'] if m['value'] is not None)['value'] += 1
        elif defect == 'fake_citation':
            bad['answer']['measurements'][0]['observation_id'] = 'O_fabricated'
        elif defect == 'missing_measurement':
            bad['answer']['measurements'].pop()
        else:
            entry = bad['answer']['interpretations'][0]
            entry['verdict'] = 'refuted' if entry['verdict'] != 'refuted' else 'supported'
        negatives.append({'defect': defect, 'rejected': not validate_answer(task, material, records, bad)['hard_pass']})
    if not all(n['rejected'] for n in negatives):
        raise DataError('Negative control failed')
    return replay, {'task_id': task['task_id'], 'status': 'reviewed_reference_checked_pending_agent',
        'reference_tool_consistency': hard, 'validator_negative_controls': negatives,
        'independent_agent_solve': 'not_run', 'semantic_review': 'current_assistant',
        'limitation': 'These checks do not measure agent success rate or establish a unique physical cause.'}


def finalize(case_dir: Path, review_path: Path):
    material = read_json(case_dir / 'private/material.json')
    records = read_json(case_dir / 'private/records.json')
    generated = read_json(case_dir / 'private/generated_candidate.json')
    if generated.get('authorship') != 'remote_api':
        raise DataError('Only API-generated candidates enter this finalizer')
    proposal = generated['proposal']
    verify_proposal(proposal, material)
    public = [public_task(t, material) for t in proposal['tasks']]
    if public != generated['public_tasks']:
        raise DataError('Candidate export changed')
    review = read_json(review_path)
    review_gate(review, proposal, material, public)
    independent = read_json(case_dir / 'independent_material_validation.json')
    if not independent.get('all_passed') or independent.get('material_sha256') != digest(material):
        raise DataError('Independent raw-data verification is missing or stale')
    if independent.get('records_sha256') != digest(records):
        raise DataError('Validated query records changed')
    for p in material['provenance']:
        for kind in ['telemetry', 'context']:
            if file_hash(Path(p[kind + '_path'])) != p['source_hashes'][kind]:
                raise DataError('Raw source changed after material validation')
    results, replays = [], []
    for task in proposal['tasks']:
        replay, result = reference_audit(task, material, records)
        results.append(result); replays.append(replay)
    # Export only after every gate succeeds.
    for task in public:
        write_json(case_dir / 'public' / (task['task_id'] + '.json'), task)
    write_json(case_dir / 'public/tasks.json', public)
    write_json(case_dir / 'private/assistant_review.json', review)
    write_json(case_dir / 'private/reference_replays.json', replays)
    write_json(case_dir / 'validation_results.json', {'material_id': material['material_id'], 'results': results})
    summary = read_json(case_dir / 'summary.json')
    summary.update(status='api_generated_reviewed_reference_checked_pending_agent', authorship='remote_api',
        tasks_generated=len(public), assistant_reviewed=len(public), reference_replays=len(replays),
        trajectories=0, pilot_passed=0, independent_raw_check='pass')
    write_json(case_dir / 'summary.json', summary)
    write_json(case_dir / 'bundle.private.json', {'material': material, 'generation': generated,
        'assistant_review': review, 'reference_replays': replays, 'validations': results,
        'summary': summary, 'warning': 'Private reference answers and source identities. Never give to a solver.'})
    return summary
