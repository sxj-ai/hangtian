"""Bind already-read, root-approved review decisions to exact publication objects.

This is a serialization gate, not an automatic semantic reviewer. The caller must
read and approve the supplied review recommendations before invoking it.
"""
import argparse
from pathlib import Path
from hangtian.autonomous import export_tasks, public_environment, review_gate
from hangtian.data import DataError, digest, file_hash, write_json
from hangtian.materials import read_json


def verify_review_identity(review,task,material,selected_source):
    tid=task['task_id']
    if review.get('public_project_digest')!=digest(task):
        raise DataError(tid+' public environment review is missing or stale')
    if review.get('material_project_digest')!=digest(material):
        raise DataError(tid+' material review is missing or stale')
    reviewed_job=review.get('reviewed_generation_job')
    if not reviewed_job or str(reviewed_job) not in Path(selected_source).parts:
        raise DataError(tid+' selected model generation differs from reviewed version')


def bind(expansion, selected_file, review_files, approve_reviewed_outcomes=False):
    if not approve_reviewed_outcomes:
        raise DataError('Explicit current-assistant adjudication required')
    selected=read_json(selected_file)
    policy=read_json(expansion/'final_grading_policy.private.json')
    reviews={}
    for path in review_files:
        document=read_json(path)
        for task in document['tasks']:
            tid=task['task_id']
            if tid in reviews:raise DataError('Duplicate task review')
            reviews[tid]=(task,{'path':str(path),'sha256':file_hash(path),
                               'reviewer':document['reviewer']})
    if set(reviews)!={f'T{i:02d}' for i in range(16,101)}:
        raise DataError('Expected all 85 new task reviews')
    staged=[]
    for case in read_json(expansion/'private/manifest.json')['cases']:
        cid=case['case_id'];directory=Path(selected[cid]);source=Path(case['source_case_dir'])
        saved=read_json(directory/'private/candidate.json')
        material=read_json(source/'private/material.json');records=read_json(source/'private/records.json')
        public=export_tasks(saved['proposal'],material,
            public_environment(material,records,case['public_context']),case['targets'])
        rubric=dict(policy,tasks=[]);accepted=[];sources=[]
        for task in public:
            tid=task['task_id'];review,origin=reviews[tid]
            if review['public_decision']!='accept':raise DataError(tid+' is not accepted')
            for field in ['title','prompt']:
                if task[field]!=review.get('reviewed_'+field,review.get(field)):
                    raise DataError(tid+' review text is stale')
            verify_review_identity(review,task,material,saved['selected_sources'][tid])
            criteria=review.get('proposed_outcome_criteria')
            rationale=review.get('public_rationale',review.get('rationale'))
            if not criteria or not rationale:raise DataError(tid+' has incomplete substantive review')
            slot_id=next(s for s,t in case['targets'].items() if t==tid)
            slot=next(s for s in material['task_slots'] if s['slot_id']==slot_id)
            notes=review.get('grading_notes',[])
            if isinstance(notes,list):notes='\n'.join(notes)
            alternatives=review.get('alternative_valid_paths',review.get('acceptable_alternative_paths',[]))
            rubric['tasks'].append({'task_id':tid,'criteria':criteria,'grading_notes':notes,
                'acceptable_alternative_paths':alternatives,'reference_fact_ids':slot['measurement_ids'],
                'references_are_examples_not_required_queries':True})
            accepted.append({'task_id':tid,'decision':'accept','blocking_issues':[],
                'no_solution_plan':True,'data_dependent':True,'fair_outcome_rubric':True,
                'rationale':rationale,'root_adjudication':
                    '本助手已阅读题面、分组审查及逐题评分建议，采纳所列结果标准并应用统一范围/替代路径政策；此审核不等于Agent实跑通过。'})
            sources.append(dict(origin,task_id=tid,review_sha256=digest(review)))
        approval={'reviewer':'current_assistant','purpose':'autonomous_investigation',
            'proposal_sha256':digest(saved['proposal']),'public_sha256':digest(public),
            'outcome_rubric_sha256':digest(rubric),'material_sha256':digest(material),
            'reviews':accepted,'supporting_subagent_reviews':sources,
            'final_grading_policy_sha256':digest(policy)}
        review_gate(approval,saved['proposal'],public,material,rubric)
        staged.append((directory,approval,rubric))
    for directory,approval,rubric in staged:
        write_json(directory/'private/autonomy_review.json',approval)
        write_json(directory/'private/outcome_rubric.json',rubric)
    print({'bound_cases':len(staged),'reviewed_tasks':len(reviews),'solver_trajectories_created':0})


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--expansion',type=Path,required=True)
    p.add_argument('--selection',type=Path,required=True)
    p.add_argument('--reviews',type=Path,nargs='+',required=True)
    p.add_argument('--approve-reviewed-outcomes',action='store_true')
    a=p.parse_args();bind(a.expansion,a.selection,a.reviews,a.approve_reviewed_outcomes)
