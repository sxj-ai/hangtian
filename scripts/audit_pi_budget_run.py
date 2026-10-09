"""Post-batch execution audit; does not grade the model's conclusions."""
import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def lines(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s] if path.exists() else []


def audit(root):
    status = read(root / 'status.json')
    if status['status'] != 'runs_finished_pending_semantic_review' or len(status['tasks']) != 15:
        raise RuntimeError('Wait for the complete 15-task batch before auditing')
    config = read(root / 'model_config.json')
    checks, tasks = [], []

    def check(tid, name, passed):
        checks.append({'task_id': tid, 'check': name, 'passed': bool(passed)})

    for i in range(1, 16):
        tid = f'T{i:02d}'
        d = root / (tid + '_tools')
        meta, trajectory = read(d / 'run_metadata.json'), read(d / 'trajectory.json')
        boundary = read(d / 'session_boundary.json')
        requests = lines(d / 'request_audit.jsonl')
        responses = lines(d / 'response_audit.jsonl')
        wire = {x['index']: x for x in responses}
        check(tid, 'request_budget', len(requests) == meta['api_requests'] <= config['max_api_calls_per_task'])
        check(tid, 'request_sequence', [r['index'] for r in requests] == list(range(1, len(requests)+1)))
        check(tid, 'all_responses_logged', set(wire) == {r['index'] for r in requests})
        check(tid, 'no_private_context', not boundary['private_reference_exposed'] and
              not boundary['project_context_files'] and not boundary['skills'] and not boundary['extensions'])
        check(tid, 'only_two_tools', sorted(boundary['active_tools']) == ['submit_report', 'telemetry_query'])
        check(tid, 'empty_prior_conversation', not any(m['role'] != 'system' for m in boundary['initial_messages']))
        check(tid, 'submission_state_matches', (meta['status'] == 'submitted') == (trajectory['answer'] is not None))
        check(tid, 'query_budget', trajectory['tool_attempts'] <= config['max_tool_calls_per_task'])
        check(tid, 'same_session_reporting', meta['budget_state']['same_session_reporting'])
        reporting_started = False
        for request in requests:
            notice = request['budget_notice']
            response = wire.get(request['index'], {})
            remote = config['model'] == 'deepseek-flash' and config['base_url'] == 'https://api.deepseek.com'
            provider_valid = (request['url'] == 'https://api.deepseek.com/chat/completions' and
                  request.get('thinking') == {'type':'disabled'}) if remote else (
                  request['url'] == config['base_url'].rstrip('/')+'/chat/completions' and
                  request.get('chat_template_kwargs') == {'enable_thinking':False})
            check(tid, f"request_{request['index']}_provider_no_thinking", provider_valid and request['model'] == config['model'])
            check(tid, f"request_{request['index']}_real_model", response.get('http_status') == 200 and
                  response.get('models') == [config['model']] and not response.get('reasoning_content_seen'))
            check(tid, f"request_{request['index']}_budget_notice", notice['request'] == request['index'] and
                  notice['maximum_model_requests'] == config['max_api_calls_per_task'] and notice['requests_left_including_this'] >= 1)
            check(tid, f"request_{request['index']}_context", request['prompt_tokens_preflight'] + request['max_tokens'] <= config['context_window'])
            actual_tokens = (response.get('usage') or {}).get('prompt_tokens')
            check(tid, f"request_{request['index']}_context_count_consistency", isinstance(actual_tokens,int) and (
                  request['prompt_tokens_preflight'] >= actual_tokens if remote else request['prompt_tokens_preflight'] == actual_tokens))
            if notice['phase'] == 'reporting':
                reporting_started = True
            check(tid, f"request_{request['index']}_report_phase_tools", not reporting_started or
                  (notice['phase'] == 'reporting' and request['tool_names'] == ['submit_report']))
            check(tid, f"request_{request['index']}_reserved_tail", request['index'] <=
                  config['max_api_calls_per_task']-config['reserved_report_requests'] or notice['phase'] == 'reporting')
        results=lines(d/'pi_tool_results.jsonl')
        result_by_id={x['toolCallId']:x for x in results}
        emitted=[c for m in lines(d/'assistant_messages.jsonl') for c in m.get('content',[]) if c.get('type')=='toolCall']
        backend=lines(d/'tool_calls.jsonl')
        check(tid,'all_tool_events_logged',{c['id'] for c in emitted} == set(result_by_id))
        for call in backend:
            result=result_by_id.get(call['tool_call_id'],{})
            check(tid,'tool_error_flag_'+call['tool_call_id'],bool(call['result'].get('error')) == result.get('isError'))
        budget_denials=[c for c in backend if c['result'].get('error','').startswith('Investigation budget ended')]
        # This flags the specific known wrapper defect; model calls of unavailable
        # tools are separate errors and are not automatically a protocol failure.
        check(tid,'no_premature_query_denial',not budget_denials)
        tasks.append({'task_id': tid, 'status': meta['status'], 'requests': len(requests),
                      'queries': trajectory['tool_attempts'], 'observations': len(trajectory['observations']),
                      'backend_errors':sum(bool(c['result'].get('error')) for c in backend),
                      'pi_errors':sum(bool(c.get('isError')) for c in results),
                      'tool_events':len(results),'successful_query_ids':len({o['observation_id'] for o in trajectory['observations']}),
                      'budget_state': meta['budget_state'],
                      'max_prompt_tokens': max((r['prompt_tokens_preflight'] for r in requests), default=0)})
    return {'scope': 'Execution policy only; not semantic correctness.',
            'passed': all(c['passed'] for c in checks), 'checks_count': len(checks),
            'failed_checks': [c for c in checks if not c['passed']], 'tasks': tasks}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    args = p.parse_args()
    result = audit(args.run)
    (args.run / 'budget_boundary_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'tasks'}, ensure_ascii=False))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
