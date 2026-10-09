"""API authoring only. Candidates need a new, hash-bound assistant review."""
import argparse
from pathlib import Path

from hangtian.autonomous import public_environment, generator_input, export_tasks
from hangtian.data import DataError, digest, file_hash, write_json
from hangtian.materials import read_json
from hangtian.models import DeepSeekModel


def generate(manifest_path, config_path, out, root, allow_remote, allow_data_egress):
    manifest = read_json(manifest_path)
    config = read_json(config_path)
    settings = config['models']['autonomous_generator']
    if settings['model'] != 'deepseek-flash' or set(config['models']) != {'autonomous_generator'}:
        raise DataError('This generation run permits the flash generator role only')
    identity = {'manifest_sha256': digest(manifest), 'config_sha256': digest(config),
                'prompt_file_sha256': file_hash(root/'prompts/autonomous_generator.md')}
    identity_path = out/'private/input_identity.json'
    if identity_path.exists() and read_json(identity_path) != identity:
        raise DataError('Changed run inputs; use a fresh output directory')
    write_json(identity_path, identity)
    write_json(out/'private/manifest.json', manifest)
    model = DeepSeekModel(config, root, out, allow_remote, allow_data_egress)
    results = []
    for case in manifest['cases']:
        source = Path(case['source_case_dir'])
        material = read_json(source/'private/material.json')
        records = read_json(source/'private/records.json')
        environment = public_environment(material, records, case['public_context'])
        payload = generator_input(material, environment, case['targets'])
        if case.get('generation_feedback'):
            payload['generation_feedback'] = case['generation_feedback']
        case_dir = out/case['case_id']
        identity = {'material_sha256': digest(material), 'records_file_sha256': file_hash(source/'private/records.json'),
                    'input_sha256': digest(payload)}
        candidate_path = case_dir/'private/candidate.json'
        if candidate_path.exists():
            saved = read_json(candidate_path)
            if saved['identity'] != identity:
                raise DataError('Source changed during resume')
            proposal = saved['proposal']
        else:
            proposal = model.call('autonomous_generator', payload, 'autonomous_tasks')
            # Keep even structurally invalid responses for truthful revision/auditing.
            write_json(candidate_path, {'identity': identity, 'proposal': proposal, 'authorship': 'remote_api'})
        public = export_tasks(proposal, material, environment, case['targets'])
        write_json(case_dir/'candidate_tasks.json', public)
        result = {'case_id': case['case_id'], 'tasks': len(public), 'status': 'pending_autonomous_review',
                  'proposal_sha256': digest(proposal), 'public_sha256': digest(public),
                  'material_sha256': digest(material), 'agent_trajectories': 0}
        write_json(case_dir/'summary.json', result)
        results.append(result)
        print(result, flush=True)
    write_json(out/'generation_summary.json', {'cases': results, 'api_calls_in_run': model.calls,
                                             'agent_trajectories': 0})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('manifest', 'config', 'out', 'project-root'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--allow-remote', action='store_true')
    p.add_argument('--allow-data-egress', action='store_true')
    a = p.parse_args()
    generate(a.manifest, a.config, a.out, a.project_root, a.allow_remote, a.allow_data_egress)
