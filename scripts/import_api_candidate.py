"""Reuse an unchanged API proposal after explicit metadata-only recipe corrections.

This is not an acceptance path: a new hash-bound review and raw validation are
still required. Original generation artifacts remain in their original run.
"""
import argparse
from pathlib import Path
from hangtian.data import digest, write_json, DataError
from hangtian.materials import build_material, public_task, read_json, verify_proposal


def import_candidate(source, recipe, out):
    if out.exists():raise DataError('Use a new import output directory')
    prior = read_json(source/'private/generated_candidate.json')
    if prior.get('authorship') != 'remote_api':raise DataError('Source is not an API candidate')
    material, _ = build_material(recipe,out)
    old_material = read_json(source/'private/material.json')
    # Only fact unit metadata may differ. No substituted evidence or scoring rules.
    def strip_units(m):
        m = {**m, 'facts':[{k:v for k,v in f.items() if k != 'unit'} for f in m['facts']]}
        return {k:v for k,v in m.items() if k != 'recipe_sha256'}
    if strip_units(material) != strip_units(old_material):raise DataError('Import permits only unit metadata corrections')
    proposal = prior['proposal']; verify_proposal(proposal,material)
    public = [public_task(t,material) for t in proposal['tasks']]
    result={**prior,'public_tasks':public,'import_provenance':{'source_case':str(source),
        'original_candidate_sha256':digest(prior),'unchanged_api_proposal_sha256':digest(proposal),
        'change':'Correct quality metric units: timestamp groups, channels and intervals are not record rows.'}}
    write_json(out/'private/generated_candidate.json',result)
    write_json(out/'candidate_tasks.json',public)
    write_json(out/'summary.json',read_json(source/'summary.json'))
    write_json(out/'private/import_identity.json',result['import_provenance'])


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--recipe',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();import_candidate(a.source,a.recipe,a.out)
